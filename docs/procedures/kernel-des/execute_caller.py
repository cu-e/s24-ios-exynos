#!/usr/bin/env python3
"""Execute only prebuilt owned component images under an explicit root guest lease."""
import argparse,datetime,hashlib,importlib.util,json,os,re,subprocess,sys,time
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',LC_ALL='C',PYTHONUTF8='1')
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);p.add_argument('--lease-grant',required=True);p.add_argument('--cases',default='positive,wrong-cookie,corrupt-answer,original-caller,panic,spin');a=p.parse_args();m=a.root.resolve()
 cases=a.cases.split(',');valid=['positive','wrong-cookie','corrupt-answer','original-caller','panic','spin']
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run) or not cases or len(cases)!=len(set(cases)) or any(x not in valid for x in cases):raise ValueError('fresh name and explicit unique cases required')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'runner.py').write_bytes(Path(__file__).read_bytes())
 runner=module('accepted_des_supervisor',WT/'src/platform/crypto/des/check.py');runner.ENV_OVERRIDES|={'LC_ALL':'C','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};runner.CHILD_ENV=dict(os.environ)|runner.ENV_OVERRIDES;avf=runner.avf;builder=module('caller_image_reader',WT/'docs/procedures/kernel-des/prepare_caller.py')
 started=time.monotonic();deadline=started+300
 r={'task':'KRN-039','kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'lease_grant':a.lease_grant,'whole_timeout_seconds':300,'requested_cases':cases,'commands':[],'checks':[],'guest_cases':[],'source_reads':[],'full_provider_startup_executed':False,'full_kernel_qualified':False,'full_crypto_qualified':False,'native_device_qualified':False,'kernel_MMU_qualified':False,'genuine_selected_caller_executed':False}
 def check(n,ok,**d):
  r['checks'].append(dict(name=n,passed=bool(ok),**d))
  if not ok:raise ValueError(n)
 try:
  state=load(m/'state/lab.json');t=next(x for x in state['tasks'] if x['id']=='KRN-039');e=next(x for x in state['experiments'] if x['id']==a.experiment);check('owned-active-prospective-plan',t['owner']==e['owner']=='codex-team-kernel-des-20261105-ci' and t['status']=='in_progress' and e['task']=='KRN-039' and e['status']=='planned');r['planning_record']=e
  rev=subprocess.run(['git','-C',str(WT),'rev-parse','HEAD'],env=ENV,capture_output=True,text=True,check=True,timeout=10);r['commit']=rev.stdout.strip();r['runner_sha256']=sha(__file__)
  parent=load(a.prepared);check('source-qualified-ready-images',parent['outcome']=='pass' and parent['guest_images_ready']);r['prepared_parent']={'path':str(a.prepared.relative_to(m)),'sha256':sha(a.prepared)}
  for path,digest in parent['source_inputs'].items():check('frozen-caller-source-'+path,sha(WT/path)==digest)
  for row in parent['fixture_components']:check('bound-fixture-'+row['output'],sha(m/row['source'])==row['source_sha256'] and sha(m/row['output'])==row['output_sha256'])
  for row in parent['retained_components']:check('retained-real-native-'+row['id'],sha(m/row['output'])==row['output_sha256'])
  check('unchanged-qualified-runtime',sha(WT/'fixtures/public/avf-handoff/runtime.h')==parent['accepted_runtime']['sha256'])
  vm2=m/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105';vm4=m/'worktrees/vm-004-20261105/artifacts/qemu-host';qemu=vm4/'build-6/build/qemu-system-aarch64';shim=vm2/'Image';check('qualified-unchanged-QEMU-shim',sha(qemu)==avf.PIN['qemu_sha256'] and sha(shim)==avf.PIN['shim_sha256']);sb=load(vm2/'report.json');qb=load(vm4/'build-6/build-report.json');qm=load(vm4/'release-10.2.0/source-manifest.json');check('qualified-source-build-bindings',sb['donor_commit']==avf.PIN['scion_commit'] and qb['pin']['commit']==avf.PIN['qemu_commit'] and qb['binary_sha256']==avf.PIN['qemu_sha256'])
  for row in sb['sources']:
   argv=['git','-C',str(m/'references/scion-avf'),'show',avf.PIN['scion_commit']+':'+row['path']];child=subprocess.run(argv,env=ENV,capture_output=True,timeout=10);digest=hashlib.sha256(child.stdout).hexdigest();r['source_reads'].append({'argv':argv,'exit_code':child.returncode,'sha256':digest});check('pinned-shim-source-'+row['path'],child.returncode==0 and digest==row['sha256'])
  for path in ['hw/arm/virt.c','hw/arm/boot.c','target/arm/tcg/psci.c']:check('pinned-QEMU-board-'+path,sha(vm4/'release-10.2.0/source/qemu-10.2.0'/path)==qm[path]['sha256'])
  r['qualified_inputs']={'pins':avf.PIN,'qemu':str(qemu),'shim':str(shim),'reports':{str(p.relative_to(m)):sha(p) for p in [vm2/'report.json',vm4/'build-6/build-report.json',vm4/'release-10.2.0/source-manifest.json']}}
  guest=(WT/'fixtures/public/xnu-kernel-des/guest.c').read_text().splitlines();expected_answer_line=next(i for i,line in enumerate(guest,1) if 'CHECK(!memcmp(out+1,expected' in line);original_source=m/next(x['source'] for x in parent['fixture_components'] if x['output'].endswith('/esp-original.o'));original_assert_line=next(i for i,line in enumerate(original_source.read_text().splitlines(),1) if 'if(error){FASSERT(result==' in line)
  header=m/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/regenerated/vectors.h';records=[tuple(map(int,x)) for x in re.findall(r'^\{(\d+),(\d+),(\d+),\d+,\d+,\d+,\d+\},$',header.read_text(),re.M)];selected=[x for x in records if x[0]!=16];expected_checks=sum(2*(11+n//8 if c else 9+2*(n//8))for _,n,c in selected)+753+125+12;check('source-bound-selected1964-check-count',len(selected)==1964 and expected_checks==47520);r['expected_positive']={'vectors':1964,'ESP_cases':120,'checks':expected_checks};r['negative_expected_locations']={'corrupt_answer_source_line':expected_answer_line,'original_error_source_line':original_assert_line,'original_error_case':13}
  for case in cases:
   label={'positive':'patched','wrong-cookie':'patched','original-caller':'original'}.get(case,case);row=parent['images'][label];image=m/row['path'];check('immutable-image-'+case,sha(image)==row['sha256']);proof=builder.Image(image).proof();check('exact-linked-mapping-proof-'+case,json.dumps(proof,sort_keys=True)==json.dumps(row['mapping_proof'],sort_keys=True));payload=out/(case+'.xnup');cookie='xts_cookie=wrong' if case=='wrong-cookie' else 'xts_cookie=owned-adapter-v1';avf.xnup(payload,image.read_bytes(),'cpus=1 '+cookie)
   timeout=3 if case=='spin' else 30;check('finite-whole-budget-before-child-'+case,time.monotonic()+timeout+50<=deadline)
   argv=[qemu,'-machine','virt,gic-version=3','-accel','tcg','-cpu','cortex-a76','-smp','1','-m','256','-kernel',shim,'-nodefaults','-nic','none','-display','none','-serial','stdio','-monitor','none','-no-reboot','-initrd',payload];result=runner.run(argv,out,case,timeout,512);r['commands'].append(result);console=(out/(case+'.log')).read_text(errors='replace');mapped=re.search(r'KDES MAPPED pc=(0x[0-9a-f]+) mode=(0x[0-9a-f]+) init=(0x[0-9a-f]+)',console);passed=re.search(r'KDES CALLER PASS vectors=(0x[0-9a-f]+) esp_cases=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=0x0',console);failed=re.search(r'KDES CALLER FAIL vectors=(0x[0-9a-f]+) esp_cases=(0x[0-9a-f]+) checks=(0x[0-9a-f]+) line=(0x[0-9a-f]+)',console);natural=result['outcome']=='pass' and result['exit_code']==0 and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' in console
   if mapped:
    mode=proof['public_modes']['_s24_kernel_des_cbc_encrypt'];check('actual-high-VA-code-mode-callback-'+case,tuple(int(mapped[i],16)for i in [1,2,3])==(proof['mapped_entry_va'],mode['va'],mode['callbacks'][0]))
   if case=='positive':ok=bool(mapped and passed) and natural and not failed and 'KDES ESP ASSERT' not in console and tuple(int(passed[i],16)for i in [1,2,3])==(1964,120,expected_checks);r['genuine_selected_caller_executed']=bool(ok)
   elif case=='wrong-cookie':ok=not mapped and not passed and natural and 'XTS SYNTHETIC REJECT command-cookie' in console
   elif case=='corrupt-answer':ok=bool(mapped and failed) and not passed and natural and tuple(int(failed[i],16)for i in [1,2,3,4])==(1,0,16,expected_answer_line)
   elif case=='original-caller':ok=bool(mapped) and not passed and natural and 'KDES ESP BASELINE SUCCESS cases=0xc' in console and ('KDES ESP ASSERT line='+hex(original_assert_line)+' case=0xd') in console
   elif case=='panic':ok=bool(mapped) and not passed and natural and 'KDES SYNTHETIC PANIC' in console and 'KDES ESP ASSERT' not in console
   else:ok=bool(mapped) and not passed and result['outcome']=='timeout' and 'KDES SPIN CONTROL' in console and 'XTS SYNTHETIC PSCI_SYSTEM_OFF' not in console
   r['guest_cases'].append({'case':case,'accepted':bool(ok),'image':str(image.relative_to(m)),'image_sha256':sha(image),'payload_sha256':sha(payload),'console_sha256':sha(out/(case+'.log')),'mapping_proof':proof,'result':result['outcome'],'exit_code':result['exit_code']});check('actual-case-'+case,ok)
  check('shared-tools-still-unchanged',sha(qemu)==avf.PIN['qemu_sha256'] and sha(shim)==avf.PIN['shim_sha256']);r['outcome']='pass'
 except Exception as error:r['error']=repr(error)
 finally:
  r['resource_admission_wait_seconds']=runner.RESOURCE_WAIT_USED;r['whole_elapsed_seconds']=time.monotonic()-started;r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['sha256']={str(p.relative_to(m)):sha(p) for p in out.rglob('*') if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k)for k in ['outcome','error','genuine_selected_caller_executed']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
