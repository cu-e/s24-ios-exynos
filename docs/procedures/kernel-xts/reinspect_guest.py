#!/usr/bin/env python3
"""Classify retained genuine mapping exception; no guest or successful-case rerun."""
import argparse,datetime,hashlib,importlib.util,json,os,re,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--run',required=True);a=p.parse_args();m=a.root.resolve();parent=a.parent.resolve();old=load(parent);out=WT/'artifacts/kernel-xts'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'verifier.py').write_bytes(Path(__file__).read_bytes())
 def module(name,path):
  s=importlib.util.spec_from_file_location(name,path);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
 b=module('builder',WT/'tools/build/xnu_kernel_xts.py');q=module('qualified',WT/'src/platform/crypto/xts/check.py');env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0')
 r=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),task='KRN-031',commands=[],checks=[],guest_reruns=0,full_kernel_qualified=False,full_crypto_qualified=False,native_device_qualified=False,retained_parent={'path':str(parent.relative_to(m)),'sha256':sha(parent),'original_outcome':old['outcome'],'original_error':old.get('error')})
 def check(name,ok):
  r['checks'].append({'name':name,'passed':bool(ok)})
  if not ok:raise ValueError(name)
 try:
  check('exact-diagnosed-original-case',old.get('error')=="ValueError('Actual caller/control case failed bad-mapping')" and [x['case'] for x in old['guest_cases']]==['positive','wrong-cookie','bad-mapping'])
  for path,digest in old['sha256'].items():check('retained-artifact-'+path,sha(m/path)==digest)
  argv=['git','-C',str(m/'references/scion-avf'),'show','a6f4bc38aa244359cd365c976244a88c9d6b3304:avf/shim/avfboot.c'];v=subprocess.run(argv,env=env,capture_output=True,timeout=10);r['commands'].append({'argv':argv,'exit_code':v.returncode,'stdout_sha256':hashlib.sha256(v.stdout).hexdigest(),'environment_overrides':{'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}});text=v.stdout.decode();check('primary-handler-natural-PSCI-failure-path',v.returncode==0 and 'void avfboot_exception(' in text and 'die("unexpected exception");' in text and 'psci_call(PSCI_SYSTEM_OFF, 0, 0, 0);' in text)
  binding=next(x['sha256'] for x in load(m/'worktrees/vm-002-20261105/artifacts/vm-002/shim-20261105/report.json')['sources'] if x['path']=='avf/shim/avfboot.c');check('handler-binds-unchanged-actual-shim',hashlib.sha256(v.stdout).hexdigest()==binding);r['primary_exception_handler_sha256']=binding
  native=load(m/'worktrees/krn-031-20261105/artifacts/kernel-xts/frozen-native2/evidence.json');check('controlled-shift-actual-compiler-input',any('-DKXTS_BAD_MAPPING'in c['argv'] for c in native['commands']));source=WT/'fixtures/public/xnu-kernel-xts/guest.c';check('actual-frozen-fixture-source',sha(source)==next(x['source_sha256'] for x in native['components'] if x['id']=='fixture/bad-mapping'))
  r['guest_cases']=[]
  for row in old['guest_cases']:
   name=row['case'];image=m/row['image'];check('unchanged-image-'+name,sha(image)==row['image_sha256']);proof=b.image_proof(image);log=parent.parent/(name+'.log');console=log.read_text(errors='replace');run=load(parent.parent/(name+'.json'));check('natural-exit-and-owned-cleanup-'+name,run['exit_code']==0 and run['outcome']=='pass' and not any(x['state']!='Z' for x in run['after']['owned_processes']))
   if name=='positive':ok=bool(re.search(r'KXTS CALLER PASS vectors=0x4c4 checks=0x1cb6 line=0x0',console)) and old['vectors']==1220 and old['checks']==7350 and row['accepted'] is True
   elif name=='wrong-cookie':ok='XTS SYNTHETIC REJECT command-cookie' in console and 'KXTS MAPPED' not in console and 'KXTS CALLER PASS' not in console and row['accepted'] is True
   else:
    diagnosis=b.shifted_mapping_result(console,run,proof,q.avf.macho(image)['segments']);r['mapping_diagnosis']=diagnosis;ok=diagnosis['accepted'] and row['accepted'] is False
   check('precise-retained-case-'+name,ok);r['guest_cases'].append({'case':name,'accepted':True,'original_validator_accepted':row['accepted'],'console_sha256':sha(log),'image_sha256':sha(image),'run_metadata_sha256':sha(parent.parent/(name+'.json'))})
  r['vectors']=1220;r['checks_executed_in_positive']=7350;r['outcome']='pass';r['summary']='Exact retained positive/wrong-cookie reused; controlled shifted mapping faults at linked high-VA entry, outside loaded image, and genuine pinned shim naturally powers off via PSCI. Original timeout-only classifier failure retained; no guest rerun.'
 except Exception as error:r['error']=repr(error)
 finally:
  r['artifacts']=[str(p.relative_to(m)) for p in sorted(out.rglob('*')) if p.is_file()];r['sha256']={str(p.relative_to(m)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ['outcome','error','mapping_diagnosis','guest_reruns']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
