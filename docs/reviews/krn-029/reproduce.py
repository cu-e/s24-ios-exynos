#!/usr/bin/env python3
"""Independent XTS capsule/corpus audit and bounded actual host/ARM replay."""
from collections import Counter
import datetime
import hashlib
import io
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import sys
import tarfile
import time
import traceback
import zipfile
from object_reader import Object

HERE=Path(__file__).resolve().parent;WT=HERE.parents[2];MAIN=WT.parents[1]
IMPL=MAIN/'worktrees/krn-029-20261105';SRC=IMPL/'src/platform/crypto/xts'
BASE=IMPL/'artifacts/crypto-xts/final-commit2';TIP='7b7607b1f907d2e51dbb55766de9cdee772c0842'
OUT=WT/'artifacts/rev-krn-029'/sys.argv[1];OUT.mkdir(parents=True,exist_ok=False)
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',
 ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
commands,checks=[],[];resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(MAIN))
def passed(name,**data):checks.append(dict(name=name,pass_check=True,**data))
def read(p):return json.loads(Path(p).read_text())
def status():return Path('/proc/self/status').read_text()
def rss():return int(re.search(r'^VmRSS:\s+(\d+) kB$',status(),re.M)[1])
def group(pgid):
    live=[];total=0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid and fields[0]!='Z':live.append(int(p.name));total+=int(fields[21])*os.sysconf('SC_PAGE_SIZE')//1024
        except (OSError,ValueError,IndexError):pass
    return live,total
def run(label,argv,codes=(0,),timeout=30,budget=256,expected_timeout=False):
    argv=[str(a) for a in argv];a,b=OUT/(label+'.stdout'),OUT/(label+'.stderr')
    start=time.monotonic();peak=0;stop=None;escalated=False
    with a.open('wb') as so,b.open('wb') as se:
        p=subprocess.Popen(argv,cwd=WT,env=ENV,stdin=subprocess.DEVNULL,stdout=so,stderr=se,start_new_session=True)
        while p.poll() is None:
            _,owned=group(p.pid);total=owned+rss();peak=max(peak,total)
            if total>budget*1024:stop='RSS-limit'
            elif time.monotonic()-start>=timeout:stop='timeout'
            if stop:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=1)
                except subprocess.TimeoutExpired:escalated=True;os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
                break
            time.sleep(.02)
        code=p.wait(timeout=2)
    remaining,_=group(p.pid)
    if remaining:
        os.killpg(p.pid,signal.SIGKILL)
        for _ in range(100):
            remaining,_=group(p.pid)
            if not remaining:break
            time.sleep(.01)
    commands.append(dict(label=label,argv=argv,cwd=str(WT),exit_code=code,stdout=rel(a),stderr=rel(b),
       elapsed_seconds=time.monotonic()-start,timeout_seconds=timeout,rss_budget_mib=budget,
       peak_total_owned_rss_kib=peak,owned_process_group=p.pid,stop_reason=stop,
       sigkill_escalated=escalated,remaining_live_owned_children=remaining))
    assert not remaining and (stop=='timeout' if expected_timeout else stop is None and code in codes),(label,code,stop,b.read_text(errors='replace')[-2000:])
    return a.read_bytes(),b.read_bytes()
def active_guests():
    result=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            if (p/'exe').resolve().name=='qemu-system-aarch64':result.append(int(p.name))
        except (OSError,RuntimeError):pass
    return result

report=dict(kind='source-review',origin='local-host',outcome='fail',commit=TIP,
 recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=commands,checks=checks,
 device_executed=False,summary='Independent typed XTS source/corpus/lifecycle and actual host/synthetic ARM review')
