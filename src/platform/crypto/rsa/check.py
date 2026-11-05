#!/usr/bin/env python3
"""Bounded RSA host/native/synthetic CPU build;does not run QEMU or register crypto."""
import argparse,datetime,hashlib,importlib.util,json,os,re,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
GUARDS={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
spec=importlib.util.spec_from_file_location('accepted_xts_build',ROOT/'src/platform/crypto/xts/check.py');shared=importlib.util.module_from_spec(spec);spec.loader.exec_module(shared)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
GATE_OBSERVATIONS=[]
def memory_gate():
    for attempt in range(26):
        count=int(re.search(r'^MemAvailable:\s*(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
        GATE_OBSERVATIONS.append(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),MemAvailable_bytes=count))
        if count>=4*1024**3:return count
        if attempt<25:time.sleep(1)
    raise RuntimeError('MemAvailable remained below4GiB for25seconds;no new bounded process started')
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--archive',type=Path,required=True);args=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('Fresh canonical run required')
    out=ROOT/'artifacts/crypto-rsa'/args.run;out.mkdir(parents=True,exist_ok=False)
    report=dict(task='KRN-035',kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],source_reads=[],summary='Actual RSA component host/native/synthetic payload build;CPU execution is a separate root-leased step',provider_registered=False,private_ABI=False,XNU_executed=False,native_device=False,QEMU_executed=False)
    def command(argv,name,seconds=30,expected=0):
        available=memory_gate();r=shared.run(argv,out,name,seconds,256);r['MemAvailable_before_bytes']=available;report['commands'].append(r)
        if r['outcome'] in ['rss-limit','timeout'] or (expected is not None and r['exit_code']!=expected):raise RuntimeError(name+' failed;see actual retained log')
        return r
    def git(repo,specification):
        argv=['git','-C',str(repo),'show',specification];r=subprocess.run(argv,capture_output=True,timeout=15,env={**os.environ,**GUARDS})
        report['source_reads'].append(dict(argv=argv,exit_code=r.returncode,stdout_sha256=hashlib.sha256(r.stdout).hexdigest(),stderr=r.stderr.decode(errors='replace')))
        if r.returncode:raise ValueError('Unavailable exact-pin object without lazy fetch')
        return r.stdout
    try:
        report['commit']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        vendor=HERE/'vendor';prov=json.loads((vendor/'provenance.json').read_text())
        bear_repo=MAIN/'worktrees/krn-028-20261105/tools/research/crypto-candidates/local/bearssl.git'
        report['canonical_vendor']={}
        for name,row in prov['files'].items():
            raw=git(bear_repo,prov['revision']+':'+name)
            if hashlib.sha256(raw).hexdigest()!=row['sha256'] or sha(vendor/name)!=row['sha256']:raise ValueError('Canonical full BearSSL source mismatch: '+name)
            report['canonical_vendor'][name]=row
        corpus=json.loads((HERE/'testdata/vectors.json').read_text())
        if sha(args.archive)!=corpus['archive_sha256']:raise ValueError('Actual official NIST archive differs')
        command([sys.executable,HERE/'replay.py','--archive',args.archive,'--json',HERE/'testdata/vectors.json','--header',out/'replay.h'],'independent-primary-replay',60)
        if sha(out/'replay.h')!=sha(HERE/'testdata/vectors.h'):raise ValueError('Header differs from primary/public-oracle replay')
        report['corpus']={k:corpus[k] for k in ['archive_sha256','primary_count','total_count','excluded','oracle']}
        xts=json.loads((ROOT/'docs/procedures/crypto-xts/qualified-evidence.json').read_text());xts_report_path=MAIN/xts['report']
        if sha(xts_report_path)!=xts['report_sha256']:raise ValueError('Accepted zeroizer qualification changed')
        xr=json.loads(xts_report_path.read_text());xts_objects={}
        for name in ['host-adapter.o','host-aes.o','arm-adapter.o','arm-aes.o']:
            path=xts_report_path.parent/name;key='artifacts/crypto-xts/final-commit2/'+name
            if sha(path)!=xr['artifact_hashes'][key]:raise ValueError('Accepted zeroizer companion object differs')
            xts_objects[name]=path
        report['shared_zeroizer']={str(path):sha(path) for path in xts_objects.values()}
        original_path=MAIN/'artifacts/xnu-kernel-declarations/controls-session1/report.json';original=json.loads(original_path.read_text())
        source=MAIN/original['source_ports']['osfmk/mc_provider.o']['source'];recipe=next(r for r in original['commands'] if str(source) in r['argv'] and '-c' in r['argv'])
        arm=Path(recipe['argv'][0]);host=Path('/home/egor/.local/bin/clang').resolve();ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
        if sha(arm)!=original['compiler_sha256']:raise ValueError('Qualified real ARM compiler changed')
        for name,argv in [('host-version',[host,'--version']),('arm-version',[arm,'--version']),('linker-version',[ld,'-v'])]:command(argv,name)
        report['tools']={str(tool):sha(tool) for tool in [host,arm,ld]}
        common=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fno-strict-aliasing','-fstack-usage',
            '-I'+str(HERE),'-I'+str(HERE/'testdata'),'-I'+str(vendor/'inc'),'-I'+str(vendor/'src'),
            '-I'+str(ROOT/'src/platform/crypto/xts'),'-I'+str(ROOT/'src/platform/crypto/xts/vendor/include'),'-I'+str(ROOT/'src/platform/crypto/xts/vendor/library'),
            '-DMBEDTLS_CONFIG_FILE="s24_xts_profile.h"']
        caller=MAIN/'references/apple-xnu/libkern/crypto/corecrypto_rsa.c'
        raw=git(MAIN/'references/apple-xnu','c54f35ca767986246321eb901baf8f5ff7923f6a:libkern/crypto/corecrypto_rsa.c')
        if hashlib.sha256(raw).hexdigest()!=sha(caller):raise ValueError('Actual selected caller is not pinned')
        # Linux sys/cdefs lacks Darwin's compiler enum macros. Extract the
        # genuine selected compiler-macro block,not replacement SDK records.
        cdefs_raw=git(MAIN/'references/apple-xnu','c54f35ca767986246321eb901baf8f5ff7923f6a:bsd/sys/cdefs.h')
        cdefs=cdefs_raw.decode();start=cdefs.index('#if __has_attribute(enum_extensibility)');end=cdefs.index('\n#if XNU_KERNEL_PRIVATE',start)
        host_macros=out/'host-compiler-macros.h';host_macros.write_text('/* Exact selected XNU BSD sys/cdefs compiler enum macros;host only. */\n'+cdefs[start:end]+'\n')
        report['host_compiler_macro_port']=dict(source='bsd/sys/cdefs.h',source_sha256=hashlib.sha256(cdefs_raw).hexdigest(),port_sha256=sha(host_macros),target_profile_uses_this_port=False)
        sources=[('adapter',HERE/'rsa.c'),('typed',HERE/'typed.c'),('caller',caller),('suite',HERE/'suite.c')]
        sources += [('bear-'+Path(name).stem,vendor/name) for name in prov['compiled_sources']]
        hflags=[*common,'--target=x86_64-unknown-linux-gnu','-include',host_macros,'-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-I'+str(MAIN/'references/apple-xnu/libkern'),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-DRSA_HOST']
        for name,src in sources:command([host,*hflags,'-MMD','-MF',out/('host-'+name+'.d'),'-c',src,'-o',out/('host-'+name+'.o')],'host-'+name)
        command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',*[out/('host-'+name+'.o') for name,_ in sources],xts_objects['host-adapter.o'],xts_objects['host-aes.o'],'-o',out/'host'],'host-link')
        command([out/'host'],'host-tests',120)
        text=(out/'host-tests.log').read_text();match=re.search(r'RSA HOST PASS vectors=(\d+) checks=(\d+) failure_line=0',text)
        if not match or int(match[1])!=corpus['total_count']:raise ValueError('Actual host verification marker mismatch')
        report['host_vectors']=int(match[1]);report['host_checks']=int(match[2])
        control=ROOT/'src/platform/crypto/xts/sanitizer_control.c'
        command([host,'--target=x86_64-unknown-linux-gnu','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',control,'-o',out/'sanitizer-control'],'sanitizer-control-build')
        report['sanitizer_controls']=[]
        for name,args_,marker in [('asan',['heap'],'AddressSanitizer: heap-buffer-overflow'),('ubsan',[],'runtime error: signed integer overflow')]:
            r=command([out/'sanitizer-control',*args_],'negative-'+name,expected=None);found=r['exit_code']!=0 and marker in (out/('negative-'+name+'.log')).read_text()
            report['sanitizer_controls'].append(dict(name=name,detected=found))
            if not found:raise ValueError('Actual sanitizer fault control undetected')
        command([host,'--target=x86_64-unknown-linux-gnu','-O1','-Wall','-Wextra','-Werror','-fno-builtin',HERE/'synthetic_mem.c',HERE/'synthetic_mem_test.c','-o',out/'checked-memory-test'],'checked-memory-build')
        command([out/'checked-memory-test'],'checked-memory-tests')
        if 'RSA CHECKED MEMSET PASS' not in (out/'checked-memory-tests.log').read_text():raise ValueError('Missing actual checked-fill controls')
        flags=list(recipe['argv'][1:])
        for key in ['-o','-MF']:
            i=flags.index(key);del flags[i:i+2]
        flags=[arg for arg in flags if not arg.startswith('-W') and arg not in ['-c','-MD','-MP','-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang',str(source)]]
        flags=['-I'+recipe['cwd'] if arg=='-I.' else arg for arg in flags]
        flags += [*common,'-isystem',str(MAIN/'references/xnu-tapi/src/clang/lib/Headers')]
        report['native_component_objects']=[]
        production=[item for item in sources if item[0] not in ['caller','suite']]
        for name,src in production:
            obj=out/('native-'+name+'.o');command([arm,*flags,'-MMD','-MF',out/('native-'+name+'.d'),'-c',src,'-o',obj],'native-'+name)
            report['native_component_objects'].append(dict(path=str(obj.relative_to(ROOT)),sha256=sha(obj),source=str(src),source_sha256=sha(src)))
        synthetic=[*flags,'-I'+str(ROOT/'fixtures/public/avf-handoff'),'-ffreestanding','-fno-pic','-fno-pie','-fno-stack-protector','-fno-jump-tables','-mstrict-align','-mgeneral-regs-only','-mno-outline-atomics']
        for name,src in [*sources,('memory',ROOT/'src/platform/crypto/xts/memory.c'),('checked-memory',HERE/'synthetic_mem.c'),('guest',HERE/'guest.c'),('spin',HERE/'guest.c')]:
            command([arm,*synthetic,*(['-DRSA_SPIN'] if name=='spin' else []),'-MMD','-MF',out/('cpu-'+name+'.d'),'-c',src,'-o',out/('cpu-'+name+'.o')],'cpu-'+name)
        sys.path.insert(0,str(ROOT/'tools/build'));from xnu_kernel_syscalls import ObjectData
        layout=ObjectData(out/'native-adapter.o').value('_s24_rsa_layout','<8Q');report['target_layout']=layout
        if tuple(layout)!=(1584,8,64,8,24,24,1568,24):raise ValueError('Genuine target container/macro layout mismatch')
        report['images']={}
        for mode,entry in [('normal','guest'),('spin','spin')]:
            target=out/(mode+'.macho')
            command([ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[out/('cpu-'+name+'.o') for name,_ in sources],out/'cpu-memory.o',out/'cpu-checked-memory.o',out/('cpu-'+entry+'.o'),xts_objects['arm-adapter.o'],xts_objects['arm-aes.o'],'-o',target],mode+'-link')
            report['images'][mode]=shared.avf.macho(target)
        report['dependency_hashes']={}
        for dep in out.glob('*.d'):
            for name in dep.read_text().replace('\\\n',' ').split(':',1)[1].split():
                path=Path(name).resolve();report['dependency_hashes'][str(path)]=sha(path)
        checked={}
        for name,digest_ in report['dependency_hashes'].items():
            if '/corecrypto/' in name and '/EXTERNAL_HEADERS/' in name:
                rel='EXTERNAL_HEADERS/'+name.split('/EXTERNAL_HEADERS/',1)[1]
                if rel not in checked:
                    if hashlib.sha256(git(MAIN/'references/apple-xnu','c54f35ca767986246321eb901baf8f5ff7923f6a:'+rel)).hexdigest()!=digest_:raise ValueError('Genuine complete selected header mismatch: '+rel)
                    checked[rel]=digest_
            path=Path(name)
            if path.is_relative_to(ROOT/'src/platform/crypto/xts'):
                rel=str(path.relative_to(ROOT))
                if xts['owned_source_hashes'].get(rel)!=digest_:raise ValueError('Accepted complete shared XTS dependency differs: '+rel)
        report['canonical_selected_headers']=checked
        report['stack_usage']={str(path.relative_to(ROOT)):path.read_text() for path in out.glob('*.su')}
        report['outcome']='pass'
    except Exception as error:report['error']=repr(error)
    finally:
        report['owned_source_hashes']={str(path.relative_to(ROOT)):sha(path) for path in HERE.rglob('*') if path.is_file() and '__pycache__' not in str(path)}
        report['shared_readonly_hashes']={str(path.relative_to(ROOT)):sha(path) for path in [ROOT/'src/platform/crypto/xts/check.py',ROOT/'src/platform/crypto/xts/memory.c',ROOT/'fixtures/public/avf-handoff/runtime.h']}
        report['memory_gate_observations']=GATE_OBSERVATIONS
        report['artifact_hashes']={str(path.relative_to(ROOT)):sha(path) for path in out.rglob('*') if path.is_file()}
        report['artifacts']=[str((ROOT/path).relative_to(MAIN)) for path in report['artifact_hashes']]
        report['sha256']={str((ROOT/path).relative_to(MAIN)):value for path,value in report['artifact_hashes'].items()}
        (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report.get(key) for key in ['outcome','error','host_vectors','host_checks','target_layout']},indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
