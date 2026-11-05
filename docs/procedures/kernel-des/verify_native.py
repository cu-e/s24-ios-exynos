#!/usr/bin/env python3
"""Targeted strict/publication/codegen proof over retained genuine native objects."""
import argparse,datetime,hashlib,importlib.util,json,os,re,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
WT=Path(__file__).resolve().parents[3]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def module(n,p):
 s=importlib.util.spec_from_file_location(n,p);v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--native',type=Path,required=True);p.add_argument('--run',required=True);p.add_argument('--experiment',required=True);p.add_argument('--host',action='store_true');a=p.parse_args();m=a.root.resolve()
 if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',a.run):raise ValueError('fresh simple name')
 out=WT/'artifacts/kernel-des'/a.run;out.mkdir(parents=True,exist_ok=False);(out/'verifier.py').write_bytes(Path(__file__).read_bytes())
 runmod=module('des_runner',WT/'src/platform/crypto/des/check.py');runmod.ENV_OVERRIDES|={'LC_ALL':'C','PYTHONUTF8':'1','PYTHONDONTWRITEBYTECODE':'1'};runmod.CHILD_ENV=dict(os.environ)|runmod.ENV_OVERRIDES
 sys.path.insert(0,str(WT/'tools/build'));from xnu_kernel_syscalls import ObjectData
 r={'outcome':'fail','task':'KRN-039','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'commands':[],'checks':[],'parents':{},'full_kernel_qualified':False,'full_crypto_qualified':False,'native_device_qualified':False,'guest_executed':False}
 def check(n,ok,**d):
  r['checks'].append(dict(name=n,passed=bool(ok),**d))
  if not ok:raise ValueError(n)
 def run(argv,label,expected=0):
  v=runmod.run(argv,out,label,30,256);r['commands'].append(v)
  if expected==0:check('command-'+label,v['exit_code']==0 and v['outcome']=='pass')
  else:check('actual-strict-negative',v['exit_code']!=0 and v['outcome']=='fail' and 'error: incompatible function pointer types' in (out/(label+'.log')).read_text() and not(out/'rejected.o').exists())
  return v
 try:
  state=load(m/'state/lab.json');task=next(t for t in state['tasks'] if t['id']=='KRN-039');e=next(e for e in state['experiments'] if e['id']==a.experiment);check('active-owned-prospective-plan',task['owner']==e['owner']=='codex-team-kernel-des-20261105-ci' and task['status']=='in_progress' and e['task']=='KRN-039' and e['status']=='planned');r['planning_record']=e
  r['source_inputs']={str(x.relative_to(WT)):sha(x) for x in [Path(__file__),WT/'src/platform/crypto/des/kernel_provider.c',WT/'src/platform/crypto/des/kernel_provider.h',WT/'fixtures/public/xnu-kernel-des/host_publication.c',WT/'fixtures/public/xnu-kernel-des/reject_wrong_callback.c']}
  native=load(a.native);check('passed-native-parent',native['outcome']=='pass');r['parents']['native']={'path':str(a.native.relative_to(m)),'sha256':sha(a.native)}
  for path,digest in native['sha256'].items():check('retained-artifact-'+path,sha(m/path)==digest)
  rows={x['id']:x for x in native['components']};des=WT/'src/platform/crypto/des';fixture=WT/'fixtures/public/xnu-kernel-des'
  for row in rows.values():check('retained-object-'+row['id'],sha(m/row['output'])==row['output_sha256'])
  helper=rows['component/des-kernel-provider'];old=ObjectData(m/helper['output']);argv=list(helper['argv']);argv[argv.index('-o')+1]=str(out/'matched-helper.o');argv[argv.index('-MF')+1]=str(out/'matched-helper.d');run(argv,'matched-helper-strict');new=ObjectData(out/'matched-helper.o')
  for obj in [old,new]:check('actual-helper-layout',obj.value('_s24_kernel_des_layout','<16Q')==(48,40,8,8,16,16,256,768,144,400,4,16,24,32,16,24))
  section=lambda o:o.sections[o.named['_s24_kernel_des_prepare']['section']-1]
  b,c=section(old),section(new);check('native-only-layout-guard-code-identical',old.data[b['offset']:b['offset']+b['size']]==new.data[c['offset']:c['offset']+c['size']])
  helper=dict(helper,source_sha256=sha(des/'kernel_provider.c'),output=str((out/'matched-helper.o').relative_to(m)),output_sha256=sha(out/'matched-helper.o'),argv=argv);rows[helper['id']]=helper
  bad=list(argv);bad[bad.index(str(des/'kernel_provider.c'))]=str(fixture/'reject_wrong_callback.c');bad[bad.index('-o')+1]=str(out/'rejected.o');bad[bad.index('-MF')+1]=str(out/'rejected.d');run(bad,'reject-wrong-callback',1)
  modeproof=[]
  for t in [0,1]:
   for d in [0,1]:
    suffix=('tdes' if t else 'des')+('_decrypt' if d else '_encrypt')
    for kind in ['ecb','cbc']:
     name='_s24_kernel_'+('tdes' if t else 'des')+'_'+kind+('_decrypt' if d else '_encrypt');size=400 if t else 144
     check('actual-mode-fields-'+name,new.value(name,'<2Q')==(size,8));callbacks=[new.relocation(name,x) for x in [16,24]]
     check('typed-real-local-callbacks-'+name,all(x['section']>0 for x in callbacks));check('unsupported-optional-field-'+name,new.value(name,'<Q',32)==(0,))
     if kind=='ecb':check('unknown-implementation-'+name,new.value(name,'<I',40)==(0,))
     modeproof.append({'name':name,'size':size,'block_size':8,'callbacks':callbacks,'storage':new.sections[new.named[name]['section']-1]})
  r['public_modes']=modeproof
  base=load(m/native['baseline_graph']['path']);graph=base['objects'];lookup={x['id']:x for x in graph}
  cc=lookup['osfmk/cc_clear.o'];ccobj=ObjectData(m/cc['output']);symbol=ccobj.named['_cc_clear'];check('existing-real-global-cc-clear',symbol['kind']==0x0f and sha(m/cc['source'])==cc['source_sha256'] and sha(m/cc['output'])==cc['output_sha256'])
  r['clear_provider']={**cc,'symbol':symbol,'declaration':str(m/'references/apple-xnu/EXTERNAL_HEADERS/corecrypto/cc.h'),'declaration_sha256':sha(m/'references/apple-xnu/EXTERNAL_HEADERS/corecrypto/cc.h'),'license_limit':'Existing selected source mixed Apple notices retained; no implementation copied or redistributed by this task.'}
  r['zeroize_provider']=next(x for x in graph if x['id']=='component/xts' or x['id']=='component/xts.o') if any(x['id'] in ['component/xts','component/xts.o'] for x in graph) else None
  esp=m/rows['bsd/esp_core.o']['output'];tool=Path('/home/egor/Android/Sdk/ndk/27.3.13750724/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-objdump');r['disassembler']={'path':str(tool),'sha256':sha(tool)}
  run([tool,'--macho','--disassemble','--reloc','--symbolize-operands',esp],'production-esp-disassembly');run([tool,'--macho','--disassemble','--reloc','--symbolize-operands',m/cc['output']],'existing-clear-provider-disassembly')
  text=(out/'production-esp-disassembly.log').read_text();proof={}
  for name,nextname in [('_esp_cbc_decrypt:','_esp_cbc_encrypt:'),('_esp_cbc_encrypt:','_esp_des_schedule:')]:
   part=text.split(name,1)[1].split(nextname,1)[0];calls=[line for line in part.splitlines() if re.search(r'\bbl\s+_cc_clear$',line)]
   check('unobserved-production-three-clear-sites-'+name,len(calls)==3 and '_kfree_ext' in part);proof[name]={'calls':calls,'disassembly_sha256':hashlib.sha256(part.encode()).hexdigest(),'disassembly':part}
  r['production_clear_codegen']=proof
  source=(m/rows['bsd/esp_core.o']['source']).read_text();part=source[source.index('\nesp_cbc_decrypt('):source.index('\nesp_auth(')];check('source-length-pointer-order',part.count('cc_clear(sizeof(iv), iv);')==2 and part.count('cc_clear(blocklen, sbuf);')==2 and part.count('return EINVAL;')==4);r['pre-IV-exclusions']='Initial unsupported IV length and DIAGNOSTIC block length exits in both functions precede IV copy; four direct source returns remain. Six post-IV validation errors join common cc_clear cleanup.'
  provider=(m/rows['osfmk/mc_provider.o']['source']).read_text();check('real-preparation-before-sha-and-register',provider.index('s24_kernel_des_prepare()')<provider.index('mc_funcs.ccsha256_di = ccsha256_di();')<provider.index('register_crypto_functions(&mc_funcs)'))
  replacements={k:rows[k] for k in ['osfmk/mc_provider.o','libkern/corecrypto_des.o','bsd/esp_core.o']};additional=[rows[k] for k in ['component/des-kernel-provider','component/des','component/mbedtls-des']];newgraph=[replacements.get(row['id'],row) for row in graph]+additional
  check('coherent988-unique-identities',len(newgraph)==len({x['id'] for x in newgraph})==988)
  closure={}
  for target in ['_mbedtls_platform_zeroize','_cc_clear','_memset_s']:
   matches=[]
   for row in graph:
    if row['id'].startswith('component/') or row['id'] in ['osfmk/cc_clear.o','osfmk/memset_s.o']:
     o=ObjectData(m/row['output'])
     if target in o.named and o.named[target]['kind']==0x0f:matches.append({'id':row['id'],'output':row['output'],'sha256':row['output_sha256'],'symbol':o.named[target]})
   check('unique-retained-real-provider-'+target,len(matches)==1);closure[target]=matches
  r['import_provider_map']=closure
  manifest={'objects':newgraph,'object_count':988,'no_full_link':True,'table_observation':native['table_observation'],'remaining_private_ARM_exports':37,'full_provider_startup_executed':False};(out/'coherent-component-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');r['coherent_component_manifest']={'path':str((out/'coherent-component-manifest.json').relative_to(m)),'sha256':sha(out/'coherent-component-manifest.json')}
  if a.host:
   host=Path('/home/egor/.local/bin/clang');cap=load(m/'docs/procedures/crypto-xts/qualified-evidence.json');hp=cap['tools']['host'];check('known-qualified-host-compiler',sha(host)==hp['sha256']);r['host_compiler']={'path':str(host),'sha256':sha(host),'runtime_hashes':hp['runtime_hashes']}
   for path,digest in hp['runtime_hashes'].items():check('actual-sanitizer-runtime-'+path,sha(path)==digest)
   vectors=m/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/regenerated';r['vectors']={str(x.relative_to(m)):sha(x) for x in [vectors/'vectors.h',vectors/'vectors.json']}
   flags=['--target=x86_64-unknown-linux-gnu','-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-sanitize-recover=all','-include','sys/types.h','-I'+str(des),'-I'+str(des/'vendor/include'),'-I'+str(des/'vendor/library'),'-I'+str(vectors),'-I'+str(m/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu/libkern'),'-I'+str(m/'references/apple-xnu/EXTERNAL_HEADERS'),'-DMBEDTLS_CONFIG_FILE="s24_des_profile.h"']
   text=(des/'des.c').read_text();start='int s24_des_ecb_descriptor(struct ccmode_ecb *m,int t,int d) {return make_ecb(m,t,d);}'
   check('unique-real-factory-gate-injection',text.count(start)==1);gated=out/'gated-factory.c';gated.write_text(text.replace(start,'extern void kdes_factory_gate(void);\nint s24_des_ecb_descriptor(struct ccmode_ecb *m,int t,int d) {kdes_factory_gate();return make_ecb(m,t,d);}'))
   mismatch=out/'mismatch-factory.c';needle='r.size=bytes((unsigned)t);r.block_size=8;r.impl=CC_IMPL_UNKNOWN;';check('unique-size-mismatch-injection',text.count(needle)==1);mismatch.write_text(text.replace(needle,needle+'r.size+=16; /* test-only factory metadata fault */'))
   drpath=m/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/evidence.json';dr=load(drpath);check('accepted-DES-host-parent',dr['outcome']=='pass');r['parents']['DES-host']={'path':str(drpath.relative_to(m)),'sha256':sha(drpath)}
   primitive=drpath.parent/'host-des.o';key=str(primitive.relative_to(m));check('accepted-host-primitive',sha(primitive)==dr['artifact_hashes'][key])
   shared=m/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2';shared_objects=[shared/'host-adapter.o',shared/'host-aes.o']
   for path in shared_objects:check('accepted-host-zeroizer-dependency-'+path.name,sha(path)==dr['zeroizer_dependency']['objects'][str(path)])
   r['retained_host_objects']={str(x):sha(x) for x in [primitive,*shared_objects]}
   for label,path in [('helper',des/'kernel_provider.c'),('gated',gated),('mismatch',mismatch)]:run([host,*flags,'-c',path,'-o',out/('host-'+label+'.o')],'host-compile-'+label)
   for label,extra in [('publication',[]),('mismatch',['-DKDES_FACTORY_MISMATCH'])]:
    run([host,*flags,*extra,'-c',fixture/'host_publication.c','-o',out/('host-'+label+'-main.o')],'host-compile-'+label+'-main')
    run([host,'--target=x86_64-unknown-linux-gnu','-fsanitize=address,undefined','-fno-sanitize-recover=all','-pthread','-Wl,--threads=1',out/'host-helper.o',primitive,*shared_objects,out/('host-'+('gated' if label=='publication' else 'mismatch')+'.o'),out/('host-'+label+'-main.o'),'-o',out/('host-'+label)],'host-link-'+label)
    run([out/('host-'+label)],'host-run-'+label);check('actual-'+label+'-pass','KDES PUBLICATION PASS' in (out/('host-run-'+label+'.log')).read_text())
  r['outcome']='pass'
 except Exception as error:r['error']=repr(error)
 finally:
  r['resource_admission_wait_seconds']=runmod.RESOURCE_WAIT_USED;r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['sha256']={str(x.relative_to(m)):sha(x) for x in out.rglob('*') if x.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n')
 print(json.dumps({k:r.get(k) for k in ['outcome','error']},indent=2));return 0 if r['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
