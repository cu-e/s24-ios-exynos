#!/usr/bin/env python3
"""Independent read-only final owner receipt binding; no compiler/test/guest."""
import datetime,hashlib,json,os,subprocess,sys,traceback
from pathlib import Path
sys.dont_write_bytecode=True
from macho import Object
ROOT=Path(__file__).resolve().parents[3];MAIN=ROOT.parents[1];IMPL=MAIN/'worktrees/krn-039-20261105';TIP='b1ae6207dea930edab8536b314b844fc25a0cd9e';SOURCE='8c3797d62efe6a800b9daa48fa01d8008b25b691'
OUT=ROOT/'artifacts/rev-kernel-des/20261106-receipt1';OUT.mkdir(parents=True,exist_ok=False);(OUT/'receipt_audit.py').write_bytes(Path(__file__).read_bytes());(OUT/'macho.py').write_bytes((ROOT/'docs/reviews/krn-039/macho.py').read_bytes());commands=[]
ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0','PYTHONDONTWRITEBYTECODE':'1','LC_ALL':'C'}
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def command(argv,label):
 a=OUT/(label+'.stdout');b=OUT/(label+'.stderr')
 with a.open('xb') as f,b.open('xb') as g:r=subprocess.run(list(map(str,argv)),cwd=ROOT,env=ENV,stdout=f,stderr=g,timeout=20)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str(a.relative_to(MAIN)),stderr=str(b.relative_to(MAIN)),environment_overrides={k:ENV[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','PYTHONDONTWRITEBYTECODE','LC_ALL']}));assert r.returncode==0;return a.read_bytes()
report=dict(kind='source-review',origin='local-host',outcome='fail',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),commit=SOURCE,metadata_commit=TIP,experiment='REVKDES-004',commands=commands,compiler_executed=False,test_binary_executed=False,QEMU_executed_by_reviewer=False,final_integration_review_complete=False)
try:
 ledger=read(MAIN/'state/lab.json');ex=ledger['experiments'];ex=ex.values() if isinstance(ex,dict) else ex;ex={x['id']:x for x in ex};plan=ex['REVKDES-004'];assert plan['status']=='planned' and plan['owner']=='codex-team-review-kernel-des-20261105-cl' and plan['task']=='REV-022';(OUT/'actual-plan.json').write_text(json.dumps(plan,indent=2)+'\n')
 owner=ex['KDES-001'];assert owner['owner']=='codex-team-kernel-des-20261105-ci' and owner['status']=='recorded' and owner['evidence']=='worktrees/krn-039-20261105/artifacts/kernel-des/final-binding3/evidence.json';(OUT/'owner-recorded-plan.json').write_text(json.dumps(owner,indent=2)+'\n')
 independent=ROOT/'artifacts/rev-kernel-des/20261106-final1/evidence.json';assert sha(independent)=='57f2094829c2dccf62f7ef91ab2b98e47ae8a293f7a1389f6eb25f9ebc3b1fd9';assert read(independent)['outcome']=='pass' and read(independent)['final_integration_review_complete']
 delta=command(['git','diff','--name-only',SOURCE,TIP],'metadata-only-delta').decode().splitlines();assert delta and all(p.startswith('docs/procedures/kernel-des/') for p in delta)
 qraw=command(['git','show',TIP+':docs/procedures/kernel-des/qualified-evidence.json'],'qualified-receipt');assert hashlib.sha256(qraw).hexdigest()=='16ebf407f44decbf47af0b7ab12b823d4cf352a33ce6c8db7b86310f727ebf19';q=json.loads(qraw);assert qraw==(IMPL/'docs/procedures/kernel-des/qualified-evidence.json').read_bytes()
 rawpath=MAIN/q['raw_evidence']['path'];assert sha(rawpath)==q['raw_evidence']['sha256']=='91a2f58c6b3f4133ce4d1885f94ce8252ade073690cc1306d431cedf8076ea0e';raw=read(rawpath);assert raw['outcome']=='pass' and raw['source_subject_commit']==q['source_subject_commit']==SOURCE and len(raw['checks'])==1311 and all(x['passed'] for x in raw['checks'])
 for name,h in raw['artifact_sha256'].items():assert sha(MAIN/name)==h
 receipt_reports={};count=0
 for name,row in q['reports'].items():
  path=MAIN/row['path'];assert sha(path)==row['sha256'];e=read(path);assert e['outcome']==row['outcome'];receipt_reports[name]=row
  for f,h in e.get('sha256',{}).items():assert sha(MAIN/f)==h;count+=1
  for c in e.get('commands',[]):
   if 'after' in c:assert c['after']['owned_processes']==[]
 assert receipt_reports['actual-CPU']['sha256']=='99cb37b8eba4980fecafa596caffbabbd14663d61d0e8ae9327120187892aff4'
 for path,h in raw['owned_source_hashes'].items():
  b=command(['git','show',SOURCE+':'+path],'owned-'+str(len(commands)));assert hashlib.sha256(b).hexdigest()==h and sha(IMPL/path)==h
 manifest_path=MAIN/q['coherent_component_manifest']['path'];assert sha(manifest_path)==q['coherent_component_manifest']['sha256'];objects=read(manifest_path)['objects'];assert len(objects)==len({x['id'] for x in objects})==988
 targets=set(q['strong_clear_and_zeroizer_providers'])
 for imports in raw['new_component_imports'].values():targets.update(imports)
 actual={name:[] for name in targets}
 for row in objects:
  assert sha(MAIN/row['source'])==row['source_sha256'] and sha(MAIN/row['output'])==row['output_sha256'];obj=Object(MAIN/row['output'])
  for symbol in obj.symbols:
   if symbol['name'] in targets and symbol['kind']==15 and not(symbol['desc']&0xc0):actual[symbol['name']].append(dict(id=row['id'],output=row['output'],output_sha256=row['output_sha256'],desc=symbol['desc']))
 for name,providers in actual.items():assert len(providers)==1,name
 for name,row in q['strong_clear_and_zeroizer_providers'].items():assert row['id']==actual[name][0]['id'] and row['output_sha256']==actual[name][0]['output_sha256'] and row['symbol']['desc']==actual[name][0]['desc']==0
 for imports in raw['new_component_imports'].values():
  for name,row in imports.items():assert row['id']==actual[name][0]['id'] and row['output_sha256']==actual[name][0]['output_sha256']
 for field in ['full_provider_startup_executed','full_kernel_qualified','full_crypto_qualified','private_Apple_ABI_qualified','FIPS_qualified','side_channels_qualified','native_device_qualified','kernel_MMU_qualified']:assert q[field]==raw[field]==False
 assert (q['actual_CPU']['vectors'],q['actual_CPU']['ESP_cases'],q['actual_CPU']['top_level_CHECKs'])==(1964,120,47520)
 history=[]
 for n in [1,2]:
  path=IMPL/f'artifacts/kernel-des/final-binding{n}/evidence.json';e=read(path);assert e['outcome']=='pass' and all(x['passed'] for x in e['checks']) and ('summary' not in e or 'artifacts' not in e);history.append(dict(path=str(path.relative_to(MAIN)),sha256=sha(path),bindings_passed=True,metadata_schema_rejected=True))
 for name,row in q['preserved_failed_attempts'].items():assert sha(MAIN/row['path'])==row['sha256']
 report.update(outcome='pass',summary='Final owner metadata receipt and independent six-case native/source review bind exact unchanged measured bytes; no actionable remaining bounded P0/P1/P2 and no reviewer compiler/guest',final_integration_review_complete=True,owner_qualified_receipt=dict(path='worktrees/krn-039-20261105/docs/procedures/kernel-des/qualified-evidence.json',sha256=hashlib.sha256(qraw).hexdigest(),metadata_commit=TIP),owner_raw_receipt=dict(path=str(rawpath.relative_to(MAIN)),sha256=sha(rawpath),binding_checks=1311),independent_final=dict(path=str(independent.relative_to(MAIN)),sha256=sha(independent)),metadata_only_paths=delta,owner_reports=receipt_reports,owner_report_artifact_hash_records=count,unique_strong_selected_import_providers=actual,metadata_schema_history=history,remaining_actionable_P0_P1_P2=[],checks=[dict(name=n,pass_check=True) for n in ['actual-prospective-plan-and-original-owner-recorded-receipt','metadata-only-Git-delta-over-reviewed-8c-source','qualified-and-raw-final-receipt-hashes1311checks','all-owned-source-Git-and988-source-object-identities','independent-unique-strong-symbol-and-new-import-provider-closure','six-case-raw-runtime-remains-exactly-reviewed99cb','prior-metadata-schema-and-native-guest-history-preserved','all-native-private-fullkernel-FIPS-gates-still-false']])
except Exception as error:report.update(error=repr(error),traceback=traceback.format_exc())
report['artifacts']=[str(x.relative_to(MAIN)) for x in sorted(OUT.rglob('*')) if x.is_file() and x.name!='evidence.json'];report['sha256']={str(x.relative_to(MAIN)):sha(x) for x in sorted(OUT.rglob('*')) if x.is_file() and x.name!='evidence.json'};(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:report.get(k) for k in ['outcome','error','final_integration_review_complete']}));raise SystemExit(report['outcome']!='pass')
