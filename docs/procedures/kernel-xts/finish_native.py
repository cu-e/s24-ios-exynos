#!/usr/bin/env python3
"""Retain passed component measurements; repair only the diagnosed strict-type control."""
import argparse,datetime,hashlib,importlib.util,json,os,re,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1')
OWNER='codex-team-kernel-xts-20261105-br'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--parent',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);a=p.parse_args();m=a.root.resolve();oldpath=a.parent.resolve();old=load(oldpath)
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('Fresh simple run name required')
 out=WT/'artifacts/kernel-xts'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'verifier.py').write_bytes(Path(__file__).read_bytes())
 def module(name,path):
  s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
 bounded=module('accepted_supervisor',WT/'src/platform/crypto/xts/check.py');builder=module('component_builder',WT/'tools/build/xnu_kernel_xts.py');sys.path.insert(0,str(WT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 r=dict(kind='host-test',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),task='KRN-031',commands=[],checks=[],parents={'retained-native':{'path':str(oldpath.relative_to(m)),'sha256':sha(oldpath),'original_outcome':old['outcome'],'original_error':old.get('error')}},full_kernel_qualified=False,full_crypto_qualified=False,apple_private_abi_qualified=False,native_device_qualified=False)
 def check(name,ok,**details):
  r['checks'].append({'name':name,'passed':bool(ok),**details})
  if not ok:raise ValueError(name)
 def run(argv,label,expected):
  check('4GiB-floor-'+label,builder.memory_available()>=4*1024**3)
  v=bounded.run(argv,out,label,30,256);r['commands'].append(v)
  if expected==0:check('matched-header-positive',v['exit_code']==0 and v['outcome']=='pass')
  else:check('actual-wrong-signature-error',v['exit_code']!=0 and 'error: incompatible function pointer types' in (out/(label+'.log')).read_text() and '-Wincompatible-function-pointer-types-strict' in (out/(label+'.log')).read_text() and not(out/'rejected.o').exists())
  return v
 try:
  ledger=load(m/'state/lab.json');t=next(t for t in ledger['tasks'] if t['id']=='KRN-031');check('owned-active-task',t['owner']==OWNER and t['status']=='in_progress');e=next(e for e in ledger['experiments'] if e['id']==a.experiment);check('owned-plan',e['owner']==OWNER and e['task']=='KRN-031' and e['status']=='planned')
  v=subprocess.run(['git','-C',str(WT),'rev-parse','HEAD'],env=ENV,capture_output=True,text=True,check=True,timeout=10);r['commit']=v.stdout.strip()
  check('only-parent-failure-is-diagnostic-policy',old.get('error')=="ValueError('real-genuine-header-callback-rejection')" and [x['name'] for x in old['checks'] if not x['passed']]==['real-genuine-header-callback-rejection'])
  for name,digest in old['sha256'].items():
   if sha(m/name)!=digest:raise ValueError('Changed retained artifact '+name)
  check('all-retained-artifacts-rehashed',True,count=len(old['sha256']))
  for row in old['components']:
   check('retained-source-'+row['id'],sha(m/row['source'])==row['source_sha256']);check('retained-object-'+row['id'],sha(m/row['output'])==row['output_sha256'])
  graph=load(m/old['original_graph']['path'])
  for row in graph:
   for key in ['source','output']:
    if sha(m/row[key])!=row[key+'_sha256']:raise ValueError('Changed coherent native graph '+row['id'])
  deps=load(m/'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3/current-dependency-files.json')
  for name,digest in deps.items():
   if sha(m/name)!=digest:raise ValueError('Changed retained dependency '+name)
  check('982-graph-and3156-dependencies-unchanged',len(graph)==982 and len(deps)==3156)
  for row in old['remaining_exports']['entries'].values():check('retained-private-export-source',sha(m/row['path'])==row['sha256'])
  runtime=old['qualified_link_runtime'];check('retained-qualified-runtime',sha(m/runtime['archive'])==runtime['sha256'])
  accepted=load(m/'docs/procedures/crypto-xts/qualified-evidence.json')
  for name,digest in accepted['owned_source_hashes'].items():check('unchanged-accepted-XTS-'+name,sha(WT/name)==digest)
  bad=old['commands'][-1];check('actual-prior-strict-warning-counterexample',bad['exit_code']==0 and '-Wincompatible-function-pointer-types-strict' in (oldpath.parent/'reject-incompatible-actual-callback.log').read_text())
  r['diagnosis']={'original_command':bad['argv'],'original_exit_code':0,'diagnostic':'-Wincompatible-function-pointer-types-strict is separate from -Wincompatible-function-pointer-types','correction':'Promote strict diagnostic for both actual negative and real unchanged helper positive; retain all prior successful measurements'}
  argv=list(bad['argv']);argv[argv.index('-o')+1]=str(out/'rejected.o');argv[argv.index('-MF')+1]=str(out/'rejected.d');argv+=['-Werror=incompatible-function-pointer-types-strict'];run(argv,'wrong-signature-strict',1)
  source=str(WT/'src/platform/crypto/xts/kernel_provider.c');native_compiler=str(m/old['native_compiler']['path']);positive=next(c for c in old['commands'] if c['argv'][0]==native_compiler and source in c['argv'] and '-c'in c['argv']);argv=list(positive['argv']);argv[argv.index('-o')+1]=str(out/'matched-helper.o');argv[argv.index('-MF')+1]=str(out/'matched-helper.d');argv+=['-Werror=incompatible-function-pointer-types-strict'];run(argv,'matched-helper-strict',0)
  before=ObjectData(m/next(c for c in old['components'] if c['id']=='component/kernel_provider')['output']);after=ObjectData(out/'matched-helper.o')
  check('matched-real-helper-genuine-layout',before.value('_s24_kernel_xts_layout','<11Q')==after.value('_s24_kernel_xts_layout','<11Q')==(80,8,1072,1072,16,608,48,24,32,40,48))
  for name in ['_s24_kernel_xts_encrypt','_s24_kernel_xts_decrypt']:
   check('same-actual-mode-bytes-'+name,before.value(name,'<3Q')==after.value(name,'<3Q')==(608,48,16))
   for offset in [24,32,40,48]:check('same-real-typed-callback-'+name+str(offset),before.relocation(name,offset)['name']==after.relocation(name,offset)['name'])
  bsec=before.sections[before.named['_s24_kernel_xts_prepare']['section']-1];asec=after.sections[after.named['_s24_kernel_xts_prepare']['section']-1]
  check('strict-policy-does-not-change-helper-code',before.data[bsec['offset']:bsec['offset']+bsec['size']]==after.data[asec['offset']:asec['offset']+asec['size']])
  r['component_dependency_hashes']={}
  for dep in [*sorted((oldpath.parent/'objects').glob('*.d')),out/'matched-helper.d',out/'rejected.d']:
   if not dep.exists():continue
   first=dep.read_text().replace('\\\n',' ').splitlines()[0]
   for name in first.split(':',1)[1].split():
    path=Path(name);check('absolute-dependency-path',path.is_absolute());r['component_dependency_hashes'][str(path.relative_to(m)) if path.is_relative_to(m) else str(path)]=sha(path)
  for key in ['components','guest_images','guest_image_ready','helper_layout','private_layout','original_graph','table_observation','startup_call_relocations','public_mode_objects','component_symbols','import_provider_map','qualified_link_runtime','remaining_exports','native_compiler','publication_controls']:
   r[key]=old[key]
  r['retained_original_commands']=old['commands'];r['retained_passing_checks']=[x for x in old['checks'] if x['passed']]
  for label,row in r['guest_images'].items():
   path=m/row['path'];check('retained-linked-image-'+label,sha(path)==row['sha256'])
   if label!='spin':r['guest_images'][label]['mapping_proof']=builder.image_proof(path,label!='factory-mismatch')
  r['owned_source_hashes']={str(p.relative_to(WT)):sha(p) for base in [WT/'src/platform/crypto/xts/kernel_provider.c',WT/'src/platform/crypto/xts/kernel_provider.h',WT/'tools/build/xnu_kernel_xts.py',Path(__file__),WT/'fixtures/public/xnu-kernel-xts',WT/'patches/kernel-xts-provider'] for p in ([base] if base.is_file() else sorted(base.rglob('*'))) if p.is_file()}
  r['outcome']='pass';r['summary']='Retained real successful native/caller/host/image measurements rehashed; exactly two targeted native compiles prove actual strict wrong-signature rejection and unchanged real matched helper. Original diagnostic-policy failure preserved.'
 except Exception as error:r['error']=repr(error)
 finally:
  r['artifacts']=[str(p.relative_to(m)) for p in sorted(out.rglob('*')) if p.is_file()];r['sha256']={str(p.relative_to(m)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ['outcome','error','commit','summary']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
