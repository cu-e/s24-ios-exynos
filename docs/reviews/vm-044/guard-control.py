#!/usr/bin/env python3
"""Focused real-child/fresh-proc and final resource-boundary controls."""
import datetime
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
from unittest.mock import patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
TOOL=MAIN/'worktrees/vm-044-ep-20261106/tools/build/avf_kernel_objects.py'
spec=importlib.util.spec_from_file_location('guard_review',TOOL);e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
started=time.monotonic();report={'kind':'host-test','outcome':'fail','argv':[sys.executable,*sys.argv],'source_sha256':e.sha(TOOL),'checks':[],'commands':[],'compiler_started':False,'guest_started':False}


def check(name,value,**details):
    report['checks'].append({'name':name,'pass':bool(value),**details})
    if not value:raise AssertionError(name)


def reject(name,call):
    try:call()
    except (ValueError,OSError,KeyError,TypeError) as error:check(name,True,error=repr(error))
    else:check(name,False)


class Project:
    def __init__(self, label=None):
        self.temp=tempfile.TemporaryDirectory(prefix='focused-budget-',dir=HERE) if label is None else None
        self.root=Path(self.temp.name) if self.temp else HERE/'runtime'/'guard-projects'/label
        if self.temp is None:self.root.mkdir(parents=True)
        self.art=self.root/'artifacts';self.art.mkdir();self.plan=self.art/'plan.json';e.write(self.plan,{'resource_profile':e.PROJECT_PROFILE})
        self.args=types.SimpleNamespace(main=self.root,out=self.art/'execute',task='REVIEW-BOUNDARY',owner='review-eq',experiment='REVCONTEND-001',shard='security')
        self.slot={k:getattr(self.args,k) for k in ['task','owner','experiment','shard']}
        self.slot.update(source_plan='artifacts/plan.json',source_plan_sha256=e.sha(self.plan),actual_output='artifacts/execute',reviewed_executor_sha256=e.sha(TOOL),max_jobs=1,max_owned_rss_bytes=e.EXECUTOR_RSS)
        grant={'schema':e.PROJECT_PROFILE,'id':'isolated-boundary-review','policy_sha256':e.sha(TOOL),'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5)).isoformat(),'max_compiler_jobs_total':6,'max_total_project_rss_bytes':6*e.GIB,'slots':[self.slot],'existing_work':[],'light_rss_budget_bytes':2*e.GIB,'six_job_measurement':None}
        self.allocation=self.art/'allocation.json';e.write(self.allocation,grant)
        self.queue=self.root/e.RESOURCE_QUEUE;self.queue.parent.mkdir(parents=True)
        e.write(self.queue,{'heavy':{'id':grant['id'],'allocation_path':'artifacts/allocation.json','allocation_sha256':e.sha(self.allocation),'slots':[self.slot]}})
        approval={'schema':e.PROJECT_PROFILE,'reviewed_executor_sha256':e.sha(TOOL),'runner_reviewed':True,'root_lease':grant['id'],'root_lease_path':'artifacts/allocation.json','root_lease_sha256':e.sha(self.allocation),'resource_queue_path':e.RESOURCE_QUEUE,'max_jobs_per_executor':1,**{k:self.slot[k] for k in ['task','owner','experiment','shard','source_plan_sha256']},'qemu_allowed':False}
        self.b=e.project_approval(self.args,approval);self.b.reserve()
    def close(self):
        self.b.release()
        if self.temp:self.temp.cleanup()


try:
    check('exact corrected helper',e.sha(TOOL)=='fe093f7c62affab911f96b3243eef28c419ddcb8180fbd74d58fc9a7420c70df')
    p=Project()
    try:
        snapshot=p.b.sample()
        check('real PID/start/current RSS and swap observed',sum(row['pid']==os.getpid() for row in snapshot['project_processes'])==1 and snapshot['project_rss_bytes']>0 and type(snapshot['project_swap_bytes']) is int)
        saved=p.queue.read_bytes();queue=json.loads(saved);queue['heavy']['allocation_sha256']='0'*64;p.queue.write_text(json.dumps(queue))
        reject('live queue revocation still rejects',p.b.sample);p.queue.write_bytes(saved)
        saved_path=p.queue.with_name('queue-original.json');p.queue.rename(saved_path);p.queue.symlink_to(saved_path)
        try:reject('live queue symlink still rejects',p.b.sample)
        finally:p.queue.unlink();saved_path.rename(p.queue)
        original_read=Path.read_text
        def unreadable(path,*args,**kwargs):
            if path==Path(f'/proc/{os.getpid()}/status'):raise PermissionError('controlled known-owned status read error')
            return original_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',unreadable):reject('fresh known-owned status read failure propagates',p.b.sample)
    finally:p.close()
    with tempfile.TemporaryDirectory(prefix='proc-missing-',dir=HERE) as directory:
        cwd=Path(directory)/'removed';cwd.mkdir();child=subprocess.Popen(['sleep','15'],cwd=cwd,start_new_session=True)
        try:
            start=e.process_table()[child.pid]['start_ticks'];cwd.rmdir();row=e.process_table()[child.pid]
            check('deleted real cwd returns unknown while preserving PID/start',row['cwd'] is None and row['start_ticks']==start and row['executable']=='sleep')
        finally:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=2)
    supervise=e.supervisor(MAIN)
    for scenario in ['actual-final-lock-timeout','synthetic-final-violation','synthetic-final-global-rss']:
        p=Project(scenario);holder=None
        try:
            output=p.args.out;output.mkdir();sample=p.b.sample;none_calls=0
            def boundary(session=None,**kwargs):
                global none_calls,holder
                if session is None:none_calls+=1
                if session is None and none_calls==2 and scenario=='actual-final-lock-timeout':
                    ready=p.art/'holder-ready'
                    code="import fcntl,pathlib,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);pathlib.Path(sys.argv[2]).touch();time.sleep(3)"
                    holder=subprocess.Popen([sys.executable,'-c',code,str(p.b.lock_path),str(ready)],cwd='/tmp',start_new_session=True)
                    end=time.monotonic()+2
                    while not ready.exists() and time.monotonic()<end:time.sleep(.005)
                    if not ready.exists():raise RuntimeError('Actual lock holder did not start')
                result=sample(session,**kwargs)
                if session is None and none_calls==2:
                    if scenario=='synthetic-final-violation':result['violations'].append('controlled-final-violation')
                    if scenario=='synthetic-final-global-rss':result['project_rss_bytes']=6*e.GIB+1
                return result
            p.b.sample=boundary
            command=e.run_child([sys.executable,'-c','print("genuine tiny child completed")'],p.root,output,'child',supervise,timeout=3,admit=False,budget=p.b)
            report['commands'].append({'scenario':scenario,'record':command,'synthetic_final_fields':scenario!='actual-final-lock-timeout'})
            check(scenario+' fails resource qualification with genuine exit/logs retained',command['exit_code']==0 and command['outcome']=='resource-deferred' and command['stop_reason']=='project-admission' and command['after']['owned_processes']==[] and (output/'child.stdout.txt').read_text()=='genuine tiny child completed\n',final_error=command.get('project_after_error'),final_resource_error=command.get('project_after_resource_error'))
        finally:
            p.b.sample=sample
            if holder is not None:
                os.killpg(holder.pid,signal.SIGTERM);holder.wait(timeout=2)
            p.close()
    report['outcome']='pass'
except Exception as error:report['error']=repr(error)
finally:
    report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
    (HERE/'guard-control.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['checks','commands']}|{'checks':len(report['checks']),'commands':len(report['commands'])}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
