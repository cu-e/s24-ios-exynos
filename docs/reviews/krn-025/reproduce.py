#!/usr/bin/env python3
"""Independent cc_kext byte audit plus small owned source/dry-run controls."""
import datetime
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import shlex
import signal
import struct
import subprocess
import sys
import time
import traceback
from object_reader import Object,members

HERE=Path(__file__).resolve().parent;WT=HERE.parents[2];MAIN=WT.parents[1]
IMPL=MAIN/'worktrees/krn-025-20261105';BASE=IMPL/'artifacts/xnu-cc-kext'
TIP='c0c69ee1fe8d0ac84dbc7700dfaf5e03b2e1cce6'
OUT=WT/'artifacts/rev-krn-025'/sys.argv[1];OUT.mkdir(parents=True,exist_ok=False)
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
commands,checks=[],[];resource.setrlimit(resource.RLIMIT_CORE,(0,0))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def rel(p):return str(Path(p).relative_to(MAIN))
def blob(data):return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def passed(name,**kw):checks.append(dict(name=name,pass_check=True,**kw))
def group(pgid):
    live=[];rss=0
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            fields=(p/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[2])==pgid and fields[0]!='Z':
                live.append(int(p.name));rss+=int(fields[21])*os.sysconf('SC_PAGE_SIZE')//1024
        except (OSError,ValueError,IndexError):pass
    return live,rss
def run(label,argv,allowed=(0,),timeout=30):
    argv=[str(x) for x in argv];a,b=OUT/(label+'.stdout'),OUT/(label+'.stderr')
    start=time.monotonic();peak=0;reason=None;escalated=False
    with a.open('wb') as so,b.open('wb') as se:
        p=subprocess.Popen(argv,cwd=WT,env=ENV,stdout=so,stderr=se,start_new_session=True)
        while p.poll() is None:
            _,rss=group(p.pid);peak=max(peak,rss)
            if rss>256*1024:reason='owned RSS limit'
            elif time.monotonic()-start>timeout:reason='timeout'
            if reason:
                os.killpg(p.pid,signal.SIGTERM)
                try:p.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    escalated=True;os.killpg(p.pid,signal.SIGKILL);p.wait(timeout=2)
                break
            time.sleep(.01)
        code=p.wait(timeout=2)
    remaining,_=group(p.pid)
    if remaining:
        os.killpg(p.pid,signal.SIGKILL)
        for _ in range(100):
            remaining,_=group(p.pid)
            if not remaining:break
            time.sleep(.01)
    commands.append(dict(argv=argv,cwd=str(WT),exit_code=code,stdout=rel(a),stderr=rel(b),
        elapsed_seconds=time.monotonic()-start,timeout_seconds=timeout,owned_group=p.pid,
        peak_owned_rss_kib=peak,remaining_live_owned_children=remaining,stop_reason=reason,sigkill_escalated=escalated))
    assert code in allowed and reason is None and not remaining,(label,code,reason,b.read_text(errors='replace')[-1500:])
    return a.read_bytes(),b.read_bytes()
def profile(data):
    magic,cpu,sub,kind,count,extent,_,_=struct.unpack_from('<8I',data)
    assert (magic,cpu,sub,kind)==(0xfeedfacf,0x100000c,0,1)
    cursor=32;versions=[]
    for _ in range(count):
        cmd,size=struct.unpack_from('<II',data,cursor)
        if cmd==0x32:versions.append(struct.unpack_from('<II',data,cursor+8))
        if cmd==0x25:versions.append((2,struct.unpack_from('<I',data,cursor+8)[0]))
        cursor+=size
    assert cursor==32+extent and versions==[(2,0x100500)]

report=dict(kind='source-review',origin='local-host',outcome='fail',commit=TIP,
 recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=commands,checks=checks,
 device_executed=False,summary='Independent native cc_kext source/member/header/driver review and bounded source semantics')
