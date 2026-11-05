#!/usr/bin/env python3
"""Read-only pre-guest source/assertion/object recheck; no compiler or guest."""
import collections,datetime,hashlib,json,os,re,subprocess,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from macho import Object
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];IMPL=MAIN/'worktrees/krn-039-20261105';TIP='8c3797d62efe6a800b9daa48fa01d8008b25b691';XNU='c54f35ca767986246321eb901baf8f5ff7923f6a';OVERFLOW='ff7fc8d6b8edd19ce10220fd26821c69ce988fc8';PROFILE='0ceb428dd3e0b83c203f6e5ab97e22f7e6999575'
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'};OUT=ROOT/'artifacts/rev-kernel-des'/os.environ.get('S24_REVKDES_ARCH_RUN','20261106-arch2');OUT.mkdir(parents=True,exist_ok=False)
for n in ['arch_audit.py','macho.py']:(OUT/n).write_bytes((ROOT/'docs/reviews/krn-039'/n).read_bytes())
commands=[]
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def save(p,data):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
def git(repo,spec,label):
 argv=['git','-C',str(repo),'show',spec];a=OUT/(label+'.stdout');b=OUT/(label+'.stderr')
 with a.open('xb') as f,b.open('xb') as g:r=subprocess.run(argv,cwd=ROOT,env=ENV,stdout=f,stderr=g,timeout=20)
 commands.append(dict(argv=argv,cwd=str(ROOT),exit_code=r.returncode,stdout=str(a.relative_to(MAIN)),stderr=str(b.relative_to(MAIN)),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE','LC_ALL']}));assert r.returncode==0;return a.read_bytes()
def sites(text,word):
 out=[]
 for m in re.finditer(r'\b'+word+r'\(',text):
  start=text.rfind('\n',0,m.start())+1
  if text[start:m.start()].lstrip().startswith('#'):continue
  at=m.end();depth=1;end=at
  while depth:
   if text[end]=='(':depth+=1
   elif text[end]==')':depth-=1
   end+=1
  out.append(dict(line=text.count('\n',0,m.start())+1,expression=text[at:end-1]))
 return out
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commit=TIP,experiment='REVKDES-003',commands=commands,compiler_executed=False,test_binary_executed=False,QEMU_executed=False,pre_guest_assertion_review_complete=False,final_integration_review_complete=False)
try:
 ledger=read(MAIN/'state/lab.json');ex=ledger['experiments'];ex=ex.values() if isinstance(ex,dict) else ex;plan=next(x for x in ex if x['id']=='REVKDES-003');assert plan['status']=='planned' and plan['task']=='REV-022' and plan['owner']=='codex-team-review-kernel-des-20261105-cl';save(OUT/'actual-plan.json',json.dumps(plan,indent=2).encode()+b'\n')
 files={}
 for i,name in enumerate(['fixtures/public/xnu-kernel-des/esp_fixture.c','fixtures/public/xnu-kernel-des/guest.c','docs/procedures/kernel-des/execute_caller.py','docs/procedures/kernel-des/prepare_caller.py']):
  raw=git(ROOT,TIP+':'+name,'frozen-'+str(i));save(OUT/'frozen'/name,raw);files[name]=raw
 fixture=files['fixtures/public/xnu-kernel-des/esp_fixture.c'].decode();guest=files['fixtures/public/xnu-kernel-des/guest.c'].decode();runner=files['docs/procedures/kernel-des/execute_caller.py'].decode()
 original_guest=git(ROOT,PROFILE+':fixtures/public/xnu-kernel-des/guest.c','before-overflow');fixed_guest=git(ROOT,OVERFLOW+':fixtures/public/xnu-kernel-des/guest.c','after-overflow')
 expected=original_guest.replace(b'e->ecb(ek,(size_t)-1/8+1,out,out)==CCERR_PARAMETER',b'e->ecb(ek,(size_t)-1/8+1,out,out)==CCERR_OVERFLOW').replace(b'c->cbc(ck,iv,(size_t)-1/8+1,out,out)==CCERR_PARAMETER',b'c->cbc(ck,iv,(size_t)-1/8+1,out,out)==CCERR_OVERFLOW');assert expected==fixed_guest==guest.encode()
 selected={}
 for i,name in enumerate(['bsd/netinet6/ipsec.h','bsd/netinet6/esp.h','bsd/sys/mbuf.h','bsd/sys/errno.h','EXTERNAL_HEADERS/corecrypto/cc_error.h','EXTERNAL_HEADERS/corecrypto/ccmode.h','EXTERNAL_HEADERS/corecrypto/ccdes.h']):
  raw=git(MAIN/'references/apple-xnu',XNU+':'+name,'selected-'+str(i));save(OUT/'selected-xnu'/name,raw);selected[name]=raw.decode()
 ipsec=selected['bsd/netinet6/ipsec.h'];assert '#if defined(__ARM__)' in ipsec and '#define IPSEC_IS_P2ALIGNED(p)        1' in ipsec and '#define IPSEC_GET_P2UNALIGNED_OFS(p) 0' in ipsec
 native=read(ROOT/'artifacts/rev-kernel-des/20261106-native4/evidence.json');assert native['outcome']=='pass' and not native['final_integration_review_complete']
 capsule=IMPL/'artifacts/kernel-des/caller-candidate6/evidence.json';assert sha(capsule)=='ff28978367b9c2fafc6660042d60308f5617fc52a59761d8f03db0108d462366';p=read(capsule);assert p['outcome']=='pass' and p['guest_images_ready'] and not p['guest_executed']
 for name,h in p['sha256'].items():assert sha(MAIN/name)==h,name
 for name,h in p['source_inputs'].items():assert hashlib.sha256(files[name] if name in files else git(ROOT,TIP+':'+name,'other-'+str(len(commands)))).hexdigest()==h,name
 original=read(IMPL/'artifacts/kernel-des/caller-candidate3/evidence.json');unchanged=[]
 assert original['retained_components']==p['retained_components']
 for row in p['retained_components']:assert sha(MAIN/row['output'])==row['output_sha256'];unchanged.append(row['id'])
 rows=p['fixture_components'];compile_commands=[c for c in p['commands'] if '-c' in c['argv']];assert len(compile_commands)==2
 layouts={};policy={};sources={}
 for row in rows:
  assert sha(MAIN/row['source'])==row['source_sha256'] and sha(MAIN/row['output'])==row['output_sha256']
  label=Path(row['output']).stem
  if label in ['esp-patched','esp-original']:
   obj=Object(MAIN/row['output']);policy[label]=obj.read('_kdes_esp_alignment_policy','<4Q');layouts[label]=obj.read('_kdes_esp_record_layout','<9Q');assert policy[label]==(1,0,4,1) and layouts[label]==(256,8,216,8,224,80,24,16,88)
   assert any(str(MAIN/row['output'])==c['argv'][c['argv'].index('-o')+1] and str(MAIN/row['source']) in c['argv'] for c in compile_commands)
   text=(MAIN/row['source']).read_text();assert text.endswith(fixture);assert '#define IPSEC_IS_P2ALIGNED' not in text and '#undef IPSEC_IS_P2ALIGNED' not in text
   assert '-D__ARM__' not in row['argv'] and '-arch' in row['argv'] and row['argv'][row['argv'].index('-arch')+1]=='arm64';sources[label]=text
  else:
   before=next(x for x in original['fixture_components'] if Path(x['output']).stem==label);assert before['output_sha256']==row['output_sha256'];unchanged.append(label)
 assert len(layouts)==2
 # Match all corrected fixture source predicates to the actual selected source paths.
 required=['expected_split=(unsigned)(fragmented==1)','expected_split=(unsigned)!IPSEC_IS_P2ALIGNED(head->m_data+16)','expected_direct_unaligned=!expected_split','saw_raw_unaligned|=((uintptr_t)sp&3)!=0','block_calls==algorithm_failure&&allocations==algorithm_failure','allocations==allocation_failure&&block_calls==allocation_failure-1','FASSERT(!allocations&&!block_calls)','FASSERT(saw_split==expected_split)','FASSERT(saw_raw_unaligned==expected_direct_unaligned)','FASSERT(saw_head_alias==(unsigned)(fragmented!=1))','FASSERT(saw_tail_alias&&saw_distinct_tail)','FASSERT(observed_iv==1&&clear_calls==(scratch_failure||validation?1U:2U))','FASSERT(observed_scratch==(scratch_failure||validation?0U:2U))']
 for text in required:assert text in fixture,text
 assert fixture.index('unsigned expected_split=')<fixture.index('int result=decrypt?') and fixture.count('/* KDES_ORIGINAL_STATUS_ASSERT */')==1
 assert "len(original_markers)==1 and 'FASSERT(result=='" in runner
 markers=[i for i,l in enumerate(sources['esp-original'].splitlines(),1) if '/* KDES_ORIGINAL_STATUS_ASSERT */' in l];assert len(markers)==1 and 'FASSERT(result==' in sources['esp-original'].splitlines()[markers[0]-1]
 vec=read(MAIN/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3/regenerated/vectors.json')['vectors'];admitted=[v for v in vec if len(bytes.fromhex(v['key'])) in [8,24]];assert len(admitted)==1964
 vector_checks=sum(2*((11+len(bytes.fromhex(v['pt']))//8) if v['iv'] else (9+2*(len(bytes.fromhex(v['pt']))//8))) for v in admitted)
 helpers_contracts=352*2+4*11+5;esp_checks=2+12+2+108+1;startup_checks=12;total=vector_checks+helpers_contracts+esp_checks+startup_checks;assert (helpers_contracts,esp_checks,total)==(753,125,47520)
 # Documentary finite expectation table, not an allocator/network simulation or runtime result.
 matrix=[]
 for t in [0,1]:
  for decrypt in [0,1]:
   for form in [0,1,2]:
    nodes=4 if form==1 else 1
    for kind,n in [('success',0),*[('algorithm',n) for n in [1,2,3]],*[('allocation',n) for n in [1,2,3]],('scratch',1),('validation-short',1),('validation-remainder',2)]:
     early=kind in ['scratch','validation-short','validation-remainder'];blocks=3 if kind=='success' else n if kind=='algorithm' else n-1 if kind=='allocation' else 0;allocations=3 if kind=='success' else n if kind in ['algorithm','allocation'] else 0;fresh=allocations-(1 if kind=='allocation' else 0)
     matrix.append(dict(triple=t,decrypt=decrypt,form=form,kind=kind,fault=n,original_nodes=nodes,fresh_nodes=fresh,block_calls=blocks,allocations=allocations,expected_status='OK' if kind=='success' else 'ENOBUFS' if kind in ['scratch','allocation'] else 'EINVAL',IV_clears=1,scratch_clear_and_free_observations=0 if early else 2,clear_calls=1 if early else 2,stirs=int(kind=='success' and not decrypt),all_live_nodes_freed_once=True,success_source_head_alias=form!=1,success_scratch_used=form==1,success_direct_unaligned=form==2))
 assert len(matrix)==120;save(OUT/'source-derived-120-case-expectations.json',json.dumps(matrix,indent=2).encode()+b'\n')
 assertions={'fixture_FASSERT':sites(fixture,'FASSERT'),'guest_CHECK':sites(guest,'CHECK')};save(OUT/'all-assertion-sites.json',json.dumps(assertions,indent=2).encode()+b'\n')
 report.update(outcome='pass',pre_guest_assertion_review_complete=True,summary='Full frozen ARM64 fixture/runner source assertion and actual affected-object recheck passes; root may consider a new six-case lease, final runtime still pending',prepared=dict(path=str(capsule.relative_to(MAIN)),sha256=sha(capsule)),compiled_policy=policy,compiled_genuine_layout=layouts,fresh_affected_compile_commands=compile_commands,ancestor_reused_from_is_not_freshness_proof=True,unchanged_retained_components=unchanged,negative_original_marker_line=markers[0],expected_CHECK_count=dict(vector_checks=vector_checks,helpers_and_contracts=helpers_contracts,ESP=esp_checks,startup=startup_checks,total=total),documentary_expected_cases=len(matrix),assertion_site_counts={k:len(v) for k,v in assertions.items()},checks=[dict(name=n,pass_check=True) for n in ['actual-prospective-plan','frozen-fixture-and-unique-original-marker','real-ARM64-header-policy-and-actual-policy-object-values','actual-layout-capacity-width-and-one-block-destination-premises','all-alignment-coverage-status-ownership-clear-stir-stop-assertion-source-review','exact-two-overflow-enum-only-guest-repair','two-fresh-affected-TU-commands-despite-inherited-row-metadata','retained-native-backend-guest-fortify-identities','independent47520-CHECK-and120-case-accounting','no-compiler-or-guest-and-no-final-runtime-acceptance']])
except Exception as error:report.update(error=repr(error),traceback=traceback.format_exc())
report['artifacts']=[str(x.relative_to(MAIN)) for x in sorted(OUT.rglob('*')) if x.is_file() and x.name!='evidence.json'];report['sha256']={str(x.relative_to(MAIN)):sha(x) for x in sorted(OUT.rglob('*')) if x.is_file() and x.name!='evidence.json'};(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','pre_guest_assertion_review_complete','final_integration_review_complete']}));raise SystemExit(report['outcome']!='pass')
