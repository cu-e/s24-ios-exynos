#!/usr/bin/env python3
"""One-shot STR-040 dispatch by the acting coordinator (Claude, owner directive 2026-11-10).

Derived from the STR024BUILD-005 launcher; admission, lease, watchdog and cleanup logic unchanged.
"""
import datetime, fcntl, hashlib, importlib.util, json, os, signal, subprocess, sys, time
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path('/home/egor/dev/pet/s24-ios-exynos')
HERE=ROOT/'artifacts/team-coordination/20261110-claude/bsda-tail'
HERE.mkdir(parents=True,exist_ok=False)
QUEUE=ROOT/'artifacts/team-coordination/20261106-team/resource-queue.json'
CALLER=ROOT/'worktrees/str-039-e1s-native-resource-20261110/fixtures/public/e1s-native-resource-fix/native_compile.py'
CALLER_SHA='d1ecbfc1ac1afe31826997b90f9415e154d3660b3c91761a319f1bd9b240792a'
POLICY_SHA='9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'
LEASE='e1s-native-bsda-tail-20261110-claude'
PLAN_ROWS=[('str-040-e1s-native-bsd-a-tail-20261110/docs/procedures/e1s-native-objects/bsd-a-tail/plan-001/plan.json', '7dbb507caa526e0e4d843caa6369feaa9de3dbb9244ca328ea13ba9f23bc6f08')]

def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,d):
 with Path(p).open('x') as f:json.dump(d,f,indent=2);f.write('\n')
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def module(path,expected,name):
 assert sha(path)==expected
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
common=module(ROOT/'tools/build/avf_kernel_objects.py',POLICY_SHA,'claude040_common')
host=module(ROOT/'tools/build/qemu_host.py','faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99','claude040_host')
assert sha(CALLER)==CALLER_SHA
assert json.loads((ROOT/'worktrees/str-039-e1s-native-resource-20261110/docs/procedures/e1s-native-resource-fix/evidence.json').read_text())['outcome']=='pass'
plans=[];slots=[]
for path,h in PLAN_ROWS:
 p=ROOT/'worktrees'/path;assert sha(p)==h
 d=json.loads(p.read_text());assert d['executor_sha256']==CALLER_SHA and not Path(d['out']).exists()
 assert sha(d['manifest']['path'])==d['manifest']['sha256']
 plans.append((p,h,d));slots.append({**{k:d[k] for k in ['task','owner','experiment','shard']},'source_plan':str(p.relative_to(ROOT)),'source_plan_sha256':h,'actual_output':str(Path(d['out']).relative_to(ROOT)),'reviewed_executor_sha256':CALLER_SHA,'max_jobs':1,'max_owned_rss_bytes':536870912})
# No in-process alarm: GNU timeout sends cooperative TERM to the native owner;
# accepted core defers TERM across reservation/release and handles command cleanup.
report={'kind':'host-test','origin':'local-host','started_at':now(),'outcome':'inconclusive','caller_sha256':CALLER_SHA,'main_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True,env={**os.environ,'GIT_NO_LAZY_FETCH':'1','GIT_OPTIONAL_LOCKS':'0'}).strip(),'commands':[],'admission':[],'stop_reason':None,'hardware_execution':False,'acting_coordinator':'claude-e1s-native-objects-20261110-sr40 under owner directive 2026-11-10','root_watchdog':{'implementation':'/usr/bin/timeout','sha256':sha('/usr/bin/timeout'),'seconds':'min(worker whole_seconds+90,1890)','signal':'TERM','kill_after_seconds':30}}
stop=[]
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda s,f:stop.append(s))
stable=0;admission_start=time.monotonic()
while stable<3:
 s=host.sample();report['admission'].append(s)
 stable=stable+1 if host.recovered(s) else 0
 if stop or time.monotonic()-admission_start>45:
  write(HERE/'admission-failure.json',report);raise SystemExit('No stable native admission; nothing granted')
 time.sleep(1)
alloc={'schema':'project-budget-v1','id':LEASE,'policy_sha256':POLICY_SHA,'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(hours=2)).isoformat(),'max_compiler_jobs_total':6,'max_total_project_rss_bytes':6442450944,'slots':slots,'existing_work':[],'light_rss_budget_bytes':2147483648,'six_job_measurement':None}
ap=HERE/'allocation.json';write(ap,alloc);ah=sha(ap)
with (ROOT/'state/.integration.lock').open('a+') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX);q=json.loads(QUEUE.read_text());assert all(q.get(k) is None for k in ['heavy','qemu','light_compile'])
 q['heavy']={'id':LEASE,'allocation_path':str(ap.relative_to(ROOT)),'allocation_sha256':ah,'slots':slots,'granted_at':now(),'purpose':'Remaining 61 native BSD-a objects under STR-040; lease self-issued by the Claude session acting as coordinator under the owner directive of 2026-11-10, not by the Codex root coordinator; one serial compiler, 512MiB owned RSS, 6GiB project ceiling; no QEMU or phone operations.','issued_by':'claude-e1s-native-objects-20261110-sr40'}
 temp=QUEUE.with_suffix('.claude040.tmp');write(temp,q);os.replace(temp,QUEUE)
