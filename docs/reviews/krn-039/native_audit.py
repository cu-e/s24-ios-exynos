#!/usr/bin/env python3
"""Independent frozen source/native/codegen review only; never compiler or guest."""
import collections,datetime,hashlib,json,os,re,struct,subprocess,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from macho import Object,branch26,cbz0
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];IMPL=MAIN/'worktrees/krn-039-20261105'
CODE='a948c6e6a0e7423158ca1829a4c9841fd0d79cc1';FOLLOW='0ceb428dd3e0b83c203f6e5ab97e22f7e6999575';XNU='c54f35ca767986246321eb901baf8f5ff7923f6a'
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}
RUN=os.environ.get('S24_REVKDES_RUN','20261106-native1');assert re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]*',RUN)
OUT=ROOT/'artifacts/rev-kernel-des'/RUN;OUT.mkdir(parents=True,exist_ok=False)
for name in ['native_audit.py','macho.py']:(OUT/name).write_bytes((ROOT/'docs/reviews/krn-039'/name).read_bytes())
commands=[];audited={}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def checked(p,h):
 p=Path(p);assert sha(p)==h,str(p);audited[str(p.relative_to(MAIN)) if p.is_relative_to(MAIN) else str(p)]=h;return p

def read(p):return json.loads(Path(p).read_text())
def save(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
def command(argv,label):
 a=OUT/(label+'.stdout');b=OUT/(label+'.stderr')
 with a.open('xb') as f,b.open('xb') as g:r=subprocess.run(list(map(str,argv)),cwd=ROOT,env=ENV,stdout=f,stderr=g,timeout=30)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str(a.relative_to(MAIN)),stderr=str(b.relative_to(MAIN)),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE','LC_ALL']}));assert r.returncode==0,label;return a.read_bytes()
def git(repo,spec,label):return command(['git','-C',repo,'show',spec],label)
def patch(raw,diff):
 original=raw.decode().splitlines(keepends=True);lines=diff.decode().splitlines(keepends=True);out=[];at=0;i=0
 while i<len(lines):
  m=re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@',lines[i])
  if not m:i+=1;continue
  begin=int(m[1])-1;assert begin>=at;out+=original[at:begin];at=begin;old=new=0;i+=1
  while i<len(lines) and not lines[i].startswith('@@'):
   line=lines[i]
   if line.startswith(('--- ','+++ ')):break
   if line[0] in [' ','-']:assert original[at]==line[1:];at+=1;old+=1
   if line[0] in [' ','+']:out.append(line[1:]);new+=1
   i+=1
  assert old==int(m[2] or 1) and new==int(m[4] or 1)
 out+=original[at:];return ''.join(out).encode()

def audit_capsule(path):
 p=Path(path);e=read(p);audited[str(p.relative_to(MAIN))]=sha(p)
 for name,h in e.get('sha256',{}).items():checked(Path(name) if Path(name).is_absolute() else MAIN/name,h)
 for c in e.get('commands',[]):
  if 'after' in c:assert not any(x['state']!='Z' for x in c['after']['owned_processes'])
 return e
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commit=CODE,followup_commit=FOLLOW,experiment='REVKDES-002',commands=commands,compiler_executed=False,test_binary_executed=False,QEMU_executed=False,final_integration_review_complete=False)
try:
 ledger=read(MAIN/'state/lab.json');ex=ledger['experiments'];ex=ex.values() if isinstance(ex,dict) else ex;plan=next(x for x in ex if x['id']=='REVKDES-002');assert plan['status']=='planned' and plan['owner']=='codex-team-review-kernel-des-20261105-cl' and plan['task']=='REV-022';save(OUT/'actual-plan.json',json.dumps(plan,indent=2).encode()+b'\n')
 names=command(['git','show','--format=','--name-only',CODE],'candidate-paths').decode().splitlines();assert len(names)==18;inputs={}
 for i,name in enumerate(names):
  raw=git(ROOT,FOLLOW+':'+name,'candidate-'+str(i));save(OUT/'candidate'/name,raw);inputs[name]=hashlib.sha256(raw).hexdigest()
 extra=['src/platform/crypto/des/des.c','src/platform/crypto/des/des.h','src/platform/crypto/des/vendor/library/des.c','src/platform/crypto/des/s24_des_profile.h']
 for i,name in enumerate(extra):
  raw=git(ROOT,FOLLOW+':'+name,'inherited-'+str(i));assert hashlib.sha256(raw).hexdigest()==sha(IMPL/name);save(OUT/'candidate'/name,raw);inputs[name]=hashlib.sha256(raw).hexdigest()
 delta=command(['git','diff','--name-only',CODE,FOLLOW],'followup-paths').decode().splitlines();assert delta==['docs/procedures/kernel-des/README.md','docs/procedures/kernel-des/handoff.md','docs/procedures/kernel-des/prepare_caller.py']
 initial=IMPL/'artifacts/kernel-des/caller-candidate1/evidence.json';checked(initial,'16a4b98aff52f2304f06f0fcc13ac969a3d234d4f4aaa91edc9dbdf0f356983d');c1=audit_capsule(initial)
 final=IMPL/'artifacts/kernel-des/caller-candidate2/evidence.json';checked(final,'9d34b6ea29cbb76f5cdc4bfecef523ed07f33b36cbc49c324dc208cb2ed21fda');candidate=audit_capsule(final)
 reports={}
 for sub in ['native-esp-clear1','native-controls4','publication-finish1','strong-clear1','production-codegen1','native-development3','caller-development4','caller-guest1']:
  reports[sub]=audit_capsule(IMPL/'artifacts/kernel-des'/sub/'evidence.json')
 native=reports['native-esp-clear1'];controls=reports['native-controls4'];pub=reports['publication-finish1'];strong=reports['strong-clear1']
 assert native['outcome']==pub['outcome']==strong['outcome']=='pass';assert controls['outcome']=='fail' and controls['error']=="ValueError('command-host-compile-publication-main')"
 assert reports['caller-guest1']['outcome']=='fail' and not any(c['accepted'] for c in reports['caller-guest1']['guest_cases'])
 for name in [CODE,FOLLOW]:assert len(command(['git','rev-parse',name],'revision-'+name[:7]).strip())==40
 manifest_path=checked(MAIN/pub['coherent_component_manifest']['path'],pub['coherent_component_manifest']['sha256']);manifest=read(manifest_path);graph={x['id']:x for x in manifest['objects']};assert len(graph)==len(manifest['objects'])==988
 base_path=checked(MAIN/native['baseline_graph']['path'],native['baseline_graph']['sha256']);base={x['id']:x for x in read(base_path)['objects']};assert len(base)==985
 replacements={'osfmk/mc_provider.o','libkern/corecrypto_des.o','bsd/esp_core.o'};added={'component/des-kernel-provider','component/des','component/mbedtls-des'};assert set(graph)==set(base)|added
 for ident,row in graph.items():
  checked(MAIN/row['source'],row['source_sha256']);checked(MAIN/row['output'],row['output_sha256'])
  if ident in base and ident not in replacements:assert row['source_sha256']==base[ident]['source_sha256'] and row['output_sha256']==base[ident]['output_sha256']
 dependencies=read(MAIN/'worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3/current-dependency-files.json');assert len(dependencies)==3156
 for name,h in dependencies.items():checked(MAIN/name,h)
 superseded=[]
 for name,h in native['component_dependency_hashes'].items():
  if sha(name)==h:checked(name,h);continue
  assert name==str(IMPL/'src/platform/crypto/des/kernel_provider.c')
  assert h==next(x for x in native['components'] if x['id']=='component/des-kernel-provider')['source_sha256']
  current=graph['component/des-kernel-provider'];assert sha(name)==current['source_sha256']==inputs['src/platform/crypto/des/kernel_provider.c']
  old_object=Object(MAIN/next(x for x in native['components'] if x['id']=='component/des-kernel-provider')['output']);new_object=Object(MAIN/current['output'])
  a=old_object.sections[old_object.named['_s24_kernel_des_prepare']['section']-1];b=new_object.sections[new_object.named['_s24_kernel_des_prepare']['section']-1]
  assert old_object.data[a['offset']:a['offset']+a['size']]==new_object.data[b['offset']:b['offset']+b['size']]
  assert old_object.read('_s24_kernel_des_layout','<16Q')==new_object.read('_s24_kernel_des_layout','<16Q')
  superseded.append(dict(path=name,predecessor_source_sha256=h,matched_strict_source_sha256=sha(name),matched_object=current['output'],native_text_and_layout_identical=True))
 # Original and corrected production ESP commands differ only in retained input/output paths.
 old_esp=next(x for x in reports['native-development3']['components'] if x['id']=='bsd/esp_core.o');new_esp=next(x for x in native['components'] if x['id']=='bsd/esp_core.o')
 def normalized(row):
  argv=list(row['argv']);argv[argv.index(str(MAIN/row['source']))]='<SOURCE>'
  argv[argv.index('-o')+1]='<OBJECT>';argv[argv.index('-MF')+1]='<DEPENDENCY>';return argv
 assert normalized(old_esp)==normalized(new_esp) and '-fno-builtin' in new_esp['argv'] and '-O2' in new_esp['argv']
 assert not any('KDES_' in x for x in new_esp['argv'])
 snapshot=strong['historical_reader_snapshot'];checked(MAIN/snapshot['path'],snapshot['sha256']);assert snapshot['sha256']==strong['reader_sha256']
 for name,h in candidate['source_inputs'].items():assert inputs[name]==h,name
 assert (IMPL/'artifacts/kernel-des/caller-candidate2/builder.py').read_bytes()==(OUT/'candidate/docs/procedures/kernel-des/prepare_caller.py').read_bytes()
 for c in controls['commands']:
  if 'reject_wrong_callback.c' in ' '.join(c['argv']):assert c['exit_code']!=0 and any('incompatible-function-pointer-types-strict' in x for x in c['argv'])
 negative=(IMPL/'artifacts/kernel-des/native-controls4/reject-wrong-callback.log').read_text();assert 'error: incompatible function pointer types' in negative and not(IMPL/'artifacts/kernel-des/native-controls4/rejected.o').exists()
 for label,count in [('publication',118),('mismatch',16)]:assert f'KDES PUBLICATION PASS checks={count} failure_line=0' in (IMPL/'artifacts/kernel-des/publication-finish1'/('run-'+label+'.log')).read_text()
 original={}
 for i,name in enumerate(['bsd/netinet6/esp_core.c','libkern/crypto/corecrypto_des.c','EXTERNAL_HEADERS/corecrypto/cc.h','osfmk/corecrypto/cc_clear.c','osfmk/kern/memset_s.c','osfmk/arm64/bzero.s','osfmk/libsa/string.h']):
  raw=git(MAIN/'references/apple-xnu',XNU+':'+name,'selected-'+str(i));save(OUT/'selected-xnu'/name,raw);original[name]=raw
 p1=(OUT/'candidate/patches/kernel-des-provider/0001-prepare-real-des-tdes-modes-and-helpers.patch').read_bytes();p2=(OUT/'candidate/patches/kernel-des-provider/0002-propagate-esp-block-errors-before-packet-publication.patch').read_bytes()
 assert patch(original['bsd/netinet6/esp_core.c'],p2)==(MAIN/graph['bsd/esp_core.o']['source']).read_bytes()
 assert patch((MAIN/base['osfmk/mc_provider.o']['source']).read_bytes(),p1)==(MAIN/graph['osfmk/mc_provider.o']['source']).read_bytes()
 assert original['libkern/crypto/corecrypto_des.c']==(MAIN/graph['libkern/corecrypto_des.o']['source']).read_bytes()
 esp_source=(MAIN/graph['bsd/esp_core.o']['source']).read_text();body=esp_source[esp_source.index('\nesp_cbc_decrypt('):esp_source.index('\nesp_auth(')]
 assert body.count('cc_clear(sizeof(iv), iv);')==body.count('cc_clear(blocklen, sbuf);')==2 and body.count('return EINVAL;')==4 and body.count('result = EINVAL;')==8
 assert body.count('m_freem(m);\n\t\tresult = ENOBUFS;\n\t\tgoto end;')==2
 assert 'void cc_clear(size_t len, void *cc_sized_by(len) dst);' in original['EXTERNAL_HEADERS/corecrypto/cc.h'].decode()
 for target,row in strong['providers'].items():
  checked(MAIN/row['source'],row['source_sha256']);checked(MAIN/row['output'],row['output_sha256']);obj=Object(MAIN/row['output']);actual=obj.strong(target);assert actual['desc']==0 and actual['kind']==15
  relpath={'_cc_clear':'osfmk/corecrypto/cc_clear.c','_memset_s':'osfmk/kern/memset_s.c','_secure_memset':'osfmk/arm64/bzero.s'}[target];assert original[relpath]==(MAIN/row['source']).read_bytes()
  if target=='_cc_clear':assert obj.direct_calls('_memset_s')
  if target=='_memset_s':assert obj.direct_calls('_secure_memset')
 esp=Object(MAIN/graph['bsd/esp_core.o']['output']);paths={};relocs={r['va']:r for r in esp.relocations(1)}
 for name,end in [('_esp_cbc_decrypt','_esp_cbc_encrypt'),('_esp_cbc_encrypt','_esp_des_schedule')]:
  sites=esp.calls(name,end,'_cc_clear');assert len(sites)==3
  for site in sites[:2]:assert esp.insn(site-8)==0xd101c3a1 and esp.insn(site-4)==0x52800200 # x1=fp-112, w0=16
  allocation=esp.calls(name,end,'_kalloc_ext');assert len(allocation)==1
  fail=cbz0(allocation[0]+8,esp.insn(allocation[0]+8));assert relocs[fail+4]['name'].startswith('_m_freem')
  assert esp.insn(fail+8)==0x528006f3 # w19=actual ENOBUFS55
  common=branch26(fail+12,esp.insn(fail+12));assert common==sites[0]-8
  assert relocs[sites[2]+20]['name']=='_kfree_ext'
  paths[name]=dict(clear_sites=sites,kalloc_site=allocation[0],scratch_null_target=fail,consuming_free_site=fail+4,IV_only_target=common,first_clear_arguments='x0=16,x1=frame-112',scratch_clear_before_free=True)
 # Old unobserved production failure is preserved, separately from observer fixture.
 old=reports['production-codegen1'];checked(old['object'],old['object_sha256']);oldobj=Object(old['object']);oldrel={r['va']:r for r in oldobj.relocations(1)};oldpaths={}
 for name,end in [('_esp_cbc_decrypt','_esp_cbc_encrypt'),('_esp_cbc_encrypt','_esp_des_schedule')]:
  call=oldobj.calls(name,end,'_kalloc_ext')[0];fail=cbz0(call+8,oldobj.insn(call+8));assert oldrel[fail+4]['name'].startswith('_m_freem');epilogue=branch26(fail+12,oldobj.insn(fail+12));assert not oldobj.calls(name,end,'_cc_clear');oldpaths[name]=dict(kalloc=call,scratch_null_target=fail,return_epilogue=epilogue,epilogue_first_words=[hex(oldobj.insn(epilogue+i*4)) for i in range(5)])
 helper=Object(MAIN/graph['component/des-kernel-provider']['output']);assert helper.read('_s24_kernel_des_layout','<16Q')==(48,40,8,8,16,16,256,768,144,400,4,16,24,32,16,24)
 private=Object(MAIN/graph['component/des']['output']);assert private.read('_s24_des_layout','<7Q')==(144,400,16,128,384,48,40)
 modes={}
 for t in ['des','tdes']:
  for kind in ['ecb','cbc']:
   for d in ['encrypt','decrypt']:
    name='_s24_kernel_'+t+'_'+kind+'_'+d;s=helper.strong(name);assert helper.read(name,'<2Q')==(400 if t=='tdes' else 144,8);assert helper.read(name,'<Q',32)==(0,)
    if kind=='ecb':assert helper.read(name,'<I',40)==(0,)
    assert 'const' in helper.sections[s['section']-1]['name'];modes[name]=[helper.pointer(name,16),helper.pointer(name,24)]
 provider=Object(MAIN/graph['osfmk/mc_provider.o']['output']);prior=Object(MAIN/base['osfmk/mc_provider.o']['output']);states=collections.Counter();added_fields=[]
 for row in native['table_observation']:
  states[row['state']]+=1
  if row['state']=='relocated':
   assert provider.pointer('_mc_funcs',row['offset'])==row['target']
   if row['field'].startswith(('ccdes_','cctdes_')):added_fields.append(row['field'])
   else:assert prior.pointer('_mc_funcs',row['offset'])==row['target']
  else:assert provider.read('_mc_funcs','<Q',row['offset'])==(0,)
 assert states=={'relocated':46,'deferred-SHA256':1,'unsupported':9} and len(added_fields)==10
 start=(MAIN/graph['osfmk/mc_provider.o']['source']).read_text();assert start.index('s24_kernel_des_prepare()')<start.index('mc_funcs.ccsha256_di = ccsha256_di();')<start.index('register_crypto_functions(&mc_funcs)')
 # The source/objects and native flags of ESP/helpers stay unchanged in candidate2.
 assert c1['retained_components']==candidate['retained_components']
 for oldrow,newrow in zip(c1['fixture_components'],candidate['fixture_components']):
  if oldrow['output'].endswith('/guest.o'):
   assert all(f in newrow['argv'] for f in ['-mgeneral-regs-only','-mstrict-align','-mno-outline-atomics'])
  else:assert oldrow['output_sha256']==newrow['output_sha256']
 frozen_fixture_bindings=[]
 for row in candidate['fixture_components']:
  source=MAIN/row['source']
  if source.is_relative_to(IMPL) and str(source.relative_to(IMPL)) in inputs:
   rel=str(source.relative_to(IMPL));assert inputs[rel]==row['source_sha256'];frozen_fixture_bindings.append(dict(path=row['source'],sha256=row['source_sha256'],commit=FOLLOW,live_worktree_not_required=True))
  else:checked(source,row['source_sha256'])
  checked(MAIN/row['output'],row['output_sha256'])
 vectors=read(MAIN/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/regenerated/vectors.json');counts=collections.Counter(len(bytes.fromhex(v['key'])) for v in vectors['vectors']);assert counts=={8:952,16:972,24:1012}
 fixture=(OUT/'candidate/fixtures/public/xnu-kernel-des/esp_fixture.c').read_text();assert 'struct mbuf fixture_pool[POOL]' in fixture and 'struct secasvar sav={0}' in fixture and 'kdes_fixture_fail' in fixture
 assert 'mbedtls_platform_zeroize(sav->sched' in fixture and 'void cc_clear(size_t n,void *p)' in fixture
 report.update(outcome='pass',summary='Independent native/source/object review passes; final guest assessment still required',source_inputs=inputs,audited_shared_inputs=audited,manifest=dict(path=str(manifest_path.relative_to(MAIN)),sha256=sha(manifest_path),objects=988,preserved_original_objects=982,baseline_objects=985,remaining_private_exports=37),strong_clear_providers=strong['providers'],production_clear_paths=paths,old_production_elision=oldpaths,publication=dict(states=dict(states),added_fields=added_fields,public_modes=modes),native_vector_key_byte_counts=dict(counts),native_admitted_vectors=counts[8]+counts[24],original_dependency_count=len(dependencies),component_dependency_count=len(native['component_dependency_hashes']),unchanged_production_ESP_argv=normalized(new_esp),strict_negative_and_matched_publication_controls=True,superseded_helper_dependency=superseded,historical_fixture_source_bindings=frozen_fixture_bindings,prior_reviewer_attempts=[dict(path=str(p.relative_to(MAIN)),sha256=sha(p),outcome=read(p)['outcome'],error=read(p).get('error')) for p in sorted((ROOT/'artifacts/rev-kernel-des').glob('20261106-native*/evidence.json')) if p.parent!=OUT],initial_guest_failure=dict(path='worktrees/krn-039-20261105/artifacts/kernel-des/caller-guest1/evidence.json',sha256=sha(IMPL/'artifacts/kernel-des/caller-guest1/evidence.json'),accepted_cases=0),checks=[dict(name=n,pass_check=True) for n in ['actual-plan-before-readonly-verification','frozen-source-and-guest-only-profile-delta','unchanged-production-ESP-profile-and3156-original-dependencies','actual-strict-signature-negative-and-sanitized-publication-controls','exact-patched-selected-source-preimages-postimages','all988-real-object-source-identities-and-preservation','raw-strong-nlist-clear-provider-and-import-chain','unobserved-raw-instruction-scratch-NULL-consuming-IV-clear-path','old-production-elision-history','actual-static46+SHA+9-and-immutable-mode-layout','genuine-fixture-records-service-boundary-and-schedule-fault','source-labeled-native8-24-key-subset-no-EDE2-claim']])
except Exception as error:report.update(error=repr(error),traceback=traceback.format_exc())
report['commands']=commands;report['artifacts']=[str(p.relative_to(MAIN)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(MAIN)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','final_integration_review_complete']}));raise SystemExit(report['outcome']!='pass')
