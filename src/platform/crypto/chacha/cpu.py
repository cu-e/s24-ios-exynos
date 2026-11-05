#!/usr/bin/env python3
"""Execute already-built actual typed ARM fixture with an explicit root lease."""
import argparse,datetime,json,re,sys,time,shutil,hashlib
from pathlib import Path
import check
class ResourceDeferred(Exception):pass
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--from-run',required=True);ap.add_argument('--run',required=True);ap.add_argument('--lease',required=True);ap.add_argument('--experiment',default='CHACHA-003');args=ap.parse_args()
    for name in [args.run,args.from_run]:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*',name):raise ValueError('Simple fresh run names required')
    root,main=check.ROOT,check.MAIN;source=root/'artifacts/crypto-chacha'/args.from_run
    out=root/'artifacts/crypto-chacha'/args.run;out.mkdir(parents=True,exist_ok=False)
    report=dict(task='KRN-034',kind='host-test',origin='local-host',outcome='inconclusive',supported_cpu='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],complete_table_qualified=False,incnonce_supported=False,provider_registered=False,native_device=False,xnu_executed=False,root_lease=args.lease)
    report['summary']='Actual typed ARM explicit-nonce fixture attempt; supported CPU outcome recorded separately and full nonce compatibility remains incomplete'
    report['resource_admission']={'policy':'Three consecutive MemAvailable>=4GiB samples1s apart; at most45s/command and180s total admission waits; no child below floor','floor_bytes':4*1024**3,'per_command_wait_seconds':45,'total_wait_budget_seconds':180,'waits':[]}
    waited=0.0
    def admit(name):
        nonlocal waited
        begin=time.monotonic();deadline=begin+min(45.0,max(0.0,180.0-waited));streak=0
        row={'command':name,'samples':[],'admitted':False}
        report['resource_admission']['waits'].append(row)
        while time.monotonic()<deadline:
            mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
            row['samples'].append({'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'MemAvailable_bytes':mem})
            streak=streak+1 if mem>=4*1024**3 else 0
            if streak>=3:row['admitted']=True;break
            time.sleep(min(1.0,max(0.0,deadline-time.monotonic())))
        elapsed=time.monotonic()-begin;waited+=elapsed
        row.update(waited_seconds=elapsed,total_waited_seconds=waited)
        if not row['admitted']:raise ResourceDeferred('Stable resource floor unavailable: '+name+'; no child started')
        return row['samples'][-1]['MemAvailable_bytes']
    def command(argv,name,seconds=30,expected=0):
        report['plan_before_last_child']=check.plan(args.experiment)
        admit(name)
        report['plan_before_last_child']=check.plan(args.experiment)
        mem=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))*1024
        if mem<4*1024**3:raise ResourceDeferred('Final resource floor fell below4GiB; no child started')
        # Exclusive single256MiB guest, bounded process+supervisor RSS512MiB.
        q=check.accepted.run(argv,out,name,seconds,512);q['MemAvailable_before_bytes']=mem;report['commands'].append(q)
        if expected is not None and (q['exit_code']!=expected or q['outcome'] in ['timeout','rss-limit']):raise ValueError(name+' failed')
        return q
    try:
        report['plan']=check.plan(args.experiment)
        oldpath=source/'evidence.json';old=json.loads(oldpath.read_text())
        if old.get('supported_host_arm')!='pass':raise ValueError('Qualified supported host/ARM inputs required')
        report['input_report']={'path':str(oldpath.relative_to(main)),'sha256':check.sha(oldpath)}
        report['commit']=old['commit'];report['commit_role']=old['commit_role'];report['source_inputs']=old['source_inputs']
        for name,wanted in old['source_inputs'].items():
            actual=check.sha(root/name)
            if actual!=wanted:
                # Root-authorized admission-only runner change; all compiled
                # sources and table/runtime inputs must remain byte-identical.
                if name!='src/platform/crypto/chacha/cpu.py':raise ValueError('Source changed since qualified compile '+name)
                report['cpu_runner_delta']={'path':name,'compiled_report_sha256':wanted,'execution_sha256':actual,'reason':'Coordinator-authorized CPU-runner-only stable admission wait; not a changed compiler input'}
        runner=Path(__file__).resolve();shutil.copyfile(runner,out/'actual-cpu-runner.py');report['actual_runner_sha256']=check.sha(runner)
        for name,wanted in old['sha256'].items():
            if check.sha(main/name)!=wanted:raise ValueError('Built capsule changed '+name)
        for name,wanted in old['imported_objects'].items():
            if check.sha(name)!=wanted:raise ValueError('Imported object changed '+name)
        runtime=main/'fixtures/public/avf-handoff/runtime.h'
        if check.sha(runtime)!='0d85cbf3acec7858458bcb086ff23a5ab8a61eefb5ce47d4d75fbf01cf728087':raise ValueError('Accepted shared runtime changed')
        avf=check.accepted.avf
        vm2=main/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105';vm4=main/'worktrees/vm-004-20261105/artifacts/qemu-host';qemu=vm4/'build-6/build/qemu-system-aarch64';shim=vm2/'Image'
        if check.sha(qemu)!=avf.PIN['qemu_sha256'] or check.sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Accepted unchanged CPU harness binaries required')
        report['avf_inputs']={'pin':avf.PIN,'qemu':str(qemu),'shim':str(shim),'runtime_sha256':check.sha(runtime),'accepted_helper_sha256':check.sha(main/'tools/verify/avf_handoff.py'),'accepted_xts_runner_sha256':check.sha(main/'src/platform/crypto/xts/check.py'),'provenance':'Unchanged accepted KRN029 shared harness; no Exynos model or XNU execution','legacy_naming':'Shared runtime cookie/markers remain XTS. Unique CHACHA markers establish which owned algorithm suite executed.'}
        base=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot']
        report['guest_cases']=[];corpus=json.loads((source/'regenerated/vectors.json').read_text())
        for name,mode,cookie in [('positive','normal','xts_cookie=owned-adapter-v1'),('wrong-cookie','normal','xts_cookie=wrong'),('corrupt-vector','normal','xts_cookie=owned-adapter-v1'),('spin-timeout','spin','xts_cookie=owned-adapter-v1')]:
            kernel=bytearray((source/(mode+'.macho')).read_bytes())
            if name=='corrupt-vector':
                pattern=bytes.fromhex(corpus['vectors'][0]['ct'])
                if kernel.count(pattern)!=1:raise ValueError('Actual negative expected-vector bytes must be unique')
                offset=kernel.index(pattern);kernel[offset]^=1
                report['corrupt_vector_control']={'offset':offset,'mutation':'xor1 first expected ciphertext byte in OWN actual image','expected_sha256':hashlib.sha256(pattern).hexdigest()}
            payload=out/(name+'.xnup');avf.xnup(payload,kernel,'cpus=1 '+cookie);argv=[*base,'-initrd',payload]
            if name=='positive':
                dtb=out/'qemu.dtb';dump=list(argv);dump[2]+=',dumpdtb='+str(dtb)
                command(dump,'dtb-dump',5);report['qemu_dtb']=avf.fdt(dtb)
            q=command(argv,name,3 if mode=='spin' else 30,None);console=(out/(name+'.log')).read_text(errors='replace');passed='CHACHA ARM PASS' in console
            if name=='positive':
                m=re.search(r'CHACHA ARM PASS checks=(0x[0-9a-f]+) failure_line=0x0 incnonce=UNQUALIFIED',console);entry=re.search(r'XTS SYNTHETIC ENTER entry=(0x[0-9a-f]+) ba=(0x[0-9a-f]+)',console)
                ok=bool(m and entry) and int(entry[1],16)==old['images'][mode]['entry_pa'] and int(entry[2],16)==old['images'][mode]['bootargs_pa'] and q['outcome']=='pass' and 'XTS SYNTHETIC HANDOFF VERIFIED' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
                if m:
                    report['arm_checks']=int(m[1],16);ok=ok and report['arm_checks']==old['host_checks']
            elif name=='wrong-cookie':ok=not passed and 'XTS SYNTHETIC REJECT command-cookie' in console and q['outcome']=='pass'
            elif name=='corrupt-vector':ok=not passed and 'CHACHA ARM FAIL' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console and q['outcome']=='pass'
            else:ok=not passed and 'CHACHA SYNTHETIC SPIN-CONTROL' in console and q['outcome']=='timeout'
            report['guest_cases'].append({'name':name,'accepted':ok,'payload_sha256':check.sha(payload),'console_sha256':check.sha(out/(name+'.log'))})
            if not ok:raise ValueError('Guest control failed '+name)
        if check.sha(qemu)!=avf.PIN['qemu_sha256'] or check.sha(shim)!=avf.PIN['shim_sha256']:raise ValueError('Immutable shared binary changed')
        report['supported_cpu']='pass';report['summary']='Real typed explicit-nonce ARM suite59 vectors matched sanitized host; reject/corruption/stop controls passed. Full all-ten acceptance incomplete: applicable incnonce semantics unavailable.'
    except ResourceDeferred as error:report['supported_cpu']='resource-deferred';report['error']=str(error)
    except Exception as error:report['error']=repr(error)
    finally:
        report['artifacts']=[str(p.relative_to(main)) for p in out.rglob('*') if p.is_file()];report['sha256']={str(p.relative_to(main)):check.sha(p) for p in out.rglob('*') if p.is_file()};report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();(out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report.get(k) for k in ['outcome','supported_cpu','arm_checks','guest_cases','error']}));return report['supported_cpu']!='pass'
if __name__=='__main__':raise SystemExit(main())
