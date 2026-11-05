#!/usr/bin/env python3
"""Retain passed native/host objects; finish only missing genuine fixture header."""
import argparse,datetime,hashlib,importlib.util,json,os,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);a=p.parse_args();m=a.root.resolve()
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh name')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'verifier.py').write_bytes(Path(__file__).read_bytes())
 s=importlib.util.spec_from_file_location('des_runner',WT/'src/platform/crypto/des/check.py');runner=importlib.util.module_from_spec(s);s.loader.exec_module(runner);runner.ENV_OVERRIDES|={'LC_ALL':'C','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};runner.CHILD_ENV=dict(os.environ)|runner.ENV_OVERRIDES
 r={'task':'KRN-039','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'checks':[],'parents':{},'guest_executed':False,'full_kernel_qualified':False,'native_device_qualified':False}
 def check(n,ok):
  r['checks'].append(dict(name=n,passed=bool(ok)))
  if not ok:raise ValueError(n)
 def run(argv,label):
  v=runner.run(argv,out,label,30,256);r['commands'].append(v);check('command-'+label,v['exit_code']==0 and v['outcome']=='pass')
 try:
  state=load(m/'state/lab.json');t=next(x for x in state['tasks'] if x['id']=='KRN-039');e=next(x for x in state['experiments'] if x['id']==a.experiment);check('owned-active-prospective-plan',t['owner']==e['owner']=='codex-team-kernel-des-20261105-ci' and t['status']=='in_progress' and e['task']=='KRN-039' and e['status']=='planned');r['planning_record']=e
  old=load(a.parent);check('exact-parent-limitation',old['error']=="ValueError('command-host-compile-publication-main')" and [x['name'] for x in old['checks'] if not x['passed']]==['command-host-compile-publication-main']);r['parents']['retained-native-and-host']={'path':str(a.parent.relative_to(m)),'sha256':sha(a.parent),'original_outcome':'fail','original_error':old['error']}
  for path,digest in old['sha256'].items():check('retained-artifact-'+path,sha(m/path)==digest)
  for path,digest in old['source_inputs'].items():
   if path!='fixtures/public/xnu-kernel-des/host_publication.c':check('unchanged-source-'+path,sha(WT/path)==digest)
  for path,digest in old['retained_host_objects'].items():check('unchanged-host-dependency-'+path,sha(path)==digest)
  r['source_inputs']={str(p.relative_to(WT)):sha(p) for p in [Path(__file__),WT/'fixtures/public/xnu-kernel-des/host_publication.c',WT/'src/platform/crypto/des/kernel_provider.c',WT/'src/platform/crypto/des/kernel_provider.h']}
  host=Path(old['host_compiler']['path']);check('qualified-host-compiler',sha(host)==old['host_compiler']['sha256'])
  for path,digest in old['host_compiler']['runtime_hashes'].items():check('actual-sanitizer-runtime-'+path,sha(path)==digest)
  failed=old['commands'][-1];check('genuine-only-fixture-header-diagnosis','undeclared function \'cccbc_ctx_decl\'' in (a.parent.parent/'host-compile-publication-main.log').read_text() and failed['argv'][0]==str(host));argv=list(failed['argv']);argv[argv.index('-o')+1]=str(out/'publication-main.o');run(argv,'compile-publication-main')
  mismatch=list(argv);mismatch.insert(mismatch.index('-c'),'-DKDES_FACTORY_MISMATCH');mismatch[mismatch.index('-o')+1]=str(out/'mismatch-main.o');run(mismatch,'compile-mismatch-main')
  dependencies=[Path(x) for x in old['retained_host_objects']]
  for label in ['publication','mismatch']:
   run([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread','-Wl,--threads=1',a.parent.parent/'host-helper.o',a.parent.parent/('host-'+('gated' if label=='publication' else 'mismatch')+'.o'),*dependencies,out/(label+'-main.o'),'-o',out/label],'link-'+label);run([out/label],'run-'+label);check('actual-real-'+label+'-pass','KDES PUBLICATION PASS' in (out/('run-'+label+'.log')).read_text())
  for key in ['coherent_component_manifest','public_modes','clear_provider','zeroize_provider','import_provider_map','production_clear_codegen','pre-IV-exclusions','host_compiler','retained_host_objects','vectors','disassembler']:
   r[key]=old[key]
  r['retained_commands']=old['commands'][:-1];r['retained_native_checks']=[x for x in old['checks'] if x['passed']];r['outcome']='pass'
 except Exception as error:r['error']=repr(error)
 finally:
  r['resource_admission_wait_seconds']=runner.RESOURCE_WAIT_USED;r['sha256']={str(p.relative_to(m)):sha(p) for p in out.rglob('*') if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ['outcome','error']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
