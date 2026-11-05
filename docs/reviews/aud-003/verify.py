#!/usr/bin/env python3
"""Bounded independent ABOX source/admission/lifecycle review."""
from datetime import datetime,timezone
import hashlib,json,os,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];LAB=ROOT.parents[1];IMPL=LAB/'worktrees/aud-003-20261105';CACHE=IMPL/'artifacts/audio-host/source-session1';RUNTIME=IMPL/'artifacts/audio-host/check-final-cbec42f'
RUN=os.environ.get('S24_REVAUD_RUN','20261105-session1');assert re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',RUN)
OUT=ROOT/'artifacts/rev-audio'/RUN;OUT.mkdir(parents=True,exist_ok=False);(OUT/'verifier-executed.py').write_bytes(Path(__file__).read_bytes())
C='cbec42fe1921b3571f440666075ab4c69566acbb';D='7854ddf6deb8af7351286385d946b6588e3cb513';PIN='417484173abc2c4fa93e738ea82ad9f2e84911b1';ENV={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'};commands=[]
def sha(p):
 with Path(p).open('rb') as s:return hashlib.file_digest(s,'sha256').hexdigest()
def run(argv,label,env=ENV,negative=False):
 with (OUT/(label+'.stdout')).open('wb') as a,(OUT/(label+'.stderr')).open('wb') as b:r=subprocess.run(list(map(str,argv)),cwd=ROOT,stdout=a,stderr=b,env=env,timeout=20)
 commands.append(dict(argv=list(map(str,argv)),cwd=str(ROOT),exit_code=r.returncode,stdout=str((OUT/(label+'.stdout')).relative_to(LAB)),stderr=str((OUT/(label+'.stderr')).relative_to(LAB)),environment_overrides={k:env[k] for k in ['GIT_NO_LAZY_FETCH','GIT_OPTIONAL_LOCKS','ASAN_OPTIONS','UBSAN_OPTIONS'] if k in env}));(OUT/'commands.json').write_text(json.dumps(commands,indent=2)+'\n');assert (r.returncode!=0)==negative,(label,r.returncode)
 return (OUT/(label+'.stdout')).read_bytes()
report=dict(kind='source-review',origin='local-host',outcome='fail',summary='Independent ABOX source, width/period/pointer and ownership review including initialization lifetime counterexample',recorded_at=datetime.now(timezone.utc).isoformat(),commit=C,metadata_commit=D,commands=commands,DSP_executed=False,native_audio_qualified=False)
try:
 inputs={}
 for i,f in enumerate(['pcm_host.c','pcm_host.h','oracle.py','oracle_api.h','profile.json','check.py','source.py','test_host.c','sanitizer_controls.c']):
  name='src/platform/audio/host/'+f;p=OUT/'candidate'/f;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(run(['git','show',C+':'+name],'candidate-'+str(i)));inputs[name]=sha(p)
 e=json.loads(run(['git','show',D+':docs/procedures/audio-host/evidence.json'],'exact-evidence'));assert e['commit']==C and e['owned_source_sha256']==inputs
 run(['git','show',D+':docs/procedures/audio-host/README.md'],'exact-handoff')
 index=e['artifact_index'];assert sha(LAB/index['path'])==index['sha256'];entries=json.loads((LAB/index['path']).read_text())['files']
 for entry in entries:assert sha(LAB/entry['path'])==entry['sha256'] and (LAB/entry['path']).stat().st_size==entry['size']
 rows=e['source_provenance']['files'];tree=run(['git','-C',LAB/'references/s24-linux','ls-tree','-r',PIN,'--',*[x['path'] for x in rows]],'source-tree').decode();blobs={x.split('\t',1)[1]:x.split('\t',1)[0].split()[2] for x in tree.splitlines()};sources={}
 for row in rows:
  p=CACHE/row['path'];data=p.read_bytes();assert sha(p)==row['sha256'] and hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==row['blob_id']==blobs[row['path']]
  target=OUT/'sources'/row['path'];target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data);sources[row['path']]=sha(target)
 oracle_meta=json.loads((RUNTIME/'oracle-source.json').read_text());oracle=(RUNTIME/'oracle.c').read_text()
 for name,fragment in oracle_meta['unchanged_fragments'].items():
  assert hashlib.sha256(fragment['text'].encode()).hexdigest()==fragment['sha256'] and fragment['text'] in oracle
  assert any(fragment['text'] in (CACHE/row['path']).read_text() for row in rows)
 for text in oracle_meta['unchanged_format_initializers']:assert text in (CACHE/'sound/core/pcm_misc.c').read_text() and text in oracle
 header=OUT/'sources/include/sound/samsung/abox_ipc.h';(OUT/'abox_ipc.h').write_bytes(header.read_bytes())
 oracle=re.sub(r'#include "[^"]*abox_ipc\.h"','#include "abox_ipc.h"',oracle)
 (OUT/'source-oracle.c').write_text(oracle);(OUT/'harness.c').write_bytes((ROOT/'docs/reviews/aud-003/harness.c').read_bytes())
 cc=Path('/home/egor/.local/bin/clang').resolve();run([cc,'--version'],'compiler')
 run(['/usr/bin/time','-v',cc,'-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-O1','-g','-fno-omit-frame-pointer','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',OUT,'-I',OUT/'candidate',OUT/'harness.c',OUT/'source-oracle.c',OUT/'candidate/pcm_host.c','-o',OUT/'harness'],'compile')
 peak=int(re.search(r'Maximum resident set size \(kbytes\):\s*(\d+)',(OUT/'compile.stderr').read_text())[1]);assert peak<=256*1024
 env={**ENV,'ASAN_OPTIONS':'halt_on_error=1:detect_leaks=1:disable_coredump=1','UBSAN_OPTIONS':'halt_on_error=1'};result=json.loads(run(['/usr/bin/time','-v',OUT/'harness'],'runtime',env))
 run([OUT/'harness','fallback'],'hardware-fallback-abort',env,negative=True)
 report.update(outcome='pass',summary='Source-backed period/physical-format/pointer and ordinary Stop/fence checks passed; live initializer reset reproduces stale lease alias, requiring an explicit fresh/retired-only initializer contract',source_inputs=inputs,primary_inputs=sources,artifact_index_entries=len(entries),source_pin=PIN,maximum_compiler_RSS_kib=peak,compiler=dict(path=str(cc),sha256=sha(cc)),result=result,findings=[dict(severity='P2',file='src/platform/audio/host/pcm_host.h',line=42,issue='Initializer lifetime precondition is unstated while init resets live leases/epoch and permits old-token alias after reconstruction',implementation='pcm_host.c:71-74',reproduction='review harness live-reinit block; all public calls return success and old lease retires newly claimed slot',scope='API contract documentation; not a firmware replay exploit or native DMA measurement')],checks=[dict(name=x,pass_check=True) for x in ['exact-source-and-commit-bound-capsule-hashes','16-pinned-source-tree-blob-identities','genuine-unchanged-pointer-conversion-assignment-and-format-oracle','independent-period-container-pointer-and-prefix-cases','ordinary-Stop-fault-retirement-fence-gating','initializer-live-reset-alias-counterexample','hardware-fallback-aborts-with-no-hardware','actual-bounded-ASan-UBSan-run']])
except Exception as error:report['error']=repr(error)
report['artifacts']=[str(p.relative_to(LAB)) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'];report['sha256']={str(p.relative_to(LAB)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='evidence.json'}
(OUT/'evidence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(commands),evidence=str((OUT/'evidence.json').relative_to(LAB)))))
raise SystemExit(report['outcome']!='pass')
