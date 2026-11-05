#!/usr/bin/env python3
"""Bounded real host/ARM XTS qualification; never registers a crypto provider."""
import argparse,datetime,hashlib,importlib.util,json,os,re,resource,subprocess,sys,time,zipfile
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
GIT_GUARDS={'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}
CHILD_ENV=dict(os.environ)|GIT_GUARDS
spec=importlib.util.spec_from_file_location('qualified_avf',ROOT/'tools/verify/avf_handoff.py')
avf=importlib.util.module_from_spec(spec);spec.loader.exec_module(avf)
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
# Process-session monitoring/cleanup derives from accepted VM-005. This owner
# deliberately uses RSS only: lld and ASan reserve large sparse virtual regions.
def run(argv, out, name, seconds=5, limit_mib=512):
    start = time.monotonic()
    record = {"argv": [str(x) for x in argv], "started_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "timeout_seconds": seconds, "rss_budget_mib": limit_mib, "outcome": "fail",
              "environment_overrides": GIT_GUARDS}

    def limits():
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    with (out / (name + ".log")).open("xb") as log, (out / (name + ".samples.jsonl")).open("x") as samples:
        proc = subprocess.Popen(record["argv"], cwd=ROOT, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT,
                                start_new_session=True, preexec_fn=limits, env=CHILD_ENV)
        record["owned_session"] = proc.pid
        peak = 0
        try:
            while proc.poll() is None:
                snap = avf.supervisor.sample(proc.pid)
                own_rss = int(Path("/proc/self/statm").read_text().split()[1]) * resource.getpagesize()
                snap["supervisor_rss_bytes"] = own_rss
                snap["total_owned_rss_bytes"] = own_rss + snap["owned_tree_rss_bytes"]
                peak = max(peak, snap["total_owned_rss_bytes"])
                samples.write(json.dumps(snap) + "\n"); samples.flush()
                if peak > limit_mib * 1024**2:
                    record["outcome"] = "rss-limit"
                    avf.supervisor.terminate(proc)
                    break
                if time.monotonic() - start >= seconds:
                    record["outcome"] = "timeout"
                    avf.supervisor.terminate(proc)
                    break
                time.sleep(0.05)
            record["exit_code"] = proc.wait(timeout=2)
            if record["outcome"] == "fail" and record["exit_code"] == 0:
                record["outcome"] = "pass"
        finally:
            if any(p["state"] != "Z" for p in avf.supervisor.sample(proc.pid)["owned_processes"]):
                avf.supervisor.terminate(proc)
            until = time.monotonic() + 2
            after = avf.supervisor.sample(proc.pid)
            while any(p["state"] != "Z" for p in after["owned_processes"]) and time.monotonic() < until:
                time.sleep(0.02); after = avf.supervisor.sample(proc.pid)
            record.update(elapsed_seconds=round(time.monotonic() - start, 3),
                          peak_total_owned_rss_bytes=peak, cumulative_children_ru_maxrss_KiB=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss, after=after)
            (out / (name + ".json")).write_text(json.dumps(record, indent=2) + "\n")
            if any(p["state"] != "Z" for p in after["owned_processes"]):
                raise RuntimeError("Live owned fixture child survived cleanup")
    return record


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--run',required=True);ap.add_argument('--nist-archive',type=Path,required=True);args=ap.parse_args()
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*',args.run):raise ValueError('fresh simple run name required')
    out=ROOT/'artifacts/crypto-xts'/args.run;out.mkdir(parents=True,exist_ok=False)
    report={'task':'KRN-029','kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':sys.argv,'commands':[],'source_reads':[],'environment_overrides':GIT_GUARDS,'xnu_executed':False,'native_device':False,'provider_registered':False}
    def command(argv,name,seconds=20,budget=256,expected=0):
        r=run(argv,out,name,seconds,budget);report['commands'].append(r)
        if expected is not None and r['exit_code']!=expected:raise ValueError(name+' exit: '+str(r['exit_code']))
        if r['outcome'] in ['rss-limit','timeout'] and expected is not None:raise ValueError(name+' '+r['outcome'])
        return r
    def git(repo,spec):
        argv=['git','-C',str(repo),'show',spec]
        p=subprocess.run(argv,env=CHILD_ENV,capture_output=True,timeout=10)
        report['source_reads'].append({'argv':argv,'exit_code':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout).hexdigest(),'stderr':p.stderr.decode(errors='replace'),'environment_overrides':GIT_GUARDS})
        if p.returncode:raise ValueError('pinned Git object unavailable without lazy fetch')
        return p.stdout
    try:
        p=subprocess.run(['git','-C',str(ROOT),'rev-parse','HEAD'],env=CHILD_ENV,capture_output=True,text=True,check=True,timeout=10);report['commit']=p.stdout.strip()
        p=subprocess.run(['git','-C',str(ROOT),'status','--porcelain','--untracked-files=all','--','src/platform/crypto/xts','docs/procedures/crypto-xts','fixtures/public/avf-handoff/runtime.h'],env=CHILD_ENV,capture_output=True,text=True,check=True,timeout=10);report['owned_dirty_at_start']=p.stdout
        vendor=HERE/'vendor';prov=json.loads((vendor/'provenance.json').read_text())
        for name,wanted in prov['files'].items():
            if digest(vendor/name)!=wanted:raise ValueError('vendor hash: '+name)
        corpus=json.loads((HERE/'testdata/vectors.json').read_text())
        if digest(args.nist_archive)!=corpus['archive_sha256']:raise ValueError('primary NIST archive hash')
        with zipfile.ZipFile(args.nist_archive) as z:
            for name,wanted in corpus['files'].items():
                if hashlib.sha256(z.read(name)).hexdigest()!=wanted:raise ValueError('primary NIST file hash')
        if digest(corpus['oracle']['path'])!=corpus['oracle']['sha256']:raise ValueError('independent oracle binary changed')
        command([sys.executable,HERE/'vectors.py',args.nist_archive,out/'regenerated'],'vectors-replay')
        for name in ['vectors.json','vectors.h']:
            if digest(out/'regenerated'/name)!=digest(HERE/'testdata'/name):raise ValueError('corpus/oracle regeneration differs: '+name)
        report['vectors']={k:corpus[k] for k in ['nist_count','oracle_extra_count','archive_sha256','oracle']}
        report['vectors']['excluded_records']=sum(x.get('count',1) if isinstance(x.get('count',1),int) else 1 for x in corpus['excluded'])
        host=Path('/home/egor/.local/bin/clang').resolve();original_path=MAIN/'artifacts/xnu-kernel-declarations/controls-session1/report.json';original=json.loads(original_path.read_text())
        source=MAIN/original['source_ports']['osfmk/mc_provider.o']['source'];recipe=next(r for r in original['commands'] if str(source) in r['argv'] and '-c'in r['argv']);arm=Path(recipe['argv'][0]);ld=MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-ld'
        if digest(arm)!=original['compiler_sha256']:raise ValueError('qualified ARM compiler changed')
        for name,argv in [('host-version',[host,'--version']),('host-resource',[host,'-print-resource-dir']),('arm-version',[arm,'--version']),('arm-resource',[arm,'-print-resource-dir']),('linker-version',[ld,'-v'])]:command(argv,name)
        resource_dir=Path((out/'host-resource.log').read_text().strip())
        runtimes={str(p):digest(p) for p in sorted((resource_dir/'lib/x86_64-unknown-linux-gnu').glob('*')) if p.is_file() and ('asan' in p.name or 'ubsan' in p.name)}
        if not any(p.endswith('/libclang_rt.asan.a') for p in runtimes):raise ValueError('actual host ASan archive missing')
        command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-###',HERE/'sanitizer_control.c','-o',out/'dry-run'],'host-sanitizer-expanded-link')
        report['tools']={'host':{'path':str(host),'sha256':digest(host),'resource_dir':str(resource_dir),'runtime_hashes':runtimes},'arm':{'path':str(arm),'sha256':digest(arm),'recipe_report':str(original_path),'recipe_report_sha256':digest(original_path),'target':'arm64-apple-ios16.5, general registers only, no outline atomics'},'ld':{'path':str(ld),'sha256':digest(ld)}}
        common=['-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-I'+str(HERE),'-I'+str(vendor/'include'),'-I'+str(vendor/'library'),'-I'+str(out/'regenerated'),'-DMBEDTLS_CONFIG_FILE="s24_xts_profile.h"']
        hflags=[*common,'--target=x86_64-unknown-linux-gnu','-I'+str(MAIN/'references/apple-xnu/EXTERNAL_HEADERS'),'-fsanitize=address,undefined','-fno-sanitize-recover=all','-DXTS_HOST']
        for name,src in [('adapter',HERE/'xts.c'),('aes',vendor/'library/aes.c'),('suite',HERE/'suite.c')]:
            command([host,*hflags,'-MMD','-MF',out/('host-'+name+'.d'),'-c',src,'-o',out/('host-'+name+'.o')],'host-'+name)
        command([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',*[out/('host-'+n+'.o') for n in ['adapter','aes','suite']],'-o',out/'host'],'host-link')
        command([out/'host'],'host-tests',30,512)
        console=(out/'host-tests.log').read_text();match=re.search(r'XTS HOST PASS vectors=(\d+) checks=(\d+) failure_line=0',console)
        if not match or int(match[1])!=len(corpus['vectors']):raise ValueError('host algorithm marker mismatch')
        report['host_checks']=int(match[2]);report['host_vectors']=int(match[1])
        report['profile_rejections']=[]
        for option in ['MBEDTLS_AES_ALT','MBEDTLS_AESNI_C','MBEDTLS_AESCE_C','MBEDTLS_HAVE_ASM']:
            r=command([host,*hflags,'-D'+option,'-c',HERE/'xts.c','-o',out/('reject-'+option+'.o')],'reject-'+option,20,256,None)
            ok=r['exit_code']!=0 and 'Unqualified AES profile' in (out/('reject-'+option+'.log')).read_text()
            report['profile_rejections'].append({'macro':option,'rejected':ok})
            if not ok:raise ValueError('unqualified profile accepted')
        command([host,'--target=x86_64-unknown-linux-gnu','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1',HERE/'sanitizer_control.c','-o',out/'sanitizer-control'],'sanitizer-control-compile')
        report['sanitizer_controls']=[]
        for name,extra,marker in [('asan-heap',['heap'],'AddressSanitizer: heap-buffer-overflow'),('ubsan-overflow',[],'runtime error: signed integer overflow')]:
            r=command([out/'sanitizer-control',*extra],name,10,512,None);text=(out/(name+'.log')).read_text()
            ok=r['exit_code']!=0 and r['outcome']=='fail' and marker in text
            report['sanitizer_controls'].append({'name':name,'detected':ok})
            if not ok:raise ValueError('real sanitizer negative did not trigger: '+name)
        flags=list(recipe['argv'][1:])
        for key in ['-o','-MF']:
            i=flags.index(key);del flags[i:i+2]
        flags=[x for x in flags if not x.startswith('-W') and x not in ['-c','-MD','-MP','-enable-trivial-auto-var-init-zero-knowing-it-will-be-removed-from-clang'] and x!=str(source)]
        flags=['-I'+recipe['cwd'] if x=='-I.' else x for x in flags]
        flags += [*common,'-isystem',str(MAIN/'references/xnu-tapi/src/clang/lib/Headers'),'-I'+str(ROOT/'fixtures/public/avf-handoff'),'-DS24_XTS_FREESTANDING','-ffreestanding','-fno-pic','-fno-pie','-fno-stack-protector','-fno-jump-tables','-mstrict-align','-mgeneral-regs-only','-mno-outline-atomics']
        for name,src in [('adapter',HERE/'xts.c'),('aes',vendor/'library/aes.c'),('suite',HERE/'suite.c'),('memory',HERE/'memory.c'),('guest',HERE/'guest.c'),('spin',HERE/'guest.c')]:
            command([arm,*flags,*(['-DXTS_SPIN'] if name=='spin' else []),'-MMD','-MF',out/('arm-'+name+'.d'),'-c',src,'-o',out/('arm-'+name+'.o')],'arm-'+name)
        report['dependency_hashes']={}
        for dep in sorted(out.glob('*.d')):
            paths=dep.read_text().replace('\\\n',' ').split(':',1)[1].split()
            for name in paths:
                p=Path(name).resolve();report['dependency_hashes'][str(p)]=digest(p)
        report['selected_source_checks']={}
        checked=set()
        for name,sha in report['dependency_hashes'].items():
            p=Path(name)
            if '/corecrypto/' in name and '/EXTERNAL_HEADERS/' in name:
                rel='EXTERNAL_HEADERS/'+name.split('/EXTERNAL_HEADERS/',1)[1]
                if rel not in checked:
                    raw=git(MAIN/'references/apple-xnu','c54f35ca767986246321eb901baf8f5ff7923f6a:'+rel)
                    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('actual selected XNU header differs: '+rel)
                    checked.add(rel);report['selected_source_checks'][rel]=sha
            if p.is_relative_to(MAIN/'references/xnu-tapi/src/clang/lib/Headers'):
                rel=str(p.relative_to(MAIN/'references/xnu-tapi'))
                raw=git(MAIN/'references/xnu-tapi','fa9443738c1a18accef4244732ec6d6ee97a8133:'+rel)
                if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('genuine Clang header differs')
        for mode,last in [('normal','guest'),('spin','spin')]:
            command([ld,'-arch','arm64','-static','-e','_xts_entry','-iphoneos_version_min','16.5','-pagezero_size','0','-seg1addr','0xfffffff007000000','-no_uuid',*[out/('arm-'+n+'.o') for n in ['adapter','aes','suite','memory',last]],'-o',out/(mode+'.macho')],mode+'-link')
        sys.path.insert(0,str(ROOT/'tools/build'));from xnu_kernel_syscalls import ObjectData
        layout=ObjectData(out/'arm-adapter.o').value('_s24_xts_layout','<6Q')
        report['target_layout']=dict(zip(['key_bytes','key_alignment','tweak_bytes','tweak_alignment','mbedtls_aes_bytes','ccmode_xts_bytes'],layout))
        if not(layout[0]<=1072 and layout[1]==16 and layout[3]==16 and layout[5]==80):raise ValueError('genuine target context fit')
        images={mode:avf.macho(out/(mode+'.macho')) for mode in ['normal','spin']};report['images']=images
        vm2=MAIN/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105';vm4=MAIN/'worktrees/vm-004-20261105/artifacts/qemu-host';qemu=vm4/'build-6/build/qemu-system-aarch64';shim=vm2/'Image'
        if digest(qemu)!=avf.PIN['qemu_sha256'] or digest(shim)!=avf.PIN['shim_sha256']:raise ValueError('qualified unchanged QEMU/shim hashes')
        sbpath=vm2/'report.json';qbpath=vm4/'build-6/build-report.json';qmpath=vm4/'release-10.2.0/source-manifest.json'
        sb=json.loads(sbpath.read_text());qb=json.loads(qbpath.read_text());qm=json.loads(qmpath.read_text())
        if sb['donor_commit']!=avf.PIN['scion_commit'] or qb['pin']['commit']!=avf.PIN['qemu_commit'] or qb['binary_sha256']!=avf.PIN['qemu_sha256'] or not any(x['sha256']==avf.PIN['shim_sha256'] for x in sb['artifacts']):raise ValueError('build report bindings')
        source_hashes={}
        for row in sb['sources']:
            raw=git(MAIN/'references/scion-avf',avf.PIN['scion_commit']+':'+row['path']);sha=hashlib.sha256(raw).hexdigest()
            if sha!=row['sha256']:raise ValueError('shim source differs')
            source_hashes[row['path']]=sha
        raw=git(MAIN/'references/scion-avf',avf.PIN['scion_commit']+':xnuloader/mkpayload.py');source_hashes['xnuloader/mkpayload.py']=hashlib.sha256(raw).hexdigest()
        for name in ['hw/arm/virt.c','hw/arm/boot.c','target/arm/tcg/psci.c']:
            sha=digest(vm4/'release-10.2.0/source/qemu-10.2.0'/name)
            if sha!=qm[name]['sha256']:raise ValueError('QEMU source differs')
            source_hashes['qemu/'+name]=sha
        report['avf_inputs']={'pin':avf.PIN,'qemu':str(qemu),'shim':str(shim),'source_hashes':source_hashes,'reports':{str(p):digest(p) for p in [sbpath,qbpath,qmpath]},'supervisor_sha256':digest(ROOT/'tools/build/qemu_host.py'),'qualified_helpers_sha256':digest(ROOT/'tools/verify/avf_handoff.py')}
        base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot']
        report['guest_cases']=[]
        for name,mode,cookie in [('positive','normal','xts_cookie=owned-adapter-v1'),('wrong-cookie','normal','xts_cookie=wrong'),('corrupt-vector','normal','xts_cookie=owned-adapter-v1'),('spin-timeout','spin','xts_cookie=owned-adapter-v1')]:
            kernel=bytearray((out/(mode+'.macho')).read_bytes())
            if name=='corrupt-vector':
                pattern=bytes.fromhex(corpus['vectors'][0]['ct'])
                if kernel.count(pattern)!=1:raise ValueError('negative vector pattern must be unique in actual guest bytes')
                offset=kernel.index(pattern);kernel[offset]^=1
                report['corrupt_vector_control']={'offset':offset,'original_expected':pattern.hex(),'mutation':'xor1 first expected-ciphertext byte in own MachO vector blob'}
            payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie)
            argv=[*base,'-initrd',payload]
            if name=='positive':
                dtb=out/'qemu.dtb';dump=list(argv);dump[2]+=',dumpdtb='+str(dtb)
                command(dump,'dtb-dump',5,512);report['qemu_dtb']=avf.fdt(dtb)
            r=command(argv,name,3 if mode=='spin' else 30,512,None)
            console=(out/(name+'.log')).read_text(errors='replace');passed='XTS ARM PASS' in console
            if name=='positive':
                m=re.search(r'XTS ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0',console)
                entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
                ok=bool(m and entry) and int(entry[1],16)==images[mode]['entry_pa'] and int(entry[2],16)==images[mode]['bootargs_pa'] and r['outcome']=='pass' and 'XTS SYNTHETIC HANDOFF VERIFIED' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
                if m:
                    report['arm_checks']=int(m[1],16)
                    ok=ok and report['arm_checks']==report['host_checks']-5
            elif name=='wrong-cookie':ok=not passed and 'XTS SYNTHETIC REJECT command-cookie' in console and r['outcome']=='pass'
            elif name=='corrupt-vector':ok=not passed and 'XTS ARM FAIL' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console and r['outcome']=='pass'
            else:ok=not passed and 'XTS SYNTHETIC SPIN-CONTROL' in console and r['outcome']=='timeout'
            report['guest_cases'].append({'name':name,'accepted':ok,'payload_sha256':digest(payload),'console_sha256':digest(out/(name+'.log'))})
            if not ok:raise ValueError('guest control failure: '+name)
        if digest(qemu)!=avf.PIN['qemu_sha256'] or digest(shim)!=avf.PIN['shim_sha256']:raise ValueError('shared immutable input changed')
        report['outcome']='pass'
        report['summary']='Genuine typed full-block XTS descriptors:1200 NIST records+20 independent OpenSSL records, real sanitized host and unchanged AVF/QEMU ARM CPU execution; no provider/XNU/native/private ABI/FIPS/side-channel qualification'
    except Exception as error:report['error']=repr(error)
    finally:
        report['owned_source_hashes']={str(p.relative_to(ROOT)):digest(p) for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in str(p)}
        runtime=ROOT/'fixtures/public/avf-handoff/runtime.h';report['owned_source_hashes'][str(runtime.relative_to(ROOT))]=digest(runtime)
        report['artifact_hashes']={str(p.relative_to(ROOT)):digest(p) for p in sorted(out.rglob('*')) if p.is_file()}
        report['artifacts']=list(report['artifact_hashes'])
        report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','error','commit','host_vectors','host_checks','arm_checks','target_layout','guest_cases']},indent=2))
    return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
