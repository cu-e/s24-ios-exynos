#!/usr/bin/env python3
"""Execute frozen RSA payload only with an explicit coordinator QEMU lease."""
import argparse,datetime,hashlib,json,re,sys,time
from pathlib import Path
import check
HERE=check.HERE;ROOT=check.ROOT;MAIN=check.MAIN;avf=check.shared.avf
def sha(path):return check.sha(path)
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--build',type=Path,required=True);p.add_argument('--lease-id',required=True);args=p.parse_args()
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',args.run) or not args.lease_id.strip():raise ValueError('Fresh run and actual coordinator lease required')
    out=ROOT/'artifacts/crypto-rsa'/args.run;out.mkdir(parents=True,exist_ok=False)
    report=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],guest_cases=[],lease_id=args.lease_id,guest_memory_mib=256,summary='Real RSA component on accepted unchanged AVF/QEMU virtual CPU;not XNU,phone,private ABI or registered crypto',provider_registered=False,native_device=False,XNU_executed=False,private_ABI=False)
    started=time.monotonic();admission_total=0
    def command(argv,name,seconds):
        nonlocal admission_total
        before=time.monotonic();stable=0;samples=[]
        while stable<3:
            memory=int(re.search(r'^MemAvailable:\s*(\d+)',Path('/proc/meminfo').read_text(),re.M)[1])*1024
            samples.append(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),MemAvailable_bytes=memory))
            stable=stable+1 if memory>=4*1024**3 else 0
            waited=time.monotonic()-before
            if waited>45 or admission_total+waited>180:raise RuntimeError('Finite QEMU resource admission deferred;no next guest started')
            if stable<3:time.sleep(1)
        admission_total+=time.monotonic()-before
        if time.monotonic()-started+seconds>360:raise RuntimeError('Conservative whole-lease deadline prevents next guest')
        r=check.shared.run(argv,out,name,seconds,512);r['admission_samples']=samples;r['MemAvailable_before_bytes']=memory;report['commands'].append(r);return r
    try:
        build_path=args.build.resolve();build=json.loads(build_path.read_text());build_dir=build_path.parent;build_root=build_dir.parents[2]
        if build['outcome']!='pass' or build.get('host_vectors')!=491:raise ValueError('Qualified frozen build required')
        report['build_capsule']=dict(path=str(build_path.relative_to(MAIN)),sha256=sha(build_path))
        for name,digest in build['artifact_hashes'].items():
            if sha(build_root/name)!=digest:raise ValueError('Frozen image/build bytes changed: '+name)
        for name,digest in build['owned_source_hashes'].items():
            if Path(name).suffix in ['.c','.h'] and sha(ROOT/name)!=digest:raise ValueError('Frozen compiled source differs: '+name)
        qualified=json.loads((ROOT/'docs/procedures/crypto-xts/qualified-evidence.json').read_text());qp=MAIN/qualified['report']
        if sha(qp)!=qualified['report_sha256']:raise ValueError('Accepted unchanged AVF qualification differs')
        prior=json.loads(qp.read_text());inputs=prior['avf_inputs']
        qemu=Path(inputs['qemu']);shim=Path(inputs['shim'])
        if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Accepted QEMU/shim bytes changed')
        for name,digest in inputs['reports'].items():
            if sha(name)!=digest:raise ValueError('Immutable AVF input report differs')
        if sha(ROOT/'tools/verify/avf_handoff.py')!=inputs['qualified_helpers_sha256'] or sha(ROOT/'tools/build/qemu_host.py')!=inputs['supervisor_sha256']:raise ValueError('Accepted source/helper profile differs')
        if sha(ROOT/'fixtures/public/avf-handoff/runtime.h')!=qualified['owned_source_hashes']['fixtures/public/avf-handoff/runtime.h']:raise ValueError('Shared runtime changed')
        report['avf_inputs']=inputs
        corpus=json.loads((HERE/'testdata/vectors.json').read_text());first=next(row for row in corpus['rows'] if row['expected']);pattern=bytes.fromhex(first['signature'])
        base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot']
        for name,mode,cookie in [('positive','normal','xts_cookie=owned-adapter-v1'),('wrong-cookie','normal','xts_cookie=wrong'),('corrupt-signature','normal','xts_cookie=owned-adapter-v1'),('spin-timeout','spin','xts_cookie=owned-adapter-v1')]:
            kernel=bytearray((build_dir/(mode+'.macho')).read_bytes())
            if name=='corrupt-signature':
                if kernel.count(pattern)!=1:raise ValueError('Positive signature must identify one actual guest vector')
                offset=kernel.index(pattern);kernel[offset]^=1;report['corrupt_control']=dict(offset=offset,mutation='xor1 first signature byte of actual positive vector',original_signature_sha256=hashlib.sha256(pattern).hexdigest())
            payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie)
            argv=[*base,'-initrd',payload];r=command(argv,name,3 if mode=='spin' else 20 if name=='wrong-cookie' else 90)
            console=(out/(name+'.log')).read_text(errors='replace');passed='RSA ARM PASS' in console
            if name=='positive':
                marker=re.search(r'RSA ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0 stack_used=(0x[0-9a-f]+)',console)
                entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
                ok=bool(marker and entry) and r['outcome']=='pass' and 'XTS SYNTHETIC HANDOFF VERIFIED' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
                if marker:
                    report['arm_checks']=int(marker[1],16);report['observed_stack_bytes']=int(marker[2],16)
                    ok=ok and report['arm_checks']==build['host_checks'] and report['observed_stack_bytes']<=32768
                if entry:ok=ok and int(entry[1],16)==build['images'][mode]['entry_pa'] and int(entry[2],16)==build['images'][mode]['bootargs_pa']
            elif name=='wrong-cookie':ok=not passed and 'XTS SYNTHETIC REJECT command-cookie' in console and r['outcome']=='pass'
            elif name=='corrupt-signature':ok=not passed and 'RSA ARM FAIL' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console and r['outcome']=='pass'
            else:ok=not passed and 'RSA SYNTHETIC SPIN-CONTROL' in console and r['outcome']=='timeout'
            report['guest_cases'].append(dict(name=name,accepted=bool(ok),payload_sha256=sha(payload),console_sha256=sha(out/(name+'.log'))))
            if not ok:raise ValueError('Actual guest case failed: '+name)
        if sha(qemu)!=avf.PIN['qemu_sha256'] or sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Immutable guest inputs changed')
        report['outcome']='pass'
    except Exception as error:report['error']=repr(error)
    report['owned_source_hashes']={str(p.relative_to(ROOT)):sha(p) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in str(p)}
    report['admission_seconds']=admission_total;report['elapsed_seconds']=time.monotonic()-started
    report['artifact_hashes']={str(p.relative_to(ROOT)):sha(p) for p in out.rglob('*') if p.is_file()}
    report['artifacts']=[str((ROOT/name).relative_to(MAIN)) for name in report['artifact_hashes']]
    report['sha256']={str((ROOT/name).relative_to(MAIN)):digest for name,digest in report['artifact_hashes'].items()}
    (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report.get(key) for key in ['outcome','error','arm_checks','observed_stack_bytes','guest_cases']},indent=2));return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