write(HERE/'grant.json',{'recorded_at':now(),'allocation_sha256':ah,'allocation_path':str(ap),'slots':slots})
children=[]
try:
 for p,h,d in plans:
  if stop:raise RuntimeError('Root cancellation before dispatch')
  approval={'schema':'project-budget-v1','reviewed_executor_sha256':CALLER_SHA,'runner_reviewed':True,'root_lease':LEASE,'root_lease_path':str(ap.relative_to(ROOT)),'root_lease_sha256':ah,'resource_queue_path':str(QUEUE.relative_to(ROOT)),'max_jobs_per_executor':1,**{k:d[k] for k in ['task','owner','experiment','shard']},'source_plan_sha256':h,'qemu_allowed':False}
  approve=HERE/(d['task']+'-approval.json');write(approve,approval)
  seconds=min(d['whole_seconds']+90,1890)
  argv=['/usr/bin/timeout','--foreground','--signal=TERM','--kill-after=30s',str(seconds)+'s',sys.executable,str(CALLER),'execute','--manifest',d['manifest']['path'],'--manifest-sha256',d['manifest']['sha256'],'--source-plan',str(p),'--source-plan-sha256',h,'--approval',str(approve),'--approval-sha256',sha(approve)]
  stdout=(HERE/(d['task']+'.stdout.json')).open('xb');stderr=(HERE/(d['task']+'.stderr.txt')).open('xb')
  proc=subprocess.Popen(argv,cwd=ROOT,stdout=stdout,stderr=stderr,start_new_session=True)
  row={'task':d['task'],'argv':argv,'identity':common.process_identity(proc.pid),'started_at':now(),'out':d['out'],'deadline_seconds':seconds}
  children.append((proc,row,stdout,stderr));report['commands'].append(row)
 write(HERE/'launched.json',report)
 with (HERE/'host-samples.jsonl').open('x') as samples:
  stopping=None
  while any(p.poll() is None for p,_,_,_ in children):
   s=host.sample();samples.write(json.dumps(s)+'\n');samples.flush()
   if stopping is None and (stop or host.pressured(s) or s['MemAvailable_bytes']<4294967296):
    report['stop_reason']='root signal' if stop else 'host memory/PSI threshold';stopping=time.monotonic()
    for p,row,_,_ in children:
     if p.poll() is None and common.process_identity(p.pid)==row['identity']:
      os.killpg(p.pid,signal.SIGTERM)
   time.sleep(1)
finally:
 # GNU timeout also provides finite deadline on each dispatched command. Do not
 # release a live/unfinished reservation, and never clean up unrelated work.
 for p,row,out,err in children:
  row['exit_code']=p.wait();row['ended_at']=now();out.close();err.close()
  ep=Path(row['out'])/'evidence.json'
  if ep.exists():
   e=json.loads(ep.read_text());row.update(evidence=str(ep),evidence_sha256=sha(ep),outcome=e.get('outcome'),objects=len(e.get('objects',[])),failure=e.get('failure'),owned_survivors=e.get('owned_survivors'))
  else:row.update(outcome='no-evidence')
 statepath=ap.with_suffix('.reservations.json');state=json.loads(statepath.read_text()) if statepath.exists() else {'entries':{}}
 table=common.process_table();survivors=[]
 # Independent fresh table; accepted method follows retained identities,
 # sessions, and descendants. It does not need a new budget reservation.
 inspector=object.__new__(common.ProjectBudget)
 for key,entry in state['entries'].items():
  survivors.extend(common.ProjectBudget.retained_processes(inspector,entry,table))
 if stop:report.update(stop_reason='root signal',cancellation_signals=list(stop))
 report.update(ended_at=now(),reservations={k:v['status'] for k,v in state['entries'].items()},owned_survivors=survivors)
 report['outcome']='pass' if len(children)==1 and all(r.get('outcome')=='pass' and r['exit_code']==0 for _,r,_,_ in children) and not survivors and not report['stop_reason'] else 'fail'
 report['released']=not survivors and all(e['status']=='complete' for e in state['entries'].values()) and all(p.poll() is not None for p,_,_,_ in children)
 write(HERE/'evidence.json',report)
 if report['released']:
  with (ROOT/'state/.integration.lock').open('a+') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX);q=json.loads(QUEUE.read_text());assert q['heavy']['id']==LEASE and q['heavy']['allocation_sha256']==ah
   q['last_heavy_wave']=q['heavy'];q['last_heavy_release']={'id':LEASE,'outcome':report['outcome'],'evidence':str((HERE/'evidence.json').relative_to(ROOT)),'evidence_sha256':sha(HERE/'evidence.json'),'owned_survivors':0};q['heavy']=None
   temp=QUEUE.with_suffix('.claude040.release.tmp');write(temp,q);os.replace(temp,QUEUE)
 if stop:
  report.update(outcome='fail',stop_reason='root signal',cancellation_signals=list(stop))
  with (HERE/'terminal-cancellation.json').open('x') as f:json.dump(report,f,indent=2)
 print(json.dumps({'outcome':report['outcome'],'released':report['released'],'commands':[{k:r.get(k) for k in ['task','exit_code','outcome','objects','failure']} for _,r,_,_ in children],'survivors':len(survivors)}),flush=True)
raise SystemExit(0 if report['outcome']=='pass' and not stop else 1)
