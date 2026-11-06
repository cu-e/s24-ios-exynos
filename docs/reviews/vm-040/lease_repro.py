#!/usr/bin/env python3
"""Reviewer-owned Python-only expiry seam; never a kernel admission or QEMU run."""
import copy,datetime,hashlib,importlib.util,json,os,resource,sys,time
from pathlib import Path
from types import SimpleNamespace
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
P=MAIN/'worktrees/vm-040-eh-20261106'
HERE=Path(__file__).resolve().parent

def save(p,x):p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def main():
 resource.setrlimit(resource.RLIMIT_AS,(256*1024**2,)*2)
 out=HERE/'runs/lease-expiry-1';out.mkdir(parents=True,exist_ok=False)
 r={'kind':'reviewer-host-control','QEMU_executed':False,'kernel_executed':False,'admission_bypasses_are_test_seams_only':True,'source_sha256':hashlib.sha256((P/'tools/run/avf_kernel_boot.py').read_bytes()).hexdigest(),'admission':[],'lease_checks':[],'clock_sleeps':[]}
 for i in range(3):
  if i:time.sleep(1)
  n=int(next(x for x in Path('/proc/meminfo').read_text().splitlines()if x.startswith('MemAvailable:')).split()[1])*1024
  r['admission'].append({'monotonic':time.monotonic(),'MemAvailable_bytes':n})
  if n<4*1024**3:raise RuntimeError('No child admitted below4GiB')
 spec=importlib.util.spec_from_file_location('reviewed_collector',P/'tools/run/avf_kernel_boot.py');c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
 pins=c.read_json(c.FIXTURE);supervisor=c.helper(MAIN,pins,'process')
 # All test files/queue live in owned review area. Actual source is unchanged.
 c.ROOT=out
 base=out/'artifacts/avf-kernel-boot';base.mkdir(parents=True)
 plan_path=base/'control-plan.json';run=base/'control-run'
 plan={'main':str(out),'image_id':'EXPLICIT-PYTHON-REVIEW-CONTROL-NO-IMAGE','cwd':str(run),'admission':{'descriptor':{'sha256':'a'*64}},'descriptor':{},'collector_sha256':c.digest(c.__file__),'fixture_sha256':c.digest(c.FIXTURE),'argv':[sys.executable,'-s','-c','import time; time.sleep(2)'],'layout':{},'package':{},'checked_layout':{},'combined_boot_args':''}
 save(plan_path,plan)
 epoch=datetime.datetime.now(datetime.timezone.utc);clock={'offset':0.0}
 grant={'id':'REVIEW-ONLY-NOT-A-ROOT-GUEST-LEASE','owner':c.OWNER,'task':'VM-040','protocol':c.PROTOCOL,'plan_sha256':c.digest(plan_path),'collector_sha256':c.digest(c.__file__),'image_descriptor_sha256':'a'*64,'guest_memory_mib':256,'owned_rss_limit_bytes':c.RSS_LIMIT,'deadline_seconds':c.DEADLINE,'output':str(run),'issued_at':epoch.isoformat(),'expires_at':(epoch+datetime.timedelta(seconds=2.5)).isoformat()}
 queue=out/'artifacts/team-coordination/20261106-team/resource-queue.json';queue.parent.mkdir(parents=True);save(queue,{'qemu':grant})
 original_lease=c.lease;original_own=c.own_process
 def checked_lease(main,lease_id,path,p):
  current=epoch+datetime.timedelta(seconds=clock['offset']);row={'virtual_seconds':clock['offset'],'current':current.isoformat()};r['lease_checks'].append(row)
  try:answer=original_lease(main,lease_id,path,p,current=current);row['accepted']=True;return answer
  except Exception as e:row['accepted']=False;row['error']=str(e);raise
 def controlled_sleep(seconds):
  r['clock_sleeps'].append(seconds);clock['offset']+=seconds
 class Captured(Exception):pass
 def observed_own(*args,**kwargs):
  r['before_own_process_virtual_seconds']=clock['offset'];r['expired_before_own_process']=clock['offset']>=2.5
  # Only tighten the real Python child's watchdog; no QEMU or kernel argument.
  kwargs['seconds']=min(kwargs['seconds'],2)
  record=original_own(*args,**kwargs);save(out/'owned-python-record.json',record)
  r['owned_session']=record.get('owned_session');r['signals']=record['host_signals'];r['live_owned_pids']=record['live_owned_pids'];r['stop_reason']=record['stop_reason'];r['exit_code']=record['exit_code'];raise Captured()
 # Explicit dependency seams reach the future branch without fabricating a real
 # image. Lease/collect loop/Popen/monitor/cleanup implementations stay genuine.
 c.prepare=lambda *args,**kwargs:copy.deepcopy(plan)
 c.helper=lambda main,pins,name:supervisor if name=='process'else (_ for _ in ()).throw(AssertionError('Unexpected helper'))
 c.protocol_operation=lambda *args:None
 c.lease=checked_lease;c.own_process=observed_own
 c.time=SimpleNamespace(monotonic=time.monotonic,sleep=controlled_sleep)
 try:c.collect(plan_path,grant['id'],c.Stop())
 except Captured:r['finding_reproduced']=bool(r.get('expired_before_own_process')and r.get('owned_session') and r['live_owned_pids']==[])
 except Exception as e:r['finding_reproduced']=False;r['pre_spawn_rejection_or_error']={'type':type(e).__name__,'message':str(e)}
 r['VmHWM_bytes']=int(next(x for x in Path('/proc/self/status').read_text().splitlines()if x.startswith('VmHWM:')).split()[1])*1024
 r['limitations']='Virtual lease clock/prepare/protocol path seams are explicit; only a real owned Python child may start. No admitted image, root guest lease, QEMU, guest or runtime proof.'
 save(out/'report.json',r);print(json.dumps(r,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
