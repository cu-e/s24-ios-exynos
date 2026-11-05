#!/usr/bin/env python3
"""Bounded REV031 correction replay of original reviewer byte fixtures; no compile/guest."""
import argparse,hashlib,importlib.util,json,os,pathlib,resource,shutil,signal,subprocess,sys,time
from datetime import datetime,timezone
P=pathlib.Path; ap=argparse.ArgumentParser(); ap.add_argument('--main',type=P,required=True); ap.add_argument('--out',type=P,required=True); a=ap.parse_args()
resource.setrlimit(resource.RLIMIT_AS,(256<<20,256<<20)); signal.alarm(60); a.out.mkdir(parents=True,exist_ok=False); start=time.monotonic(); wt=P.cwd(); bindings={}; commands=[]
def bound(p):
 p=P(p)
 with p.open('rb') as f: h=hashlib.file_digest(f,'sha256').hexdigest()
 bindings[str(p)]=h; return h
def run(argv,name,cwd=wt):
 r=subprocess.run(argv,cwd=cwd,capture_output=True,timeout=15,env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'})
 (a.out/(name+'.stdout')).write_bytes(r.stdout); (a.out/(name+'.stderr')).write_bytes(r.stderr); commands.append({'argv':argv,'cwd':str(cwd),'exit_code':r.returncode,'stdout':str(a.out/(name+'.stdout')),'stderr':str(a.out/(name+'.stderr'))}); return r
fix=a.main/'worktrees/vm-026-alignment-20261106'; old=a.main/'worktrees/vm-026-20261106'; commit='7554b14d13040521e7f5f05ea8b856f76473ccb2'; rel='tools/build/avf_guest_boot_memory.py'; tool=fix/rel
assert bound(tool)=='acb03b68b8c9fbe4b7dd6e9f279ec98853d9a37106d79eb1d1779d76fb7e158e'
assert bound(old/rel)=='e2623a3a1aadd5dc1e3a592ff174eae36ee46eb0091bd53d90d0f4e700a86948'
r=run(['/usr/bin/git','-C',str(fix),'show',commit+':'+rel],'fix-git-bytes'); assert r.returncode==0 and r.stdout==tool.read_bytes()
assert tool.read_bytes()==(old/rel).read_bytes().replace(b"        require(any(s['va'] <= pc",b"        require(pc % 4 == 0, 'ARM64 thread entry must be four-byte aligned')\n        require(any(s['va'] <= pc",1)
metadata=fix/'docs/procedures/avf-guest-boot-memory/entry-alignment-evidence.json'; assert bound(metadata)=='23ea218e8b6f495e9b6d7ba2a63dc6b9d31bd6b71e324446a371866d6f4894e7'
r=run(['/usr/bin/git','-C',str(fix),'show','281747d47d5333214f131e9ad46b896fab674d5a:docs/procedures/avf-guest-boot-memory/entry-alignment-evidence.json'],'metadata-git-bytes'); assert r.returncode==0 and r.stdout==metadata.read_bytes()
matrix=fix/'artifacts/avf-guest-boot-memory/entry-alignment-7554b14/matrix.json'; assert bound(matrix)=='24e64d77be38f81a91a01edfa1c455a76c4e8cc3b19eeed99287a162415177e1'; m=json.loads(matrix.read_text())
for p,h in m['files'].items(): assert bound(fix/p)==h
assert len(m['commands'])==15 and len(m['cases'])==15
for c in m['commands']: assert c['exit_code']==c['expected_exit_code']
for c in m['cases']: assert bound(c['evidence'])==c['evidence_sha256']
# No repeat of the broad source matrix. Source/pin rows are identical to the reviewed baseline.
pin='fixtures/public/avf-guest-boot-memory/source-pins.json'; assert bound(fix/pin)==bound(old/pin)
spec=importlib.util.spec_from_file_location('fixed_candidate',tool); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
snapshot=a.out/'snapshot'; (snapshot/'tools/build').mkdir(parents=True); (snapshot/'fixtures/public/avf-guest-boot-memory').mkdir(parents=True)
for p in [rel,pin]: shutil.copyfile(fix/p,snapshot/p)
layout=a.out/'declared-synthetic-plan.json'; layout.write_bytes((wt/'artifacts/rev-boot-memory/20261106-cli1/declared-synthetic-plan.json').read_bytes())
cases=[]
for name,expected in [('independent-format-positive',0),('unaligned-pc-plus1',2),('unaligned-pc-plus2',2),('unaligned-pc-plus3',2),('aligned-pc-plus4',0)]:
 path=wt/'artifacts/rev-boot-memory/20261106-review2'/(name+'.xnup'); bound(path)
 try: pkg=module.payload(path); image=module.macho(path,pkg['entries']['kernel']); parser=0; error=None
 except ValueError as e: parser=2; error=str(e)
 assert parser==expected,(name,error)
 if expected: assert error=='ARM64 thread entry must be four-byte aligned'
 dest=snapshot/'artifacts/avf-guest-boot-memory'/name
 argv=[sys.executable,'-B',str(snapshot/rel),'--main',str(a.main),'--payload',str(path),'--layout',str(layout),'--out',str(dest)]
 r=run(argv,name); assert r.returncode==expected,(name,r.stdout,r.stderr)
 evidence=dest/'evidence.json'; doc=json.loads(evidence.read_text()); bound(evidence)
 assert doc['exit_code']==expected and doc['outcome']==('fail' if expected else 'pass')
 if expected: assert doc['error']==error and 'layout_preflight' not in doc
 else: assert doc['layout_preflight']=='pass' and doc['layout']['entry_physical']%4==0
 cases.append({'case':name,'expected_exit':expected,'parser_exit':parser,'cli_exit':r.returncode,'outcome':doc['outcome'],'error':error,'evidence':str(evidence)})
first=wt/'artifacts/rev-boot-memory/20261106-receipt1/evidence.json'; assert bound(first)=='aa1f3b0601d49318e326cd9225b6fe5b9b9762f65898c2d3490cafcda99daa86'
for p,h in json.loads(first.read_text())['artifact_hashes'].items():
 if P(p)==wt/'docs/reviews/vm-026/procedure.md':
  historic=run(['/usr/bin/git','show','6d8a037:docs/reviews/vm-026/procedure.md'],'original-procedure-git-bytes')
  assert historic.returncode==0 and hashlib.sha256(historic.stdout).hexdigest()==h
 else: assert bound(p)==h
for p in a.out.rglob('*'):
 if p.is_file(): bound(p)
for p in [wt/'docs/reviews/vm-026/recheck_alignment.py',wt/'docs/reviews/vm-026/procedure.md',P(sys.executable),P('/usr/bin/git')]: bound(p)
hwm=next(x for x in P('/proc/self/status').read_text().splitlines() if x.startswith('VmHWM:'))
e={'task':'REV-031','owner':'codex-review-boot-gates-20261106-eb','experiment':'REVBOOTMEM-002','kind':'host-test','origin':'local-host','outcome':'pass','recorded_at':datetime.now(timezone.utc).isoformat(),'summary':'P2-ENTRY-ALIGN resolved by exact one-line guard7554b14: same3 independent unaligned byte fixtures now reject in parser and actual CLI;2 aligned controls pass. Original failure preserved; no remaining finding in bounded source/preflight scope.','commit':commit,'prior_finding_commit':'6d8a037','prior_evidence_sha256':'aa1f3b0601d49318e326cd9225b6fe5b9b9762f65898c2d3490cafcda99daa86','producer_metadata_commit':'281747d47d5333214f131e9ad46b896fab674d5a','producer_metadata_sha256':bound(metadata),'producer_matrix_sha256':bound(matrix),'producer_matrix_files_verified':len(m['files']),'reviewer_invocation':sys.argv,'commands':commands,'cases':cases,'artifact_hashes':bindings,'artifacts':[str(first.relative_to(a.main)),str(matrix.relative_to(a.main))]+[str(P(c['evidence']).relative_to(a.main)) for c in cases],'memory':hwm,'elapsed_seconds':time.monotonic()-start,'compiler_executed':False,'qemu_executed':False,'common_checks_executed':False,'limitations':['Independent byte fixtures are synthetic format controls, not XNU.','Actual final kernel/XNUP unavailable; runtime FDT/MMU/allocator memory demand and256MiB sufficiency remain unmeasured.','No PID1/iOS/Exynos/native/privateABI qualification.','Task remains in progress for root acceptance and integrator publication/common checks.']}
(a.out/'evidence.json').write_text(json.dumps(e,indent=2)+'\n'); print(json.dumps({'outcome':'pass','case_count':len(cases),'producer_file_hashes':len(m['files']),'hashes_total':len(bindings),'seconds':e['elapsed_seconds'],'memory':hwm,'evidence':str(a.out/'evidence.json')}))
