#!/usr/bin/env python3
"""Bounded P2 constructor-contract closure; does not repeat original matrix."""
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];LAB=ROOT.parents[1]
RUN=os.environ.get('S24_REVAUD_LIFETIME_RUN','20261105-lifetime1');assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-audio'/RUN;OUT.mkdir(parents=True,exist_ok=False);(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
BASE='cbec42fe1921b3571f440666075ab4c69566acbb';FIX='08ec46d92ae3e4b95ecf9d56d2ac180b53183208';DOC='fff8f269d5dd6f38472b0fa6e77e1f33a2eb32a4';ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'};commands=[]
def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def run(argv,name,env=ENV):
 with (OUT/(name+'.stdout')).open('wb') as a,(OUT/(name+'.stderr')).open('wb') as b:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=env,timeout=20)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(name+'.stdout')).relative_to(LAB)),stderr=str((OUT/(name+'.stderr')).relative_to(LAB)),environment_overrides={k:env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','ASAN_OPTIONS','UBSAN_OPTIONS'] if k in env}));(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');assert r.returncode==0,(name,r.returncode)
 return (OUT/(name+'.stdout')).read_bytes()
report=dict(kind='source-review',origin='local-host',outcome='fail',summary='Bounded AUD-003 P2 initializer contract followup and legal reconstruction check',recorded_at=datetime.now(timezone.utc).isoformat(),commit=FIX,metadata_commit=DOC,original_review_commit='98ee3cf887bbb1f331b0ca278d0a5f73c7c733b2',commands=commands,DSP_executed=False,native_audio_qualified=False)
try:
 for f,name in [('pcm_host.c','core'),('pcm_host.h','header'),('test_host.c','regression')]:
  p=OUT/f;p.write_bytes(run(['git','show',FIX+':src/platform/audio/host/'+f],name))
 old=run(['git','show',BASE+':src/platform/audio/host/pcm_host.c'],'original-core');assert old==(OUT/'pcm_host.c').read_bytes()
 header=(OUT/'pcm_host.h').read_text()
 for phrase in ['Constructor, never Stop/drain/reset','fresh storage or a fully','backend access and callbacks drained','borrowed views retired','do not clone','without reading old bytes','external epoch','strictly newer than ALL prior','Never recycle epochs']:assert phrase in header,phrase
 regression=(OUT/'test_host.c').read_text();assert 'static void reconstruction(void)' in regression and 'reconstruction();' in regression
 for phrase in ['epoch_authority=41','++epoch_authority','current.serial==old.serial','pcm_host_retire(&h,&old,0)==PCM_STALE','!memcmp(before,&h,sizeof(h))','pcm_host_claim(&h,epoch_authority,0,&old)==PCM_BUSY']:assert phrase in regression,phrase
 doc=run(['git','show',FIX+':docs/procedures/audio-host/README.md'],'contract-readme').decode();assert 'retire every borrowed view' in doc and 'epoch high-water mark **outside**' in doc
 exact=run(['git','show',DOC+':docs/procedures/audio-host/evidence-lifetime.json'],'owner-evidence');expected='43bbe3ee50e2d93c0f25ff7fe33b07a845197502b73f29751163c07bb959c9d4';assert hashlib.sha256(exact).hexdigest()==expected
 e=json.loads(exact);assert e['commit']==FIX and e['outcome']=='pass'
 index=e['artifact_index'];assert sha(LAB/index['path'])==index['sha256'];entries=json.loads((LAB/index['path']).read_text())['files'];assert len(entries)==59
 for entry in entries:assert sha(LAB/entry['path'])==entry['sha256'] and (LAB/entry['path']).stat().st_size==entry['size']
 for name,h in e['owned_source_sha256'].items():assert hashlib.sha256(run(['git','show',FIX+':'+name],'owned-'+Path(name).name.replace('.','-'))).hexdigest()==h
 for key in ['prior_evidence']:
  prior=Path(e[key]);prior=prior if prior.is_absolute() else LAB/prior;assert sha(prior)==e['prior_evidence_sha256']
 # Original review measurement, wrapper and finding remain unmodified/local.
 original=ROOT/'artifacts/rev-audio/20261105-session1/evidence.json';wrapper=ROOT/'artifacts/rev-audio/20261105-session1-registration/evidence.json';w=json.loads(wrapper.read_text());assert sha(original)==w['original_runtime_evidence']['sha256']
 source=LAB/'worktrees/aud-003-20261105/artifacts/audio-host/source-session1/include/sound/samsung/abox_ipc.h';expected_header=next(x['sha256'] for x in json.loads(prior.read_text())['source_provenance']['files'] if x['path']=='include/sound/samsung/abox_ipc.h');assert sha(source)==expected_header;(OUT/'abox_ipc.h').write_bytes(source.read_bytes())
 (OUT/'lifetime.c').write_bytes((ROOT/'docs/reviews/aud-003/lifetime.c').read_bytes());cc=Path('/home/egor/.local/bin/clang').resolve();run([cc,'--version'],'compiler')
 run(['/usr/bin/time','-v',cc,'-std=c11','-Wall','-Wextra','-Werror','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',OUT,OUT/'lifetime.c',OUT/'pcm_host.c','-o',OUT/'lifetime'],'compile')
 peak=int(re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',(OUT/'compile.stderr').read_text())[1]);assert peak<=256*1024
 env={**ENV,'ASAN_OPTIONS':'halt_on_error=1:detect_leaks=1','UBSAN_OPTIONS':'halt_on_error=1'};result=json.loads(run(['/usr/bin/time','-v',OUT/'lifetime'],'legal-reconstruction',env))
 report.update(outcome='pass',summary='P2 resolved by explicit constructor/lifetime/external-epoch contract; core behavior unchanged and focused legal epoch41-to42 reconstruction rejects old lease without ownership mutation',finding_disposition=dict(severity='P2',status='resolved-by-contract-clarification',original_counterexample_preserved=True,unsupported_live_reinit_not_made_safe=True),owner_evidence=dict(sha256=expected,index_entries=len(entries),path='worktrees/aud-003-20261105/docs/procedures/audio-host/evidence-lifetime.json'),source_inputs={name:sha(OUT/name) for name in ['pcm_host.c','pcm_host.h','test_host.c','abox_ipc.h']},result=result,maximum_compiler_RSS_kib=peak,compiler=dict(path=str(cc),sha256=sha(cc)),checks=[dict(name=x,pass_check=True) for x in ['exact-core-byte-identity','explicit-fresh-retired-external-epoch-contract','actual-owner-legal-regression-source','59-real-followup-artifact-hashes','original-review-history-preserved','independent-legal-reconstruction-ASan-UBSan']])
except Exception as error:report['error']=repr(error)
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(LAB)))))
raise SystemExit(report['outcome']!='pass')
