#!/usr/bin/env python3
"""Independent tiny real-process and live canonical-path boundary controls."""
import argparse,datetime,hashlib,importlib.util,json,os,resource,signal,subprocess,sys,tempfile,time
from pathlib import Path
from types import SimpleNamespace
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
TOOL=Path('/home/egor/dev/pet/s24-ios-exynos/worktrees/vm-037-ea-20261106/tools/build/avf_kernel_objects.py')
spec=importlib.util.spec_from_file_location('review_budget',TOOL);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)

def identity(pid):
 row=e.process_table().get(pid)
 return {key:row[key] for key in ('pid','start_ticks','session','ppid','cwd','state')} if row else None

def stop_group(pid,expected=None):
 if expected:
  row=e.process_table().get(expected['pid'])
  if not row or row['start_ticks']!=expected['start_ticks']:return
 try:os.killpg(pid,signal.SIGTERM)
 except ProcessLookupError:return
 until=time.monotonic()+1
 while time.monotonic()<until:
  if not any(r['state']!='Z' and r['session']==pid for r in e.process_table().values()):return
  time.sleep(.02)
 try:os.killpg(pid,signal.SIGKILL)
 except ProcessLookupError:pass

class Project:
 def __init__(self):
  self.temp=tempfile.TemporaryDirectory(prefix='review-budget-',dir=HERE);self.root=Path(self.temp.name)
  self.art=self.root/'artifacts';self.art.mkdir();self.out=self.art/'execute';self.out.mkdir()
  self.plan=self.art/'plan.json';self.plan.write_text(json.dumps({'resource_profile':e.PROJECT_PROFILE,'synthetic_plan':True}))
  caller=e.sha(__file__)
  self.args=SimpleNamespace(main=self.root,out=self.out,task='REVIEW-TASK',owner='review-eg',experiment='REVIEW-001',shard='synthetic-component')
  self.slot={k:getattr(self.args,k) for k in ('task','owner','experiment','shard')}
  self.slot.update(source_plan='artifacts/plan.json',source_plan_sha256=e.sha(self.plan),actual_output='artifacts/execute',reviewed_executor_sha256=caller,max_jobs=1,max_owned_rss_bytes=e.EXECUTOR_RSS)
  self.grant={'schema':e.PROJECT_PROFILE,'id':'synthetic-review-only','policy_sha256':e.sha(TOOL),'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5)).isoformat(),'max_compiler_jobs_total':6,'max_total_project_rss_bytes':6*e.GIB,'slots':[self.slot],'existing_work':[],'light_rss_budget_bytes':2*e.GIB,'six_job_measurement':None}
  self.allocation=self.art/'allocation.json';self.allocation.write_text(json.dumps(self.grant))
  self.queue=self.root/e.RESOURCE_QUEUE;self.queue.parent.mkdir(parents=True);self.queue.write_text(json.dumps({'heavy':{'id':self.grant['id'],'allocation_path':'artifacts/allocation.json','allocation_sha256':e.sha(self.allocation),'slots':[self.slot]}}))
  self.approval={'schema':e.PROJECT_PROFILE,'reviewed_executor_sha256':caller,'runner_reviewed':True,'root_lease':self.grant['id'],'root_lease_path':'artifacts/allocation.json','root_lease_sha256':e.sha(self.allocation),'resource_queue_path':e.RESOURCE_QUEUE,'max_jobs_per_executor':1,'task':self.args.task,'owner':self.args.owner,'experiment':self.args.experiment,'shard':self.args.shard,'source_plan_sha256':e.sha(self.plan),'qemu_allowed':False}
  self.b=e.project_approval(self.args,self.approval,executor_path=__file__);self.b.reserve()
 def close(self):
  try:self.b.release()
  except Exception:pass
  self.temp.cleanup()


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
 started=time.monotonic();report={'kind':'host-test','origin':'synthetic-local-resource-controls','outcome':'fail','recorded_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tool':str(TOOL),'tool_sha256':e.sha(TOOL),'argv':[sys.executable,*sys.argv],'cases':[],'compiler_guest_common_started':False}
 if report['tool_sha256']!='42f84aff5febfe4800cb0f84f4052bc98ac539766f8d4ecd7739a63d2fb7dd0d':raise ValueError('Exact frozen helper required')
 try:
  p=Project();leader=None;second=None;orphan=None
  try:
   pidfile=p.art/'orphan.pid'
   code="import pathlib,subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(9)'],cwd='/tmp');pathlib.Path(sys.argv[1]).write_text(str(p.pid))"
   leader=subprocess.Popen([sys.executable,'-c',code,str(pidfile)],cwd=p.root,start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
   leader.wait(timeout=2)
   until=time.monotonic()+2
   while time.monotonic()<until:
    if pidfile.exists() and pidfile.read_text():
     orphan=identity(int(pidfile.read_text()))
     if orphan and orphan['ppid']!=leader.pid:break
    time.sleep(.01)
   if not orphan:raise RuntimeError('Owned orphan did not become observable')
   first=p.b.sample(leader.pid);tracked_first=orphan['pid'] in {r['pid'] for r in first['project_processes']}
   second=subprocess.Popen(['sleep','9'],cwd='/tmp',start_new_session=True)
   next_sample=p.b.sample(second.pid);tracked_next=orphan['pid'] in {r['pid'] for r in next_sample['project_processes']}
   stop_group(second.pid,identity(second.pid));second.wait(timeout=2)
   released=False;release_error=None
   try:p.b.release();released=True
   except Exception as error:release_error=repr(error)
   alive=identity(orphan['pid']);alive=bool(alive and alive['state']!='Z' and alive['start_ticks']==orphan['start_ticks'])
   report['cases'].append({'name':'old-session orphan retained across new session','pass':tracked_first and tracked_next and not released,'orphan_identity':orphan,'tracked_before':tracked_first,'tracked_after_session_change':tracked_next,'release_succeeded':released,'release_error':release_error,'orphan_still_alive_after_release':alive,'first_sample':first,'next_sample':next_sample})
  finally:
   if leader:stop_group(leader.pid,orphan);leader.wait(timeout=2)
   if second:
    stop_group(second.pid,identity(second.pid));second.wait(timeout=2)
   p.close()
  for target in ['queue','allocation']:
   p=Project();path=getattr(p,target);saved=path.with_name(path.name+'.original');saved.write_bytes(path.read_bytes());path.unlink();path.symlink_to(saved.name)
   try:
    accepted=False;error=None
    try:p.b.sample();accepted=True
    except Exception as exc:error=repr(exc)
    report['cases'].append({'name':'live '+target+' symlink is rejected','pass':not accepted,'actual_accepted':accepted,'error':error,'symlink_target':saved.name})
   finally:path.unlink();saved.rename(path);p.close()
  report['outcome']='pass' if all(c['pass'] for c in report['cases']) else 'fail'
 except Exception as error:report['error']=repr(error)
 finally:
  report.update(elapsed_seconds=round(time.monotonic()-started,3),controller_memory=e.actual_controller_memory())
  args.output.write_text(json.dumps(report,indent=2)+'\n')
  print(json.dumps({k:v for k,v in report.items() if k!='cases'}|{'cases':[ {k:v for k,v in c.items() if k not in ('first_sample','next_sample')} for c in report['cases']]}))
 return 0 if report['outcome']=='pass' else 1
if __name__=='__main__':raise SystemExit(main())