try:
    capsule=read(BASE/'evidence.json');descriptor=read(MAIN/'docs/procedures/crypto-xts/qualified-evidence.json')
    assert sha(BASE/'evidence.json')==descriptor['report_sha256'] and capsule['outcome']=='pass' and capsule['commit']==TIP
    for name,h in capsule['artifact_hashes'].items():assert sha(IMPL/name)==h,name
    for name,h in capsule['owned_source_hashes'].items():
        assert sha(IMPL/name)==sha(MAIN/name)==h,name
        if name in ['src/platform/crypto/xts/xts.c','src/platform/crypto/xts/memory.c','src/platform/crypto/xts/check.py','fixtures/public/avf-handoff/runtime.h']:
            data,_=run('exact-source-'+Path(name).stem,['git','-C',MAIN,'cat-file','blob',TIP+':'+name]);assert hashlib.sha256(data).hexdigest()==h
    for p,h in capsule['dependency_hashes'].items():assert sha(Path(p))==h,p
    for name,h in capsule['selected_source_checks'].items():
        data,_=run('selected-'+Path(name).stem,['git','-C',MAIN/'references/apple-xnu','cat-file','blob','c54f35ca767986246321eb901baf8f5ff7923f6a:'+name])
        assert hashlib.sha256(data).hexdigest()==h
    passed('exact-source-capsule125-artifacts-dependencies-and-genuine-selected-ccmode-header-blobs',artifact_count=len(capsule['artifact_hashes']))
    vendor=SRC/'vendor';provenance=read(vendor/'provenance.json')
    archive=IMPL/'artifacts/crypto-xts/inputs/mbedtls.tar.gz';assert sha(archive)==provenance['archive_sha256']
    with tarfile.open(archive,'r:gz') as tar:
        root=next(n for n in tar.getnames() if n.endswith('/library/aes.c')).removesuffix('library/aes.c')
        for name,h in provenance['files'].items():
            actual=(vendor/name).read_bytes();assert hashlib.sha256(actual).hexdigest()==h
            original=tar.extractfile(root+name).read()
            if name=='library/common.h':
                patch=provenance['patches'][name];assert hashlib.sha256(original).hexdigest()==patch['upstream_sha256']
                expected=original.replace(b'#include <assert.h>',b'/* Owned freestanding AES-only port: this unit uses no runtime assert. */\n#if !defined(S24_XTS_FREESTANDING)\n#include <assert.h>\n#endif',1)
                assert expected==actual
            else:assert original==actual
    passed('all-vendor-pinned-primary-archive-bytes-license-and-sole-include-only-patch')
    corpus=read(SRC/'testdata/vectors.json');nist=IMPL/'artifacts/crypto-xts/inputs/XTSTestVectors.zip'
    assert sha(nist)==corpus['archive_sha256'] and sha(corpus['oracle']['path'])==corpus['oracle']['sha256']
    parsed=[];partial=0;sequence=0
    with zipfile.ZipFile(nist) as z:
        for name in sorted(z.namelist()):
            if not name.endswith('.rsp'):continue
            raw=z.read(name);assert hashlib.sha256(raw).hexdigest()==corpus['files'][name]
            if '128 hex str' not in name:sequence+=len(re.findall(rb'^COUNT =',raw,re.M));continue
            direction=None;row={}
            def finish():
                global partial
                if not row:return
                if int(row['DataUnitLen'])%128:partial+=1;return
                assert len(bytes.fromhex(row['PT']))*8==int(row['DataUnitLen'])
                parsed.append(dict(source='NIST',file=name,direction=direction,count=int(row['COUNT']),
                   key=row['Key'].lower(),iv=row['i'].lower(),pt=row['PT'].lower(),ct=row['CT'].lower()))
            for line in raw.decode().splitlines():
                line=line.strip()
                if line in ['[ENCRYPT]','[DECRYPT]']:
                    finish();row={};direction=line[1:-1].lower()
                elif line.startswith('COUNT ='):
                    finish();row={'COUNT':line.split('=',1)[1].strip()}
                elif row and ' = ' in line:
                    key,value=line.split(' = ',1);row[key]=value.strip()
            finish()
    assert parsed==corpus['vectors'][:1200] and len(parsed)==1200 and partial==800 and sequence==2000
    report['nist_direction_counts']=dict(Counter(v['direction'] for v in parsed))
    run('fresh-nist-openssl-replay',[sys.executable,SRC/'vectors.py',nist,OUT/'regenerated'])
    assert sha(OUT/'regenerated/vectors.json')==sha(SRC/'testdata/vectors.json')
    assert sha(OUT/'regenerated/vectors.h')==sha(SRC/'testdata/vectors.h')
    passed('independent1200-primary-record-parse-and-fresh1220-OpenSSL-corpus-replay',partial_excluded=partial,sequence_excluded=sequence)
    host=Path(capsule['tools']['host']['path']);assert sha(host)==capsule['tools']['host']['sha256']
    for p,h in capsule['tools']['host']['runtime_hashes'].items():assert sha(p)==h
    host_sources=capsule['commands'][7:10]
    assert all(c['exit_code']==0 and '-fsanitize=address,undefined' in c['argv'] for c in host_sources)
    run('original-full-host-suite',[BASE/'host'],timeout=40,budget=256)
    assert b'XTS HOST PASS vectors=1220 checks=40708 failure_line=0' in (OUT/'original-full-host-suite.stdout').read_bytes()
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-sanitize-recover=all',
       '-I'+str(SRC),'-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS')]
    run('independent-boundaries-compile',[host,*flags,'-c',HERE/'boundary_probe.c','-o',OUT/'boundary.o'])
    run('independent-boundaries-link',[host,'-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',
        OUT/'boundary.o',BASE/'host-adapter.o',BASE/'host-aes.o','-o',OUT/'boundary'])
    stdout,_=run('independent-boundaries-execute',[OUT/'boundary'])
    assert b'PASS independent XTS probe: 1220 records both directions' in stdout
    report['independent_boundary_result']=stdout.decode().strip()
    passed('actual-original40708-host-checks-and-independent-vectors-alias-lifecycle-error-controls')
    renames=['memcpy','memmove','memset','memcmp','bzero','__memcpy_chk']
    macro=lambda n:'review_memcpy_chk' if n=='__memcpy_chk' else 'review_'+n
    run('synthetic-memory-compile',[host,*flags,*['-D'+n+'='+macro(n) for n in renames],'-c',SRC/'memory.c','-o',OUT/'memory.o'])
    run('synthetic-memory-link',[host,*flags,'-Wl,--threads=1',HERE/'memory_probe.c',OUT/'memory.o','-o',OUT/'memory'])
    stdout,_=run('synthetic-memory-cases',[OUT/'memory']);report['memory_result']=stdout.decode().strip()
    run('synthetic-memory-fortify-trap',[OUT/'memory','fortify'],codes=(-4,))
    passed('real-synthetic-memory-routines132096-overlap-compare-cases-and-actual-fortify-trap')
    layout=Object((BASE/'arm-adapter.o').read_bytes()).values('_s24_xts_layout',6)
    assert layout==[608,16,48,16,288,80]
    assert all(c['accepted'] for c in capsule['guest_cases'])
    assert capsule['host_checks']-capsule['arm_checks']==5 and capsule['arm_checks']==40703
    qemu=Path(capsule['avf_inputs']['qemu']);shim=Path(capsule['avf_inputs']['shim'])
    assert sha(qemu)==capsule['avf_inputs']['pin']['qemu_sha256'] and sha(shim)==capsule['avf_inputs']['pin']['shim_sha256']
    report['guest_replays']=[]
    for index,name in [(28,'positive'),(29,'wrong-cookie'),(30,'corrupt-vector'),(31,'spin-timeout')]:
        assert not active_guests(),'Competing guest active; do not start a second guest'
        argv=capsule['commands'][index]['argv'];assert argv[argv.index('-m')+1]=='256'
        stdout,stderr=run('ARM-'+name,argv,timeout=2 if name=='spin-timeout' else 30,budget=512,expected_timeout=name=='spin-timeout')
        console=(stdout+stderr).decode(errors='replace')
        if name=='positive':
            match=re.search(r'XTS ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0',console)
            entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
            assert match and int(match[1],16)==40703 and entry
            assert int(entry[1],16)==capsule['images']['normal']['entry_pa'] and int(entry[2],16)==capsule['images']['normal']['bootargs_pa']
            assert 'XTS SYNTHETIC HANDOFF VERIFIED' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
        elif name=='wrong-cookie':assert 'XTS SYNTHETIC REJECT command-cookie' in console and 'XTS ARM PASS' not in console
        elif name=='corrupt-vector':assert 'XTS ARM FAIL' in console and 'XTS ARM PASS' not in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
        else:assert 'XTS SYNTHETIC SPIN-CONTROL' in console and 'XTS ARM PASS' not in console
        report['guest_replays'].append(dict(name=name,accepted=True,console_sha256=hashlib.sha256(stdout+stderr).hexdigest()))
    passed('actual-genuine-target-layout-and-four-fresh-conditional-ARM-payload-replays')
    report['outcome']='pass'
