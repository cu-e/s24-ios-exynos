#!/usr/bin/env python3
"""Bounded actual explicit-nonce subset tests; complete table stays unqualified."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
OWNER='codex-team-crypto-chacha-20261105-bu'
PIN='c54f35ca767986246321eb901baf8f5ff7923f6a'
GUARDS={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
spec=importlib.util.spec_from_file_location('accepted_xts',MAIN/'src/platform/crypto/xts/check.py')
accepted=importlib.util.module_from_spec(spec);spec.loader.exec_module(accepted)
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def sources():return {str(p.relative_to(ROOT)):sha(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in str(p)}
def plan(experiment):
    state=MAIN/'state/lab.json';data=json.loads(state.read_text())
    task=next(x for x in data['tasks'] if x['id']=='KRN-034')
    row=next(x for x in data['experiments'] if x['id']==experiment)
    if task['owner']!=OWNER or task['status']!='in_progress' or row['owner']!=OWNER or row['task']!='KRN-034' or row['status']!='planned':
        raise ValueError('Matching current unrecorded canonical plan/claim required')
    if not (MAIN/row['procedure']).is_file():raise ValueError('Planned procedure absent')
    return dict(entry=row,entry_sha256=hashlib.sha256(json.dumps(row,sort_keys=True).encode()).hexdigest(),checked_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('--experiment',default='CHACHA-002');args=ap.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',args.run):raise ValueError('Fresh simple run name required')
    out=ROOT/'artifacts/crypto-chacha'/args.run;out.mkdir(parents=True,exist_ok=False)
    r=dict(task='KRN-034',kind='host-test',origin='local-host',outcome='inconclusive',supported_host_arm='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],complete_table_qualified=False,incnonce_supported=False,provider_registered=False,xnu_executed=False,native_device=False,guest_executed=False)
    def command(argv,name,expected=0,seconds=30):
        r['plan_before_last_child']=plan(args.experiment)
        mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        if mem<4*1024**3:raise ValueError('Memory guard: MemAvailable below4GiB, no child started')
        q=accepted.run(argv,out,name,seconds,256);q['MemAvailable_before_bytes']=mem;r['commands'].append(q)
        if expected is not None and (q['exit_code']!=expected or q['outcome'] in ['timeout','rss-limit']):raise ValueError(name+' failed')
        return q
    try:
        r['plan']=plan(args.experiment)
        r['commit']=subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'],env=dict(os.environ)|GUARDS,text=True).strip()
        r['commit_role']='Base; source snapshot/hash identifies actual uncommitted inputs'
        r['source_inputs']=sources()
        for name in r['source_inputs']:
            dest=out/'source-snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
        vendor=HERE/'vendor';provenance=json.loads((vendor/'provenance.json').read_text())
        for name,wanted in provenance['files'].items():
            if sha(vendor/name)!=wanted:raise ValueError('Vendor hash mismatch '+name)
        # Earlier acquisition was genuinely preplan after a failed procedure-path
        # submission; retain it as acquisition, never retrofit a planned test.
        r['preplan_acquisition']={'report':'worktrees/krn-034-20261105/artifacts/crypto-chacha/oracle-session1/report.json','started_at':'2026-11-05T18:15:49.041895+00:00','corrected_plan_created_at':'2026-11-05T18:17:40+00:00','deviation':'Independent corpus acquisition ran before corrected plan; all adapter execution below requires canonical planned entry'}
        rfc=ROOT/'artifacts/crypto-chacha/inputs/rfc8439.txt'
        command([sys.executable,HERE/'vectors.py',rfc,out/'regenerated'],'vectors-replay')
        for name in ['vectors.json','vectors.h']:
            if sha(out/'regenerated'/name)!=sha(HERE/'testdata'/name):raise ValueError('Primary/oracle corpus regeneration differs '+name)
        corpus=json.loads((out/'regenerated/vectors.json').read_text());r['vectors']={'count':len(corpus['vectors']),'primary_count':2,'oracle_count':57,'oracle':corpus['oracle'],'primary_sha256':corpus['primary_sha256']}
        # Import the single accepted zeroizer, through immutable accepted objects.
        depwt=MAIN/'worktrees/krn-029-20261105';dep=depwt/'artifacts/crypto-xts/final-commit2';dep_report=dep/'evidence.json'
        if sha(dep_report)!='c5064a512ba295d1cd447af1e73ac6fc4f9c0ffeaf5b78f09ca0f80fc1f6216c':raise ValueError('Accepted XTS report changed')
        accepted_report=json.loads(dep_report.read_text());r['imported_objects']={}
        for name in ['host-adapter.o','host-aes.o','arm-adapter.o','arm-aes.o','arm-memory.o']:
            p=dep/name;wanted=accepted_report['artifact_hashes'][str(p.relative_to(depwt))]
            if sha(p)!=wanted:raise ValueError('Accepted object changed '+name)
            r['imported_objects'][str(p)]=wanted
        r['accepted_xts_evidence']={'path':str(dep_report),'sha256':sha(dep_report),'purpose':'Single existing zeroizer; unrelated AES required by accepted XTS object linkage, no XTS provider registration'}
        host=Path('/home/egor/.local/bin/clang').resolve();reportpath=MAIN/'artifacts/xnu-kernel-declarations/controls-session1/report.json';original=json.loads(reportpath.read_text());source=MAIN/original['source_ports']['osfmk/mc_provider.o']['source'];recipe=next(q for q in original['commands'] if str(source) in q['argv'] and '-c' in q['argv']);arm=Path(recipe['argv'][0]);ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
        if sha(arm)!=original['compiler_sha256']:raise ValueError('Accepted target compiler changed')
        for name,argv in [('host-version',[host,'--version']),('host-resource',[host,'-print-resource-dir']),('arm-version',[arm,'--version']),('ld-version',[ld,'-v'])]:command(argv,name)
        rd=Path((out/'host-resource.log').read_text().strip());runtime={str(p):sha(p) for p in (rd/'lib/x86_64-unknown-linux-gnu').glob('*') if p.is_file() and ('asan' in p.name or 'ubsan' in p.name)}
        if not any(x.endswith('/libclang_rt.asan.a') for x in runtime):raise ValueError('Native ASan archive unavailable')
        r['tools']={'host':{'path':str(host),'sha256':sha(host),'native_runtime_hashes':runtime},'arm':{'path':str(arm),'sha256':sha(arm),'recipe':str(reportpath),'recipe_sha256':sha(reportpath)},'linker':{'path':str(ld),'sha256':sha(ld)},'accepted_supervisor':{'path':str(MAIN/'src/platform/crypto/xts/check.py'),'sha256':sha(MAIN/'src/platform/crypto/xts/check.py')}}
        common=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-I'+str(HERE),'-I'+str(vendor/'include'),'-I'+str(vendor/'library'),'-I'+str(out/'regenerated'),'-I'+str(MAIN/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu/libkern'),'-DMBEDTLS_CONFIG_FILE="s24_chacha_profile.h"']
        hf=[*common,'--target=x86_64-unknown-linux-gnu','-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-DCHACHA_HOST']
        units=[('adapter',HERE/'chacha.c'),('chacha',vendor/'library/chacha20.c'),('poly',vendor/'library/poly1305.c'),('suite',HERE/'suite.c')]
        for name,p in units:command([host,*hf,'-MMD','-MF',out/('host-'+name+'.d'),'-c',p,'-o',out/('host-'+name+'.o')],'host-'+name)
        command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',*[out/('host-'+name+'.o') for name,p in units],dep/'host-adapter.o',dep/'host-aes.o','-o',out/'host'],'host-link')
        command(['env','ASAN_OPTIONS=detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1',out/'host'],'host-tests')
        match=re.search(r'CHACHA HOST PASS vectors=(\d+) checks=(\d+) failure_line=0 incnonce=UNQUALIFIED',(out/'host-tests.log').read_text())
        if not match or int(match[1])!=59:raise ValueError('Supported host marker mismatch')
        r['host_checks']=int(match[2]);r['host_vectors']=int(match[1]);r['profile_rejections']=[]
        for option in ['MBEDTLS_CHACHA20_ALT','MBEDTLS_POLY1305_ALT','MBEDTLS_HAVE_ASM']:
            q=command([host,*hf,'-D'+option,'-c',HERE/'chacha.c','-o',out/('reject-'+option+'.o')],'reject-'+option,None)
            ok=q['exit_code']!=0 and q['outcome']=='fail' and 'Unqualified ChaCha/Poly1305 primitive profile' in (out/('reject-'+option+'.log')).read_text();r['profile_rejections'].append({'option':option,'rejected':ok})
            if not ok:raise ValueError('Unqualified profile accepted')
        command([host,'--target=x86_64-unknown-linux-gnu','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',HERE/'sanitizer_control.c','-o',out/'sanitizer-control'],'sanitizer-control-compile')
        r['sanitizer_controls']=[]
        for name,control_args,marker in [('asan-heap',['heap'],'AddressSanitizer: heap-buffer-overflow'),('ubsan-overflow',[],'runtime error: signed integer overflow')]:
            q=command([out/'sanitizer-control',*control_args],name,None);ok=q['exit_code']!=0 and q['outcome']=='fail' and marker in (out/(name+'.log')).read_text();r['sanitizer_controls'].append({'name':name,'detected':ok})
            if not ok:raise ValueError('Negative sanitizer failed '+name)
        flags=list(recipe['argv'][1:])
        for key in ['-o','-MF']:
            i=flags.index(key);del flags[i:i+2]
        flags=[x for x in flags if not x.startswith('-W') and x not in ['-c','-MD','-MP','-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang'] and x!=str(source)]
        flags=['-I'+recipe['cwd'] if x=='-I.' else x for x in flags]
        flags += [*common,'-isystem',str(MAIN/'references/xnu-tapi/src/clang/lib/Headers'),'-I'+str(MAIN/'fixtures/public/avf-handoff'),'-DS24_CHACHA_FREESTANDING','-ffreestanding','-fno-pic','-fno-pie','-fno-stack-protector','-fno-jump-tables','-mstrict-align','-mgeneral-regs-only','-mno-outline-atomics']
        for name,p in [*units,('functions',HERE/'functions.c'),('cpu-functions',HERE/'functions.c'),('guest',HERE/'guest.c'),('spin',HERE/'guest.c')]:
            command([arm,*flags,*(['-DCHACHA_CPU_FIXTURE'] if name in ['cpu-functions','guest','spin'] else []),*(['-DCHACHA_SPIN'] if name=='spin' else []),'-MMD','-MF',out/('arm-'+name+'.d'),'-c',p,'-o',out/('arm-'+name+'.o')],'arm-'+name)
        command([arm,*flags,'-S',HERE/'chacha.c','-o',out/'arm-adapter.s'],'arm-adapter-assembly')
        command([host,*hf,'-S',HERE/'chacha.c','-o',out/'host-adapter.s'],'host-adapter-assembly')
        r['dependency_hashes']={}
        for depfile in out.glob('*.d'):
            for name in depfile.read_text().replace('\\\n',' ').split(':',1)[1].split():
                p=Path(name).resolve();r['dependency_hashes'][str(p)]=sha(p)
        r['selected_source_checks']={}
        for name,digest in r['dependency_hashes'].items():
            if '/EXTERNAL_HEADERS/corecrypto/' in name:
                rel='EXTERNAL_HEADERS/'+name.split('/EXTERNAL_HEADERS/',1)[1]
                raw=subprocess.check_output(['git','-C',str(MAIN/'references/apple-xnu'),'show',PIN+':'+rel],env=dict(os.environ)|GUARDS,timeout=10)
                if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Selected primary header mismatch '+rel)
                r['selected_source_checks'][rel]=digest
        table=MAIN/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu/libkern/libkern/crypto/register_crypto.h';raw=subprocess.check_output(['git','-C',str(MAIN/'references/apple-xnu'),'show',PIN+':libkern/libkern/crypto/register_crypto.h'],env=dict(os.environ)|GUARDS,timeout=10)
        if hashlib.sha256(raw).hexdigest()!=sha(table):raise ValueError('Genuine table header mismatch')
        r['selected_source_checks']['libkern/libkern/crypto/register_crypto.h']=sha(table)
        sys.path.insert(0,str(MAIN/'tools/build'));from xnu_kernel_syscalls import ObjectData
        r['target_layout']=ObjectData(out/'arm-adapter.o').value('_s24_chacha_layout','<6Q');r['table_layout']=ObjectData(out/'arm-functions.o').value('_s24_chacha_table_layout','<2Q')
        if tuple(r['target_layout'])!=(256,8,256,8,136,80) or tuple(r['table_layout'])!=(80,8):raise ValueError('Actual target layout mismatch')
        table_object=ObjectData(out/'arm-functions.o');r['typed_method_relocations']=[]
        for i,name in enumerate(['info','init','reset','setnonce','incnonce','aad','encrypt','finalize','decrypt','verify']):
            relocation=table_object.relocation('_functions',i*8)
            if relocation['name']!='_s24_chacha_'+name or relocation['addend']!=0:raise ValueError('Actual typed table method binding mismatch')
            r['typed_method_relocations'].append(relocation)
        for mode,last in [('normal','guest'),('spin','spin')]:
            command([ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[out/('arm-'+n+'.o') for n in ['adapter','chacha','poly','suite','cpu-functions',last]],dep/'arm-adapter.o',dep/'arm-aes.o',dep/'arm-memory.o','-o',out/(mode+'.macho')],mode+'-link')
        r['images']={mode:accepted.avf.macho(out/(mode+'.macho')) for mode in ['normal','spin']}
        nm=host.parent/'llvm-nm';r['tools']['nm']={'path':str(nm),'sha256':sha(nm)}
        command([nm,'--defined-only',out/'normal.macho'],'arm-defined-symbols')
        command([nm,'--defined-only',out/'host'],'host-defined-symbols')
        for arch in ['arm','host']:
            definitions=(out/(arch+'-defined-symbols.log')).read_text().splitlines()
            if sum(line.split()[-1] in ['_mbedtls_platform_zeroize','mbedtls_platform_zeroize'] for line in definitions if line.split())!=1:raise ValueError('Single imported zeroizer required')
        import addresses
        r['linked_runtime_address_proof']=addresses.prove(out/'normal.macho',(out/'arm-defined-symbols.log').read_text(),r['images']['normal'])
        r['supported_host_arm']='pass';r['summary']='Supported explicit-nonce subset host tests and genuine ARM compilation passed; CPU runtime pending separate lease and incnonce contract still unavailable'
    except Exception as error:r['error']=repr(error)
    finally:
        r['artifacts']=[str(p.relative_to(MAIN)) for p in out.rglob('*') if p.is_file()];r['sha256']={str(p.relative_to(MAIN)):sha(p) for p in out.rglob('*') if p.is_file()}
        r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps({k:r.get(k) for k in ['outcome','supported_host_arm','error','host_vectors','host_checks','target_layout','table_layout']}));return r['supported_host_arm']!='pass'
if __name__=='__main__':raise SystemExit(main())
