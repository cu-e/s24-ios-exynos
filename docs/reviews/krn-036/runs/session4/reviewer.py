#!/usr/bin/env python3
"""Continue only resource-deferred focused CTS3 checks, preserving source audit."""
import argparse,datetime,hashlib,importlib.util,json,os,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos');BASE=Path(__file__).resolve().parent
WT=ROOT/'worktrees/krn-036-20261105';OWNER='codex-team-review-cts3-20261105-ck'
def sha(p):
 with Path(p).open('rb')as f:return hashlib.file_digest(f,'sha256').hexdigest()
def load(p):return json.loads(Path(p).read_text())
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run',required=True);args=ap.parse_args();out=BASE/'runs'/args.run;out.mkdir(parents=True,exist_ok=False)
 r=dict(kind='source-review',origin='local-host',outcome='fail',task='REV-021',recorded_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),checks=[],inputs={},commands=[],reviewer_guest_runs=0)
 def check(name,ok):
  r['checks'].append(dict(name=name,passed=bool(ok)))
  if not ok:raise AssertionError(name)
 def bind(p,digest=None):
  p=Path(p);value=sha(p);r['inputs'][str(p)]=value
  check('hash-'+str(p),digest is None or value==digest);return p
 def prospective():
  state=load(ROOT/'state/lab.json');task=next(x for x in state['tasks']if x['id']=='REV-021');plan=next(x for x in state['experiments']if x['id']=='REVCTS3-001');check('prospective-active-owned-plan',task['owner']==OWNER and task['status']=='in_progress'and plan['owner']==OWNER and plan['status']=='planned'and plan['task']=='REV-021');return plan
 def child(argv,label,expected=0,seconds=15):
  prospective();v=supervisor.run(argv,out,label,seconds,256);r['commands'].append(v);check('actual-command-'+label,v['exit_code']==expected and v['outcome']==('pass'if expected==0 else'fail')and not v['after']['owned_processes']and v['peak_total_owned_rss_bytes']<=256*1024**2);return v
 try:
  (out/'prospective-plan.json').write_text(json.dumps(prospective(),indent=2)+'\n')
  parent_path=bind(BASE/'runs/session2/evidence.json','fed6eb429535882321fb5215f3db715fcc2916902448d7f445ea7741341cca07');parent=load(parent_path)
  check('exact-preserved-static-resource-deferral',parent['outcome']=='inconclusive'and parent['error'].startswith("ResourceDeferred('normative-extract:")and not parent['commands']and len(parent['checks'])==618 and all(x['passed']for x in parent['checks'])and any(x['name']=='actual-spin-timeout'for x in parent['checks']))
  for name,digest in parent['inputs'].items():bind(name,digest)
  for name,digest in parent['reviewer_source_hashes'].items():bind(BASE/'runs/session2/reviewer.py'if Path(name).name=='review.py'else name,digest)
  r['retained_source_audit']={'path':str(parent_path.relative_to(ROOT)),'sha256':sha(parent_path),'original_outcome':parent['outcome'],'source_checks':618,'source_command_count':45,'source_inputs':567,'no_compiler_or_algorithm_rerun':True}
  raw=load(WT/'artifacts/crypto-cts3/cpu-final1/evidence.json');helper=bind(raw['resource_supervisor']['path'],raw['resource_supervisor']['sha256']);spec=importlib.util.spec_from_file_location('accepted_bounded_resource',helper);supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
  # Retain successful actual extraction; the prior checker expected "swaps"
  # where the normative sentence says "are unconditionally swapped".
  extracted_path=BASE/'runs/session3/evidence.json';extracted=load(bind(extracted_path))
  check('precise-retained-extraction-only',extracted['outcome']=='fail'and extracted['error']=="AssertionError('normative-unconditional-CS3-swap')"and len(extracted['commands'])==1 and extracted['commands'][0]['exit_code']==0 and extracted['commands'][0]['outcome']=='pass'and not extracted['commands'][0]['after']['owned_processes'])
  for name,digest in extracted['inputs'].items():bind(name,digest)
  text_path=BASE/'runs/session3/nist-addendum.txt';bind(text_path,extracted['artifacts'][str(text_path.relative_to(ROOT))]);r['retained_normative_extraction']={'path':str(extracted_path.relative_to(ROOT)),'sha256':sha(extracted_path),'original_outcome':extracted['outcome'],'child_replayed':False}
  previous_admission=load(BASE/'runs/session3/normative-extract.admission.json');supervisor.RESOURCE_WAIT_USED=previous_admission['cumulative_resource_wait_seconds'];r['prior_resource_wait_seconds']=supervisor.RESOURCE_WAIT_USED
  text=text_path.read_text();check('normative-unconditional-CS3-swap',re.search(r'unconditionally\s+swapped',text)and'CBC-CS3'in text)
  corpus=load(raw['corpus_path']);chosen=list(corpus['vectors'][:6])
  for algorithm,keybytes,block,size in [(0,8,8,9),(0,8,8,16),(1,16,8,17),(1,24,8,32),(2,24,16,33),(2,32,16,64)]:chosen.append(next(v for v in corpus['vectors']if v['algorithm']==algorithm and len(v['key'])==keybytes*2 and len(v['iv'])==block*2 and len(v['pt'])==size*2 and any(bytes.fromhex(v['iv']))))
  def array(value):return'{'+','.join(str(x)for x in bytes.fromhex(value))+'}'
  lines=['#define PROBE_RECORDS 12','struct probe_record {unsigned algorithm,keybytes,block,bytes;unsigned char key[32],iv[16],pt[272],ct[272],next[16];};','static const struct probe_record probe_records[]={']
  for v in chosen:lines.append('{'+','.join([str(v['algorithm']),str(len(v['key'])//2),str(len(v['iv'])//2),str(len(v['pt'])//2),*(array(v[f])for f in ['key','iv','pt','ct','next_iv'])])+'},')
  lines.append('};');(out/'records.h').write_text('\n'.join(lines)+'\n');(out/'focused-records.json').write_text(json.dumps(chosen,indent=2)+'\n')
  source=WT/'src/platform/crypto/cts3';objects=WT/'artifacts/crypto-cts3/host-arm2';xts=ROOT/'worktrees/krn-029-20261105/artifacts/crypto-xts/final-commit2';des=ROOT/'worktrees/krn-032-20261105/artifacts/crypto-des/cpu-final3'
  link=[objects/'host-adapter.o',objects/'host-fixture.o',objects/'host-aes.o',xts/'host-adapter.o',des/'host-adapter.o',des/'host-des.o'];host=bind(raw['tools']['host']['path'],raw['tools']['host']['sha256'])
  check('focused-one-real-AES-object',sum(p.name=='host-aes.o'for p in link)==1 and not any(p.parent==xts and p.name=='host-aes.o'for p in link))
  child([host,'--target=x86_64-unknown-linux-gnu','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fno-builtin','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Wl,--threads=1','-I'+str(source),'-I'+str(out),'-I'+str(ROOT/'references/apple-xnu/EXTERNAL_HEADERS'),BASE/'focused.c',*link,'-o',out/'focused'],'focused-compile',seconds=30)
  child([out/'focused'],'focused-positive',seconds=10);child([out/'focused','--wrong-expected'],'focused-wrong-expected',expected=1,seconds=10)
  positive=(out/'focused-positive.log').read_text();negative=(out/'focused-wrong-expected.log').read_text();check('real-postwrite-error-probe-pass','REVIEW CTS3 PASS records=12'in positive and'post-real-CBC-error=all-stages'in positive and'AddressSanitizer'not in positive and'UndefinedBehaviorSanitizer'not in positive);check('wrong-expected-actual-failure','REVIEW CTS3 FAIL'in negative and'record=0 direction=0'in negative and'AddressSanitizer'not in negative)
  r['focused_checks']=int(re.search(r'checks=(\d+)',positive)[1]);r['focused_records']=12;r['outcome']='pass';r['summary']='Retained independent source/canonical/corpus/native/payload audit plus fresh bounded sanitized12-record real-CBC postwrite-error/admission probe and wrong-oracle control pass; no bounded blocking finding'
 except Exception as error:
  r['error']=repr(error)
  if 'supervisor'in locals()and isinstance(error,supervisor.ResourceDeferred):r['outcome']='inconclusive';r['summary']='Focused review resource-deferred before child; no algorithm defect inferred'
 r['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();r['reviewer_source_hashes']={str(p):sha(p)for p in [Path(__file__),BASE/'focused.c',BASE/'experiment.md']};r['artifacts']={str(p.relative_to(ROOT)):sha(p)for p in sorted(out.rglob('*'))if p.is_file()};(out/'evidence.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps({k:r.get(k)for k in ['outcome','error','focused_checks','focused_records','summary']},indent=2));return r['outcome']!='pass'
if __name__=='__main__':raise SystemExit(main())