try:
    files=['tools/build/xnu_cc_kext.py','fixtures/public/xnu-cc-kext/arithmetic-shift.c',
      'fixtures/public/xnu-cc-kext/integer-semantics.c','fixtures/public/xnu-cc-kext/link-probe.c',
      'fixtures/public/xnu-cc-kext/owned-child-stop.py','patches/cc-kext-runtime/source-pin.json',
      'patches/cc-kext-runtime/0001-ashrti3-unsigned-cross-word-shift.patch']
    for i,name in enumerate(files):
        data,_=run('exact-source-'+str(i),['git','-C',MAIN,'cat-file','blob',TIP+':'+name])
        assert data==(MAIN/name).read_bytes()==(IMPL/name).read_bytes()
    name='docs/procedures/xnu-cc-kext.md';data,_=run('handoff-source',['git','-C',MAIN,'cat-file','blob','6dbcd7cddf485ebc7f0e51d1fab200213794cf7b:'+name])
    assert data==(MAIN/name).read_bytes()
    assert (BASE/'controls-session2/builder.py').read_bytes()==(MAIN/'tools/build/xnu_cc_kext.py').read_bytes()
    passed('exact-frozen-executable-fixture-patch-and-handoff-bytes')
    capsules={};reports={}
    for name in ['source-session4','headers-session5','build-session5','corrected-session1','controls-session2']:
        p=BASE/name/'evidence.json';doc=read(p);assert doc['outcome']==('fail' if name=='build-session5' else 'pass')
        for source,h in doc['sha256'].items():assert sha(MAIN/source)==h,source
        reports[name]=read(BASE/name/'report.json')
        capsules[name]=dict(evidence=rel(p),sha256=sha(p),hash_entries=len(doc['sha256']))
    report['capsules']=capsules
    source,headers,old,corrected,controls=[reports[n] for n in capsules]
    assert len(corrected['checks'])==305 and len(controls['checks'])==343
    assert all(c['pass_check'] for r in [corrected,controls] for c in r['checks'])
    for r in [old,corrected,controls]:
        for p,h in r['tools_sha256'].items():assert sha(Path(p))==h,p
    passed('five-original-capsules-original-UBSan-failure-and305-343-passing-recorded-checks',capsules=capsules)
    source_root=MAIN/source['source_tree']['root'];manifest=read(BASE/'source-session4/source-files.json')
    assert len(manifest)==472
    for name,row in manifest.items():
        data=(source_root/name).read_bytes();assert blob(data)==row['git_blob_sha1'] and hashlib.sha256(data).hexdigest()==row['sha256']
    header_manifest=read(BASE/'headers-session5/public-header-files.json');assert len(header_manifest)==149
    for name,row in header_manifest.items():
        data=(BASE/'headers-session5/headers'/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==row['sha256'] and blob(data)==row['git_blob_sha1']
        for link in row.get('source_symlink_chain',[]):assert blob(link['target'].encode())==link['git_blob_sha1']
    for name,expected in [('build-session5',509),('corrected-session1',514)]:
        deps=read(BASE/name/'dependency-files.json');assert len(deps)==expected
        for path,digest in deps.items():assert sha(MAIN/path)==digest,path
    assert not (BASE/'build-session5/public-source-headers/sys/cdefs.h').exists()
    assert 'Not to be installed in /usr/include' in (BASE/'headers-session5/headers/sys/cdefs.h').read_text()
    passed('472-Git-blob-sources149-Git-blob-declarations-and509-original514-corrected-dependencies')
    selection=old['selection'];assert selection['count']==len(selection['sources'])==287
    assert sum('outline_atomic_helpers.dir' in n for n in selection['sources'])==125
    assert sum('/lib/profile/' in n for n in selection['sources'])==6
    assert all(old['native_feature_profile'].values()) and old['native_feature_profile']==selection['measured_features']
    cmake=(source_root/'cmake/Modules/CompilerRTDarwinUtils.cmake').read_text()
    assert 'PROFILE_SOURCES' in cmake and 'MIN_VERSION' in cmake
    command=next(c for c in old['commands'] if c['stdout'].endswith('/genuine-CMake-source-selection.stdout.txt'))
    cmakelists=(BASE/'build-session5/selection/CMakeLists.txt').read_text()
    assert 'darwin_filter_builtin_sources(filtered cc_kext_ios_arm64 EXCLUDE ios_arm64_EXCLUDED ${arm64_SOURCES})' in cmakelists
    assert 'MIN_VERSION' not in cmakelists
    for c in old['commands']:
        if '/compile-' in c['stdout']:
            assert '-mkernel' in c['argv'] and '-DKERNEL_USE' in c['argv'] and '-nostdinc' in c['argv']
    passed('genuine-native-feature-selection287-members125-outline-atomics-six-profile-sources')
    pin=read(MAIN/'patches/cc-kext-runtime/source-pin.json');patched=BASE/'corrected-session1/patched-source'
    original=(source_root/'lib/builtins/ashrti3.c').read_bytes();fixed=(patched/'lib/builtins/ashrti3.c').read_bytes()
    assert hashlib.sha256(original).hexdigest()==pin['base_sha256'] and hashlib.sha256(fixed).hexdigest()==pin['patched_sha256']
    assert original.replace(b'(input.s.high << (bits_in_dword - b))',b'((du_int)input.s.high << (bits_in_dword - b))',1)==fixed
    assert [n for n,row in manifest.items() if sha(patched/n)!=row['sha256']]==['lib/builtins/ashrti3.c']
    original_members=read(BASE/'build-session5/archive-members.json');assert len(original_members)==287
    for row in original_members:
        assert sha(BASE/'build-session5/objects'/row['name'])==sha(BASE/'corrected-session1/objects'/row['name'])==row['sha256']
    selected_archive=MAIN/controls['qualified_component']['archive'];payloads=members(selected_archive.read_bytes())
    assert len(payloads)==287 and sha(selected_archive)=='67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5'
    definitions,imports=set(),set()
    for (name,data),row in zip(payloads,original_members):
        assert name==row['name'] and hashlib.sha256(data).hexdigest()==row['sha256']
        profile(data);obj=Object(data);definitions.update(obj.exported());imports.update(obj.imported())
    assert len(definitions)==318 and len(imports-definitions)==47
    assert sorted(definitions)==controls['runtime_symbols']['defined'] and sorted(imports-definitions)==controls['runtime_symbols']['external_imports']
    assert sha(MAIN/corrected['archive']['path'])==sha(MAIN/old['archive']['path'])==sha(selected_archive)
    for index,(source_path,row) in enumerate(zip(selection['sources'],original_members)):
        expected_name=str(index)+'-'+Path(source_path).stem+'.o'
        assert row['name']==expected_name
        output=str(BASE/'build-session5/objects'/expected_name)
        actual=next(c for c in old['commands'] if '-o' in c['argv'] and c['argv'][c['argv'].index('-o')+1]==output)
        assert actual['exit_code']==0 and actual['argv'][actual['argv'].index('-c')+1]==str(MAIN/source_path)
        assert '-DHAS_ASM_LSE' in actual['argv']
    report['external_runtime_imports']=sorted(imports-definitions)
    passed('one-line-unsigned-correction287-native-members318-definitions47-imports-and-identical-original-native-bytes')
    positive=controls['driver_links']['positive'];image=MAIN/(controls['qualified_component']['resource_dir'].rsplit('/',1)[0]+'/probe-positive')
    assert sha(image)==positive['output_sha256'];view=Object(image.read_bytes())
    assert not view.imported() and {'___ashrti3','___divti3','___modti3','___multi3','___udivti3','___umodti3','_s24_runtime_link_probe'}<=view.named.keys()
    for name,item in controls['driver_links'].items():
        journal=read(MAIN/item['actual_backend_journal']);assert journal['argv']==item['expanded_backend']
        assert item['exit_code']==(0 if name=='positive' else 1) and item['output_exists']==(name=='positive')
    stop=next(c for c in controls['commands'] if 'owned-ignore-term' in c['stdout'])
    ids=read(BASE/'controls-session2/owned-stop-pids.json')
    assert ids['group']==ids['child_group']==stop['owned_process_group'] and stop['exit_code']==-9
    assert stop['sigkill_escalated'] and stop['stop_reason']=='timeout' and not stop['remaining_live_owned_children'] and stop['elapsed_seconds']<5
    passed('actual-positive-MachO-provider-image-seven-backend-journals-six-failures-and-finite-owned-stop-record')
    host=Path('/home/egor/.local/bin/clang');instrument=['-std=gnu11','-O3','-g','-fno-builtin','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    for name,root in [('original',source_root),('corrected',patched)]:
        binary=OUT/(name+'-shift')
        run(name+'-independent-shift-build',[host,*instrument,'-I',root/'lib/builtins',HERE/'shift_probe.c',root/'lib/builtins/ashrti3.c','-o',binary])
        stdout,stderr=run(name+'-independent-shift-execute',['env','ASAN_OPTIONS=detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1',binary],allowed=(1,) if name=='original' else (0,))
        if name=='original':assert b'left shift of negative value -1' in stderr
        else:assert b'PASS 132225 independent bitwise-oracle arithmetic-shift cases' in stdout
    passed('fresh-actual-original-UBSan-rejection-and132225-independent-corrected-ASan-UBSan-cases')
    c=next(c for c in controls['commands'] if c['stdout'].endswith('/driver-positive-execute.stdout.txt'))
    stdout,stderr=run('fresh-original-driver-resource-expansion',[*c['argv'],'-###'])
    wrapper=c['argv'][c['argv'].index(next(x for x in c['argv'] if x.startswith('--ld-path=')))].split('=',1)[1]
    expansions=[shlex.split(l) for l in stderr.decode().splitlines() if l.strip().startswith('"'+wrapper+'"')]
    assert len(expansions)==1 and [positive['expanded_backend'][0],*expansions[0][1:]]==positive['expanded_backend']
    assert str(selected_archive) in expansions[0] and '-lcc_kext' not in expansions[0]
    report['tools_sha256']={str(host.resolve()):sha(host),str(MAIN/controls['qualified_component']['compiler']):sha(MAIN/controls['qualified_component']['compiler'])}
    passed('fresh-actual-driver-expansion-to-exact-link-only-runtime-with-no-literal-bypass')
    report['outcome']='pass'
except Exception as e:report['error']=repr(e);report['traceback']=traceback.format_exc()
finally:
    report['review_inputs_sha256']={str(p):sha(p) for p in [HERE/'object_reader.py',HERE/'shift_probe.c',Path(__file__)]}
    report['actual_process_VmHWM_kib']=int(re.search(r'^VmHWM:\s+(\d+) kB$',Path('/proc/self/status').read_text(),re.M)[1])
    report['max_sampled_owned_child_rss_kib']=max((c['peak_owned_rss_kib'] for c in commands),default=0)
    report['limitations']=['One small owned subprocess at a time;256MiB group RSS limit;no full runtime/compiler rebuild or full kernel link.',
       'Fresh sanitizer source execution qualifies only this arithmetic-shift helper;other original integer harness evidence is separately audited.',
       'All287 native members are inspected,including47 lazy userland/kernel/unwind imports;not complete kernel/runtime/SDK/privateApple/native qualification.']
    (OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    artifacts=sorted(p for p in OUT.rglob('*') if p.is_file())
    evidence={k:report[k] for k in ['kind','origin','outcome','commit','recorded_at','commands','summary','device_executed']}
    evidence.update(artifacts=[rel(p) for p in artifacts],sha256={rel(p):sha(p) for p in artifacts})
    (OUT/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),traceback=report.get('traceback'),checks=checks,
       commands=len(commands),VmHWM_kib=report['actual_process_VmHWM_kib'],child_RSS_kib=report['max_sampled_owned_child_rss_kib'],evidence=rel(OUT/'evidence.json')),indent=2))
sys.exit(0 if report['outcome']=='pass' else 1)
