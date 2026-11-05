#!/usr/bin/env python3
"""Audit the actual eight-source VM013 history only in a disposable clone."""
import datetime,hashlib,importlib.util,json,os,resource,subprocess,sys,tempfile,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('review_controls',HERE/'controls.py');helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
FROZEN=MAIN/'worktrees/int-history-gate-20261106/tools/integration_gate.py'
HISTORY=json.loads((HERE/'vm013-history.json').read_text())
started=time.monotonic();result={'kind':'host-test','origin':'local-host','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'argv':[sys.executable,*sys.argv],'publication_common_compiler_guest_started':False,'patches':[]}
def patch_sha(root,parent,commit):
 with tempfile.TemporaryFile() as stream:
  process=subprocess.run(['git','diff','--binary','--full-index','--no-ext-diff','--no-textconv','--no-renames',parent,commit],cwd=root,env=helpers.ENV,stdout=stream,stderr=subprocess.PIPE,timeout=20)
  helpers.check(process.returncode==0,'Actual parent-to-commit raw patch read')
  stream.seek(0);return hashlib.file_digest(stream,'sha256').hexdigest()
try:
 base=helpers.git(MAIN,'rev-parse','HEAD');result['captured_main_base']=base
 with tempfile.TemporaryDirectory(prefix='rev030-actual-') as temp:
  root=Path(temp)/'primary'
  helpers.git(Path(temp),'clone','--shared','--no-checkout','--single-branch','--branch','main',str(MAIN),str(root))
  helpers.git(root,'config','user.name','Independent history review');helpers.git(root,'config','user.email','fixture@example.invalid')
  helpers.git(root,'switch','-C','main',base)
  candidate=root/'worktrees/candidate';helpers.git(root,'worktree','add','-b','candidate',str(candidate))
  sources=[r['commit'] for r in HISTORY['commits']];mapped=[]
  for source in sources:
   previous=helpers.git(candidate,'rev-parse','HEAD')
   helpers.git(candidate,'cherry-pick',source,candidate=True)
   commit=helpers.git(candidate,'rev-parse','HEAD');mapped.append(commit)
   original_parent=helpers.git(root,'rev-parse',source+'^')
   source_patch=patch_sha(root,original_parent,source);candidate_patch=patch_sha(root,previous,commit)
   helpers.check(source_patch==candidate_patch,'Independent actual source/candidate binary patch identity')
   result['patches'].append({'source':source,'candidate':commit,'source_patch_sha256':source_patch,'candidate_patch_sha256':candidate_patch})
  tip=mapped[-1]
  net=set(filter(None,helpers.git(root,'diff','--no-renames','--name-only','-z',base,tip).split('\0')));union=set()
  for commit in mapped:union.update(filter(None,helpers.git(root,'diff','--no-renames','--name-only','-z',commit+'^',commit).split('\0')))
  historical=union-net
  helpers.check(historical==set(HISTORY['exact_historical_paths']),'Exact actual historical path after preserved eight patches')
  receipt=root/'artifacts/review.json';receipt.parent.mkdir(exist_ok=True);receipt.write_text('{"temporary_actual_history_audit":true}\n')
  plan={'base_head':base,'candidate_head':tip,'candidate_worktree':'worktrees/candidate','commits':mapped,'commit_map':[{'source':a,'candidate':b} for a,b in zip(sources,mapped)],'paths':sorted(net),'historical_paths':sorted(historical),'bindings':[{'path':'artifacts/review.json','sha256':hashlib.sha256(receipt.read_bytes()).hexdigest()}]}
  fixture=type('ActualFixture',(),{'root':root,'sources':sources,'candidates':mapped,'union':sorted(union),'historical':sorted(historical)})()
  gate=helpers.load(FROZEN,'actual_frozen_gate')
  frozen=helpers.audit(gate,fixture,plan);helpers.check(frozen['accepted'],'Frozen gate rejects real VM013 history: '+str(frozen['error']))
  baseline=helpers.load(HERE/'baseline-gate.py','actual_baseline_gate')
  legacy=helpers.audit(baseline,fixture,plan);helpers.check(not legacy['accepted'] and 'unplanned path' in legacy['error'],'Baseline must reproduce real historical rejection')
  result.update(outcome='pass',plan=plan,independent_net_paths=sorted(net),independent_touched_union=sorted(union),independent_historical_paths=sorted(historical),frozen_audit=frozen,baseline_audit=legacy)
except Exception as error:result['error']=repr(error)
finally:
 usage={line.split(':')[0]:int(line.split()[1])*1024 for line in Path('/proc/self/status').read_text().splitlines() if line.startswith(('VmHWM:','VmRSS:'))}
 result.update(elapsed_seconds=round(time.monotonic()-started,3),current_image_peak_rss_bytes=usage['VmHWM'],current_rss_bytes=usage['VmRSS'],raw_rusage_maxrss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,commands=helpers.COMMANDS)
 (HERE/'actual-history-control.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({k:v for k,v in result.items() if k not in ('plan','commands','patches','frozen_audit','baseline_audit','independent_net_paths','independent_touched_union')}))
sys.exit(0 if result['outcome']=='pass' else 1)
