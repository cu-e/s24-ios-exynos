#!/usr/bin/env python3
"""One registered source-only plan,120 seconds/256MiB, owned-session cleanup."""
import hashlib,importlib.util,json,os,subprocess,time
from pathlib import Path
wt=Path(__file__).resolve().parents[4]
main=Path('/home/egor/dev/pet/s24-ios-exynos')
req=json.loads((Path(__file__).with_name('resource-v2-request.json')).read_text())
sha=lambda p:hashlib.file_digest(Path(p).open('rb'),'sha256').hexdigest()
assert sha(req['helper']['path'])==req['helper']['sha256']
pin=json.loads((main/'fixtures/public/avf-kernel-profile/inputs.json').read_text())['accepted_readonly_inputs']['tools/build/qemu_host.py']['sha256']
superpath=main/'tools/build/qemu_host.py';assert sha(superpath)==pin
spec=importlib.util.spec_from_file_location('owned_supervisor',superpath);supervise=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervise)
record=wt/'artifacts/avf-object-shards/bsd-core/resource-v2/plan-invocation-001';record.mkdir(parents=True,exist_ok=False)
cmd=req['plan_command'];start=time.monotonic();result={'argv':cmd,'started_at':supervise.now(),'timeout_seconds':120,'tree_rss_limit_bytes':268435456,'supervisor_sha256':pin,'samples':[]}
proc=None
try:
 with (record/'stdout.log').open('xb') as out,(record/'stderr.log').open('xb') as err:
  proc=subprocess.Popen(cmd,cwd=wt,stdout=out,stderr=err,start_new_session=True,env=dict(os.environ,GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',PYTHONDONTWRITEBYTECODE='1'))
  result['owned_session']=proc.pid
  print(json.dumps({'pid':proc.pid,'experiment':req['experiment']}),flush=True)
  while proc.poll() is None:
   current=supervise.sample(proc.pid)
   selfrss=int(next(l.split()[1] for l in Path('/proc/self/status').read_text().splitlines() if l.startswith('VmRSS:')))*1024
   current['wrapper_rss_bytes']=selfrss;current['total_planner_rss_bytes']=selfrss+current['owned_tree_rss_bytes'];result['samples'].append(current)
   if current['total_planner_rss_bytes']>268435456:
    result['stop_reason']='tree-rss-limit';supervise.terminate(proc);break
   if time.monotonic()-start>120:
    result['stop_reason']='deadline';supervise.terminate(proc);break
   time.sleep(.1)
  result['exit_code']=proc.wait(timeout=2)
finally:
 if proc is not None:
  remaining=supervise.sample(proc.pid)
  if remaining['owned_processes']:supervise.terminate(proc)
  result['after']=supervise.sample(proc.pid)
 result['elapsed_seconds']=time.monotonic()-start;result['ended_at']=supervise.now()
 result['peak_total_planner_rss_bytes']=max([s['total_planner_rss_bytes'] for s in result['samples']],default=0)
 (record/'invocation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='samples'}),flush=True)