except Exception as e:report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
    report['review_inputs_sha256']={str(p):sha(p) for p in [Path(__file__),HERE/'boundary_probe.c',HERE/'memory_probe.c',HERE/'object_reader.py']}
    report['actual_process_VmHWM_kib']=int(re.search(r'^VmHWM:\s+(\d+) kB$',status(),re.M)[1])
    report['max_sampled_total_owned_rss_kib']=max((c['peak_total_owned_rss_kib'] for c in commands),default=0)
    report['limitations']=['Accessible capacity, lifetime and serialization remain caller obligations; numeric checks cannot verify mappings.',
       'One small compiler at a time, actual immutable256MiB QEMU payload replays, no broad backend/kernel/provider build.',
       'Software ROM-table functional tests provide no side-channel/FIPS/privateApple/provider/XNU/native qualification;kernel wrapper still ignores xts return.']
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    artifacts=sorted(p for p in OUT.rglob('*') if p.is_file())
    evidence={k:report[k] for k in ['kind','origin','outcome','commit','recorded_at','commands','summary','device_executed']}
    evidence.update(artifacts=[rel(p) for p in artifacts],sha256={rel(p):sha(p) for p in artifacts})
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),traceback=report.get('traceback'),checks=checks,
       commands=len(commands),VmHWM_kib=report['actual_process_VmHWM_kib'],owned_RSS_kib=report['max_sampled_total_owned_rss_kib'],evidence=rel(OUT/'evidence.json')),indent=2))
sys.exit(0 if report['outcome']=='pass' else 1)
