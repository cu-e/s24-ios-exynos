#!/usr/bin/env python3
"""Genuine selected native DES provider integration; no full kernel link/device."""
import argparse,datetime,hashlib,importlib.util,json,os,re,shutil,struct,subprocess,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[2]
OWNER='codex-team-kernel-des-20261105-ci'
ENV=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1',LC_ALL='C',PYTHONUTF8='1')
XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
SLOTS={'ccdes_ecb_encrypt':'s24_kernel_des_ecb_encrypt','ccdes_ecb_decrypt':'s24_kernel_des_ecb_decrypt','ccdes_cbc_encrypt':'s24_kernel_des_cbc_encrypt','ccdes_cbc_decrypt':'s24_kernel_des_cbc_decrypt','cctdes_ecb_encrypt':'s24_kernel_tdes_ecb_encrypt','cctdes_ecb_decrypt':'s24_kernel_tdes_ecb_decrypt','cctdes_cbc_encrypt':'s24_kernel_tdes_cbc_encrypt','cctdes_cbc_decrypt':'s24_kernel_tdes_cbc_decrypt','ccdes_key_is_weak_fn':'s24_kernel_des_key_is_weak','ccdes_key_set_odd_parity_fn':'s24_kernel_des_key_set_odd_parity'}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def dump(p,r):Path(p).write_text(json.dumps(r,indent=2)+'\n')
def module(name,p):
 s=importlib.util.spec_from_file_location(name,p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);p.add_argument('--reuse-native',type=Path,help='Bind passed unchanged components; compile only changed production ESP');a=p.parse_args();m=a.root.resolve()
 if WT==m or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('Fresh isolated worktree run required')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);shutil.copyfile(__file__,out/'builder.py')
 runner=module('accepted_des_supervisor',WT/'src/platform/crypto/des/check.py');runner.ENV_OVERRIDES=runner.ENV_OVERRIDES|{'LC_ALL':'C','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};runner.CHILD_ENV=dict(os.environ)|runner.ENV_OVERRIDES
 sys.path.insert(0,str(WT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 r=dict(kind='host-test',origin='local-host',outcome='fail',task='KRN-039',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commands=[],checks=[],parents={},source_reads=[],components=[],source_inputs={},full_provider_startup_executed=False,full_kernel_qualified=False,full_crypto_qualified=False,private_Apple_ABI_qualified=False,native_device_qualified=False,guest_executed=False)
 def check(name,ok,**details):
  r['checks'].append({'name':name,'passed':bool(ok),**details})
  if not ok:raise ValueError(name)
 def run(argv,label,expected=0,seconds=30):
  v=runner.run(argv,out,label,seconds,256);r['commands'].append(v)
  if expected is not None:check('command-'+label,v['exit_code']==expected and v['outcome']=='pass')
  return v
 def git(repo,pin,file):
  argv=['git','-C',str(m/repo),'show',pin+':'+file];v=subprocess.run(argv,env=ENV,capture_output=True,timeout=10);r['source_reads'].append({'argv':argv,'exit_code':v.returncode,'sha256':hashlib.sha256(v.stdout).hexdigest(),'environment_overrides':{k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','LC_ALL','PYTHONUTF8']}});check('pinned-source-'+file,v.returncode==0);return v.stdout
 try:
  ledger=load(m/'state/lab.json');tasks={t['id']:t for t in ledger['tasks']};t=tasks['KRN-039'];e=next(e for e in ledger['experiments'] if e['id']==a.experiment);check('owned-active-task',t['status']=='in_progress' and t['owner']==OWNER);check('owned-prospective-plan',e['status']=='planned' and e['owner']==OWNER and e['task']=='KRN-039');check('completed-prerequisites',all(tasks[x]['status']=='done' for x in ['KRN-031','KRN-032']));r['planning_record']=e;r['planning_snapshot_sha256']=sha(m/'state/lab.json')
  v=subprocess.run(['git','-C',str(WT),'rev-parse','HEAD'],env=ENV,capture_output=True,text=True,check=True,timeout=10);r['commit']=v.stdout.strip();v=subprocess.run(['git','-C',str(WT),'status','--porcelain','--untracked-files=all'],env=ENV,capture_output=True,text=True,check=True,timeout=10);r['owned_dirty_at_start']=v.stdout
  xts_cap_path=m/'docs/procedures/kernel-xts/qualified-evidence.json';xts_cap=load(xts_cap_path);des_cap_path=m/'docs/procedures/crypto-des/qualified-evidence.json';des_cap=load(des_cap_path)
  for name,path,cap in [('native-XTS',xts_cap_path,xts_cap),('DES-component',des_cap_path,des_cap)]:check('accepted-parent-'+name,cap['outcome']=='pass');r['parents'][name]={'path':str(path.relative_to(m)),'sha256':sha(path)}
  des_raw_path=m/des_cap['raw_evidence']['path'];check('accepted-DES-raw-capsule',sha(des_raw_path)==des_cap['raw_evidence']['sha256']);des_raw=load(des_raw_path)
  for name,digest in des_raw['owned_source_hashes'].items():
   path=Path(name) if Path(name).is_absolute() else m/name
   if str(path).startswith(str(m/'worktrees/krn-032-20261105')):path=WT/path.relative_to(m/'worktrees/krn-032-20261105')
   elif not path.exists() and (WT/name).exists():path=WT/name
   check('unchanged-DES-input-'+name,sha(path)==digest)
  base_path=m/xts_cap['coherent_component_manifest']['path'];check('accepted985-manifest',sha(base_path)==xts_cap['coherent_component_manifest']['sha256']);base=load(base_path);rows=base['objects'];selected={x['id']:x for x in rows};check('actual985-unique-identities',len(rows)==len(selected)==985)
  for row in rows:
   for key in ['source','output']:
    if sha(m/row[key])!=row[key+'_sha256']:raise ValueError('Changed accepted native identity '+row['id'])
  original_deps=load(m/'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3/current-dependency-files.json')
  for name,digest in original_deps.items():
   if sha(m/name)!=digest:raise ValueError('Changed original native dependency '+name)
  check('3156-original-dependencies-unchanged',len(original_deps)==3156)
  for info in xts_cap['reports'].values():check('retained-native-report-'+info['path'],sha(m/info['path'])==info['sha256'])
  strict=load(m/xts_cap['reports']['strict_native']['path']);prior=load(m/strict['parents']['retained-native']['path']);r['parents']['native-snapshot']={'path':strict['parents']['retained-native']['path'],'sha256':sha(m/strict['parents']['retained-native']['path'])};runtime=strict['qualified_link_runtime'];check('qualified-LINK-ONLY-runtime',sha(m/runtime['archive'])==runtime['sha256']);r['qualified_link_runtime']=runtime
  for row in strict['remaining_exports']['entries'].values():check('unchanged-private-export-list',sha(m/row['path'])==row['sha256'])
  r['remaining_exports']=strict['remaining_exports'];r['baseline_graph']={'path':str(base_path.relative_to(m)),'sha256':sha(base_path),'objects':985,'dependencies':3156,'native_metadata':strict['original_graph']}
  source=out/'source';(source/'osfmk/minicrypto').mkdir(parents=True);(source/'libkern/crypto').mkdir(parents=True);(source/'bsd/netinet6').mkdir(parents=True)
  production={}
  provider_row=selected['osfmk/mc_provider.o'];provider_path=source/'osfmk/minicrypto/mc_provider.c';provider_path.write_bytes((m/provider_row['source']).read_bytes());production['osfmk/mc_provider.o']=provider_path
  for ident,file in [('libkern/corecrypto_des.o','libkern/crypto/corecrypto_des.c'),('bsd/esp_core.o','bsd/netinet6/esp_core.c')]:
   raw=git('references/apple-xnu',XNU,file);check('actual-selected-source-'+ident,raw==(m/selected[ident]['source']).read_bytes());dest=source/file;dest.write_bytes(raw);production[ident]=dest
  (source/'osfmk/minicrypto/minicrypto.h').write_bytes(git('references/s24-port','c8860decc62c6d6180e609036d027a2997972420','xnu/hackios/files/osfmk/minicrypto/minicrypto.h'))
  for patch in sorted((WT/'patches/kernel-des-provider').glob('*.patch')):
   command=['git','apply','--unsafe-paths','--check','--directory='+str(source),str(patch)];run(command,'check-'+patch.stem);command.remove('--check');run(command,'apply-'+patch.stem);r['source_inputs'][str(patch.relative_to(m))]=sha(patch)
  native_report_path=m/'artifacts/xnu-compiler-cxx-storage/full-profile-session2/report.json';native=load(native_report_path);r['parents']['native-recipes']={'path':str(native_report_path.relative_to(m)),'sha256':sha(native_report_path)}
  des=WT/'src/platform/crypto/des';objects=out/'objects';objects.mkdir()
  reused=None
  if a.reuse_native:
   reused=load(a.reuse_native);check('passed-retained-native-parent',reused['outcome']=='pass' and len(reused['components'])==6)
   r['parents']['reused-native']={'path':str(a.reuse_native.relative_to(m)),'sha256':sha(a.reuse_native)}
  def recipe(ident):
   path=str(m/selected[ident]['source'])
   if ident=='osfmk/mc_provider.o':return next(c for c in prior['commands'] if '-c'in c['argv'] and path in c['argv']),path
   return next(c for c in native['commands'] if '-c'in c['argv'] and path in c['argv']),path
  def compile(ident,path,template,extra=(),expected=0):
   if reused and ident!='bsd/esp_core.o':
    row=next(x for x in reused['components'] if x['id']==ident);dest=m/row['output']
    check('unchanged-retained-component-'+ident,row['source_sha256']==sha(path) and row['output_sha256']==sha(dest))
    r['components'].append(dict(row,reused_from=r['parents']['reused-native']))
    return ObjectData(dest),dest
   c,old=recipe(template);argv=list(c['argv']);compiler=Path(argv[0]);check('actual-native-compiler-'+ident,sha(compiler)==strict['native_compiler']['sha256']);argv[argv.index(old)]=str(path);dest=objects/(ident.replace('/','-')+'.o');argv[argv.index('-o')+1]=str(dest);argv[argv.index('-MF')+1]=str(dest.with_suffix('.d'));argv=['-I'+c['cwd'] if x=='-I.' else x for x in argv];argv+=['-I'+str(WT/'src'),'-I'+str(des),'-Werror=incompatible-function-pointer-types','-Werror=incompatible-function-pointer-types-strict','-fstack-usage',*extra]
   v=run(argv,'compile-'+ident.replace('/','-'),expected=expected)
   if expected is None:return v,dest
   header=struct.unpack('<4I',dest.read_bytes()[:16]);check('real-native-ARM64-object-'+ident,(header[0],header[1],header[3])==(0xfeedfacf,0x100000c,1));row={'id':ident,'source':str(path.relative_to(m)),'source_sha256':sha(path),'output':str(dest.relative_to(m)),'output_sha256':sha(dest),'template':template,'argv':v['argv']};r['components'].append(row);return ObjectData(dest),dest
  provider,pobj=compile('osfmk/mc_provider.o',provider_path,'osfmk/mc_provider.o')
  caller,cobj=compile('libkern/corecrypto_des.o',production['libkern/corecrypto_des.o'],'libkern/corecrypto_des.o')
  esp,eobj=compile('bsd/esp_core.o',production['bsd/esp_core.o'],'bsd/esp_core.o')
  publication,hobj=compile('component/des-kernel-provider',des/'kernel_provider.c','libkern/corecrypto_des.o')
  profile=['-mgeneral-regs-only','-mstrict-align','-mno-outline-atomics','-I'+str(des/'vendor/include'),'-I'+str(des/'vendor/library'),'-isystem',str(m/'references/xnu-tapi/src/clang/lib/Headers'),'-DMBEDTLS_CONFIG_FILE="s24_des_profile.h"','-DS24_DES_FREESTANDING']
  adapter,aobj=compile('component/des',des/'des.c','libkern/corecrypto_des.o',profile)
  primitive,dobj=compile('component/mbedtls-des',des/'vendor/library/des.c','osfmk/mc_provider.o',profile)
  baseline=ObjectData(m/provider_row['output']);fields=load(WT/'fixtures/public/corecrypto-provider/registration-abi.json')['table']['fields'];observations=[]
  for row in fields:
   name=row['field'];offset=row['offset'];expected='_'+SLOTS[name] if name in SLOTS else row['target'] if row['state']=='relocated' else None
   if name in ['ccaes_xts_encrypt','ccaes_xts_decrypt']:expected='_s24_kernel_xts_'+('encrypt' if name.endswith('encrypt') else 'decrypt')
   if expected:
    actual=provider.relocation('_mc_funcs',offset);check('actual-relocation-'+name,actual['name']==expected)
    if name not in SLOTS:check('preserved-original36-'+name,actual['name']==baseline.relocation('_mc_funcs',offset)['name'])
    observations.append({'field':name,'offset':offset,'state':'relocated','target':actual['name']})
   else:
    check('remaining-static-zero-'+name,provider.value('_mc_funcs','<Q',offset)==(0,));observations.append({'field':name,'offset':offset,'state':'deferred-SHA256' if name=='ccsha256_di' else 'unsupported'})
  check('46-static-one-deferred-nine-unsupported',sum(x['state']=='relocated' for x in observations)==46 and sum(x['state']=='deferred-SHA256' for x in observations)==1 and sum(x['state']=='unsupported' for x in observations)==9);r['table_observation']=observations
  layout=publication.value('_s24_kernel_des_layout','<16Q');r['public_layout']=layout;r['private_layout']=adapter.value('_s24_des_layout','<7Q');check('actual-public-private-layout',layout==(48,40,8,8,16,16,256,768,144,400,4,16,24,32,16,24) and r['private_layout']==(144,400,16,128,384,48,40))
  r['symbols']={};definitions=set()
  for name,obj in [('provider',provider),('caller',caller),('ESP',esp),('publication',publication),('adapter',adapter),('primitive',primitive)]:
   defs={x['name'] for x in obj.symbols if x['kind']&0x0e==0x0e and x['kind']&1};imports={x['name'] for x in obj.symbols if x['kind']&0x0e==0 and x['name']};definitions|=defs;r['symbols'][name]={'definitions':sorted(defs),'imports':sorted(imports)}
  r['stack_usage']=dict(reused['stack_usage']) if reused else {}
  r['stack_usage'].update({str(p.relative_to(m)):p.read_text() for p in objects.glob('*.su')});check('actual-compiler-stack-usage-records',len(r['stack_usage'])>=6)
  r['component_dependency_hashes']=dict(reused['component_dependency_hashes']) if reused else {}
  for path,digest in r['component_dependency_hashes'].items():check('retained-component-dependency-'+path,sha(path)==digest)
  for dep in objects.glob('*.d'):
   first=dep.read_text().replace('\\\n',' ').splitlines()[0]
   for path in first.split(':',1)[1].split():r['component_dependency_hashes'][path]=sha(path)
  r['outcome']='pass';r['summary']='Genuine selected native DES provider/caller/ESP plus real publication/primitive objects compiled and actual46-slot/deferredSHA/nine-unsupported layout proven; CPU/closure controls pending, no full startup/kernel/native claim'
 except Exception as error:r['error']=repr(error)
 finally:
  r['resource_admission_wait_seconds']=runner.RESOURCE_WAIT_USED;r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['artifacts']=[str(p.relative_to(m)) for p in out.rglob('*') if p.is_file()];r['sha256']={str(p.relative_to(m)):sha(p) for p in out.rglob('*') if p.is_file()};dump(out/'evidence.json',r)
 print(json.dumps({k:r.get(k) for k in ['outcome','error','public_layout','private_layout']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
