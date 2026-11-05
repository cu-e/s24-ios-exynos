#!/usr/bin/env python3
"""Bind actual passed component/CPU receipts to frozen implementation bytes."""
import argparse,collections,datetime,hashlib,importlib.util,json,os,re,struct,subprocess,sys
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
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--guest',type=Path,required=True);p.add_argument('--run',required=True);a=p.parse_args();m=a.root.resolve()
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh run name')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'verifier.py').write_bytes(Path(__file__).read_bytes());reader=module('image_reader',WT/'docs/procedures/kernel-des/prepare_caller.py');sys.path.insert(0,str(WT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 r={'task':'KRN-039','kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'checks':[],'reports':{},'source_reads':[],'full_provider_startup_executed':False,'full_kernel_qualified':False,'full_crypto_qualified':False,'FIPS_qualified':False,'side_channels_qualified':False,'private_Apple_ABI_qualified':False,'native_device_qualified':False,'kernel_MMU_qualified':False}
 def check(n,ok,**d):
  r['checks'].append(dict(name=n,passed=bool(ok),**d))
  if not ok:raise ValueError(n)
 def report(name,path,passed=True):
  v=load(path);check('report-outcome-'+name,not passed or v['outcome']=='pass');r['reports'][name]={'path':str(path.relative_to(m)),'sha256':sha(path),'outcome':v['outcome']}
  for key,digest in v.get('sha256',{}).items():check('unchanged-artifact-'+key,sha(m/key)==digest)
  return v
 try:
  state=load(m/'state/lab.json');t=next(x for x in state['tasks'] if x['id']=='KRN-039');check('active-original-owner',t['owner']=='codex-team-kernel-des-20261105-ci' and t['status']=='in_progress')
  guest=report('actual-CPU',a.guest);check('six-actual-cases-no-skips',len(guest['guest_cases'])==6 and {x['case'] for x in guest['guest_cases']}=={'positive','wrong-cookie','corrupt-answer','original-caller','panic','spin'} and all(x['accepted'] for x in guest['guest_cases']) and guest['genuine_selected_caller_executed']);r['source_subject_commit']=guest['commit'];r['guest_cases']=guest['guest_cases'];r['actual_workload']=guest['expected_positive']
  for child in guest['commands']:check('no-guest-survivors',not child['after']['owned_processes'])
  prepared=report('prepared-images',m/guest['prepared_parent']['path']);check('exact-prepared-binding',sha(m/guest['prepared_parent']['path'])==guest['prepared_parent']['sha256']);r['prepared_source_hashes']=prepared['source_inputs']
  for path,digest in prepared['source_inputs'].items():check('current-prepared-source-'+path,sha(WT/path)==digest)
  for row in prepared['fixture_components']:check('current-measured-fixture-'+row['output'],sha(m/row['source'])==row['source_sha256'] and sha(m/row['output'])==row['output_sha256'])
  verified=report('native-and-publication',m/prepared['parents']['verified']['path']);native=report('native-ESP',m/prepared['parents']['native']['path']);check('exact-parents',sha(m/prepared['parents']['verified']['path'])==prepared['parents']['verified']['sha256'] and sha(m/prepared['parents']['native']['path'])==prepared['parents']['native']['sha256']);retained=report('retained-native-controls',m/verified['parents']['retained-native-and-host']['path'],False);check('retained-only-fixture-header-failure',retained.get('error')=="ValueError('command-host-compile-publication-main')")
  manifest_path=m/verified['coherent_component_manifest']['path'];check('coherent-manifest-binding',sha(manifest_path)==verified['coherent_component_manifest']['sha256']);graph=load(manifest_path);rows={x['id']:x for x in graph['objects']};check('actual988-identities',len(rows)==len(graph['objects'])==988);r['coherent_component_manifest']=verified['coherent_component_manifest']
  for row in rows.values():check('native-source-object-'+row['id'],sha(m/row['source'])==row['source_sha256'] and sha(m/row['output'])==row['output_sha256'])
  table=ObjectData(m/rows['osfmk/mc_provider.o']['output']);observed=native['table_observation'];check('actual56-fields',len(observed)==56)
  for row in observed:
   if row['state']=='relocated':check('actual-static-slot-'+row['field'],table.relocation('_mc_funcs',row['offset'])['name']==row['target'])
   else:check('actual-static-zero-'+row['field'],table.value('_mc_funcs','<Q',row['offset'])==(0,))
  counts=collections.Counter(x['state'] for x in observed);check('actual46-plus-deferred-SHA-nine',counts=={'relocated':46,'deferred-SHA256':1,'unsupported':9});r['native_table']={'counts':counts,'fields':observed,'remaining_private_ARM_exports':37};r['actual_context_layout']={'DES_bytes':144,'TDES_bytes':400,'alignment':16,'selected_capacities':[256,768],'ECB_descriptor_bytes':48,'CBC_descriptor_bytes':40}
  providers={};symbol_index={}
  for row in rows.values():
   obj=reader.Image(m/row['output'])
   for name,entries in obj.symbols.items():
    for entry in entries:
     if entry['kind']==15 and not(entry['desc']&0x80):symbol_index.setdefault(name,[]).append({'id':row['id'],'output':row['output'],'output_sha256':row['output_sha256'],'symbol':entry})
  for name in ['_cc_clear','_memset_s','_secure_memset','_mbedtls_platform_zeroize']:
   check('unique-strong-provider-'+name,len(symbol_index.get(name,[]))==1);providers[name]=symbol_index[name][0]
  r['strong_clear_and_zeroizer_providers']=providers;r['clear_scope']='Actual unobserved production calls and complete existing strong source/object provider chain. Guest scratch/IV observer delegates to accepted volatile Mbed zeroizer and proves values/ownership separately; no full kernel/runtime erase qualification.'
  r['new_component_imports']={}
  for ident in ['component/des-kernel-provider','component/des','component/mbedtls-des']:
   obj=ObjectData(m/rows[ident]['output']);imports=sorted({x['name'] for x in obj.symbols if x['kind']&0x0e==0 and x['name']});r['new_component_imports'][ident]={}
   for name in imports:check('strong-import-provider-'+ident+name,len(symbol_index.get(name,[]))==1);r['new_component_imports'][ident][name]=symbol_index[name][0]
  esp=next(x for x in prepared['fixture_components'] if x['output'].endswith('/esp-patched.o'));r['genuine_fixture_record_layout']=ObjectData(m/esp['output']).value('_kdes_esp_record_layout','<9Q')
  r['owned_source_hashes']={str(x.relative_to(WT)):sha(x) for base in [WT/'src/platform/crypto/des/kernel_provider.c',WT/'src/platform/crypto/des/kernel_provider.h',WT/'patches/kernel-des-provider',WT/'fixtures/public/xnu-kernel-des',WT/'tools/build/xnu_kernel_des.py'] for x in ([base] if base.is_file() else sorted(base.rglob('*'))) if x.is_file()}
  for path,digest in r['owned_source_hashes'].items():
   argv=['git','-C',str(WT),'show',r['source_subject_commit']+':'+path];child=subprocess.run(argv,env=ENV,capture_output=True,timeout=10);actual=hashlib.sha256(child.stdout).hexdigest();r['source_reads'].append({'argv':argv,'exit_code':child.returncode,'sha256':actual});check('exact-commit-owned-source-'+path,child.returncode==0 and actual==digest)
  r['limits']=['Only selected DES8/TDES24; local EDE2/roundkey/general APIs unpublished','Original34+XTS2 callbacks and deferred SHA256 preserved;9 slots unsupported;37 private ARM exports unchanged','Full mc_provider startup/PRNG, ESP SADB/locking/key allocation/maturity and NFS/GSS/CTS paths not executed','Fixture logging/cluster/unavailable services fail-stop; IV-update service synthetic deterministic, not entropy','High-VA component runtime is synthetic; no XNU MMU/board/full kernel/native-device/private Apple ABI/FIPS/side-channel claim'];r['outcome']='pass'
 except Exception as error:r['error']=repr(error)
 finally:
  r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['artifact_sha256']={str(p.relative_to(m)):sha(p) for p in out.rglob('*') if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k)for k in ['outcome','error','source_subject_commit']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
