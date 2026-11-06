#!/usr/bin/env python3
"""Focused SID and main-loop controls; never launches a compiler."""
import ast
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import types
from unittest.mock import patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent; MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
OLD=MAIN/'worktrees/vm-044-ep-fix1-20261106/tools/build/avf_kernel_objects.py'
NEW=MAIN/'worktrees/vm-044-ep-fix2-20261106/tools/build/avf_kernel_objects.py'
RAW=MAIN/'worktrees/vm-014-profile-v1-20261106/artifacts/avf-object-shards/libkern/profile-v1/build-001'
RUNTIME=HERE/'runtime'/'focused';RUNTIME.mkdir()
started=time.monotonic();report={'kind':'host-test','outcome':'fail','argv':[sys.executable,*sys.argv],'checks':[],'orchestration_cases':[],'compiler_started':False,'namespace_qualified':False,'boundaries':'Mocked ledger/approval/bind/namespace boundaries exercise actual main dispatch. No genuine source CLI admission or fresh compilation is claimed. Resume parses existing genuine AF193 Mach-O and dependencies under a synthetic schema wrapper, never modifies originals.'}


def module(path):
    spec=importlib.util.spec_from_file_location('focused_subject',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


e=module(NEW)


def check(name,value,**details):
    report['checks'].append({'name':name,'pass':bool(value),**details})
    if not value:raise AssertionError(name)


def rejected(name,callback):
    try:callback()
    except (ValueError,OSError,KeyError,TypeError) as error:check(name,True,error=repr(error))
    else:check(name,False)


class Project:
    def __init__(self,label='sid-project'):
        self.root=RUNTIME/label;self.root.mkdir();art=self.root/'artifacts';art.mkdir()
        plan=art/'plan.json';e.write(plan,{'resource_profile':e.PROJECT_PROFILE})
        self.args=types.SimpleNamespace(main=self.root,out=art/'execute',task='FOCUSED-SID',owner='eq-control',experiment='REVCONTEND-002',shard='security')
        slot={k:getattr(self.args,k) for k in ['task','owner','experiment','shard']}
        slot.update(source_plan='artifacts/plan.json',source_plan_sha256=e.sha(plan),actual_output='artifacts/execute',reviewed_executor_sha256=e.sha(NEW),max_jobs=1,max_owned_rss_bytes=e.EXECUTOR_RSS)
        grant={'schema':e.PROJECT_PROFILE,'id':'focused-synthetic-only','policy_sha256':e.sha(NEW),'expires_at':(datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5)).isoformat(),'max_compiler_jobs_total':6,'max_total_project_rss_bytes':6*e.GIB,'slots':[slot],'existing_work':[],'light_rss_budget_bytes':2*e.GIB,'six_job_measurement':None}
        allocation=art/'allocation.json';e.write(allocation,grant)
        queue=self.root/e.RESOURCE_QUEUE;queue.parent.mkdir(parents=True);e.write(queue,{'heavy':{'id':grant['id'],'allocation_path':'artifacts/allocation.json','allocation_sha256':e.sha(allocation),'slots':[slot]}})
        approval={'schema':e.PROJECT_PROFILE,'reviewed_executor_sha256':e.sha(NEW),'runner_reviewed':True,'root_lease':grant['id'],'root_lease_path':'artifacts/allocation.json','root_lease_sha256':e.sha(allocation),'resource_queue_path':e.RESOURCE_QUEUE,'max_jobs_per_executor':1,**{k:slot[k] for k in ['task','owner','experiment','shard','source_plan_sha256']},'qemu_allowed':False}
        self.b=e.project_approval(self.args,approval);self.b.reserve()


def orchestration(tool,label,scenario):
    subject=module(tool);out=RUNTIME/label;fake_main=out/'synthetic-main'
    original_plan=json.loads((RAW/'execution-plan.json').read_text())
    plan=copy.deepcopy(original_plan)
    raw=json.loads((RAW/'evidence.json').read_text())
    witness=next(row for row in raw['objects'] if row['id']=='libkern/OSKext.cpo')
    old=subject.load(witness['record'],witness['record_sha256'])
    selected=next(row for row in plan['selected'] if row['id']==old['id'])
    plan['selected']=[selected,next(row for row in plan['selected'] if row['id']!=old['id'])]
    if scenario=='resume-single':plan['selected']=[selected]
    inputs={'roots':[],'absent_search_roots':[],'files':old['dependencies']}
    calls=[];popen=[]
    class Budget:
        rss_limit=subject.EXECUTOR_RSS
        source_plan=plan
        def reserve(self):pass
        def release(self):pass
    def owned(args):
        out.mkdir();fake_main.mkdir();args.ownership_binding={'host_control_only':True,'mocked_ledger_and_admission':True,'fresh_compilation':False};return out
    def approval(args):args.project_budget=Budget();return {'host_control_only':True,'not_a_root_grant':True}
    def bind(args,path):
        subject.write(path/'input-bindings.json',{'host_control_only':True,**inputs});return plan,inputs,subject.Digests()
    actual_load_project=subject.load_project
    def load_project(path,*args,**kwargs):
        if Path(path)==fake_main/'manifest.json':return []
        if Path(path)==fake_main/'qualification.json':return {'artifact_index':'index.json','artifact_index_sha256':subject.sha(fake_main/'index.json')}
        return actual_load_project(path,*args,**kwargs)
    actual_run=subject.run_child
    def admission_error(*args,**kwargs):raise ValueError('Project budget lock acquisition timed out')
    def dispatched(*args,**kwargs):
        calls.append([str(x) for x in args[0]])
        if scenario=='ordinary-validation':return {'outcome':'pass','resource_qualification':'pass','child_started':False,'control_injected_result':True}
        if scenario in ['resume','resume-single']:raise AssertionError('Resource-unqualified resume must stop before a subsequent child')
        return actual_run(*args,**kwargs)
    def forbidden_popen(*args,**kwargs):popen.append(str(args));raise AssertionError('Compiler/process dispatch forbidden in orchestration fixture')
    def bad_macho(*args,**kwargs):raise ValueError('controlled ordinary object validation error')
    argv=[str(tool),'--mode','execute','--main',str(fake_main),'--manifest',str(fake_main/'manifest.json'),'--manifest-sha256','a'*64,'--qualification',str(fake_main/'qualification.json'),'--qualification-sha256','b'*64,'--selectors',str(fake_main/'selectors.json'),'--selectors-sha256','c'*64,'--shard',plan['shard'],'--owner','eq-host-control','--task','HOST-CONTROL','--experiment','REVCONTEND-002','--out',str(out)]
    if scenario in ['resume','resume-single']:
        prior_record=RUNTIME/(label+'-prior-object.json');prior=copy.deepcopy(old);prior.update(resource_qualification='inconclusive',host_control_wrapper=True,prior_genuine_bytes_origin=str(witness['record']))
        subject.write(prior_record,prior)
        prior_capsule=RUNTIME/(label+'-prior-capsule.json');subject.write(prior_capsule,{'host_control_wrapper':True,'not_a_measurement':True,'executor_sha256':subject.sha(tool),'provenance':plan['provenance'],'objects':[{'id':old['id'],'outcome':'pass','record':str(prior_record),'record_sha256':subject.sha(prior_record)}]})
        argv.extend(['--resume',str(prior_capsule),'--resume-sha256',subject.sha(prior_capsule)])
    bindings={'owned_out':owned,'approval':approval,'bind':bind,'supervisor':lambda *args:None,'stable_memory':admission_error,'run_child':dispatched,'accepted_profile':lambda args:{},'load_project':load_project,'namespace':lambda *args:inputs}
    if scenario=='ordinary-validation':bindings['macho']=bad_macho
    # This fixture skips namespace admission deliberately; the real dependency
    # closure below is still rehashed by reusable/main and is never invented.
    original_owned=bindings['owned_out']
    def with_index(args):
        result=original_owned(args);subject.write(fake_main/'index.json',{'files':inputs['files']});return result
    bindings['owned_out']=with_index
    with patch.multiple(subject,**bindings),patch.object(subject.subprocess,'Popen',forbidden_popen),patch.object(sys,'argv',argv):
        code=subject.main()
    result=json.loads((out/'evidence.json').read_text())
    summary={'label':label,'source_sha256':subject.sha(tool),'scenario':scenario,'main_exit':int(code),'dispatch_calls':len(calls),'popen_attempts':popen,'resource_qualification':result.get('resource_qualification'),'outcome':result['outcome'],'compiler_started':result['compiler_started'],'object_outcomes':[row['outcome'] for row in result['objects']],'command_records':result['commands'],'evidence':str(out/'evidence.json'),'evidence_sha256':subject.sha(out/'evidence.json'),'original_genuine_object_record':witness}
    report['orchestration_cases'].append(summary);return summary


try:
    check('exact2bb source preserved',e.sha(OLD)=='2bb96f520791fb5dd5e05090fcffeabccc1a9e2d9e37dd0911221dce494a4f83')
    check('exact final prechild correction',e.sha(NEW)=='e97a5c9e6edf4daae4924bafb9f50f9bbacf90f1257012da54401feebdb2f4f6')
    supervise=e.supervisor(MAIN);admission=[]
    for number in range(3):
        if number:time.sleep(1)
        sample=supervise.sample();sample['monotonic']=time.monotonic();admission.append(sample)
    report['admission']=admission
    if any(row['MemAvailable_bytes']<4*e.GIB or supervise.pressured(row) for row in admission):raise RuntimeError('resource-deferred: preflight; no retry')
    oldtree=ast.parse(OLD.read_text());newtree=ast.parse(NEW.read_text())
    for node in oldtree.body:
        if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and node.name!='run_child':
            other=next(n for n in newtree.body if isinstance(n,type(node)) and n.name==node.name);check('2bb unchanged full AST '+node.name,ast.dump(node)==ast.dump(other))
    p=Project();child=subprocess.Popen(['sleep','15'],cwd=p.root,start_new_session=True)
    try:
        real_scan=e.process_table;scans=[];reads=[];real_read=Path.read_text
        def scan():scans.append(time.monotonic());return real_scan()
        def read(path,*args,**kwargs):
            if path==Path('/proc',str(child.pid),'stat'):reads.append(time.monotonic())
            return real_read(path,*args,**kwargs)
        with patch.object(e,'process_table',scan),patch.object(Path,'read_text',read):
            p.b.sample(child.pid);p.b.sample(child.pid)
        check('two requests each read SID stat freshly plus one full locked snapshot',len(scans)==2 and len(reads)>=4,full_scans=len(scans),sid_stat_reads=len(reads))
        def reused():
            table=real_scan();table[child.pid]['start_ticks']+=1;return table
        with patch.object(e,'process_table',reused):rejected('fresh locked snapshot refuses modeled session PID reuse',lambda:p.b.sample(child.pid))
        def denied(path,*args,**kwargs):
            if path==Path('/proc',str(child.pid),'stat'):raise PermissionError('controlled direct SID stat denial')
            return real_read(path,*args,**kwargs)
        with patch.object(Path,'read_text',denied):rejected('direct SID read error fails closed',lambda:p.b.sample(child.pid))
        os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=2);snapshot=p.b.sample(child.pid)
        check('disappeared real session is handled without inventing a live process',all(row['pid']!=child.pid for row in snapshot['project_processes']))
    finally:
        if child.poll() is None:os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=2)
        p.b.release()
    p=Project('final-child');holder=None;original=p.b.sample;none_calls=0
    try:
        output=p.args.out;output.mkdir()
        def held_final(session=None,**kwargs):
            global none_calls,holder
            if session is None:none_calls+=1
            if session is None and none_calls==2:
                ready=p.root/'holder-ready'
                code="import fcntl,pathlib,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);pathlib.Path(sys.argv[2]).touch();time.sleep(3)"
                holder=subprocess.Popen([sys.executable,'-c',code,str(p.b.lock_path),str(ready)],cwd='/tmp',start_new_session=True)
                end=time.monotonic()+2
                while not ready.exists() and time.monotonic()<end:time.sleep(.005)
                if not ready.exists():raise RuntimeError('Owned final lock holder missing')
            return original(session,**kwargs)
        p.b.sample=held_final
        command=e.run_child([sys.executable,'-c','print("real host child only; no compiler")'],p.root,output,'child',supervise,timeout=3,admit=False,budget=p.b)
        report['actual_final_command']=command
        check('actual child execution pass and missing final resource observation stay separate',command['exit_code']==0 and command['execution_outcome']=='pass' and command['resource_qualification']=='inconclusive' and command['outcome']=='resource-deferred' and command['after']['owned_processes']==[])
    finally:
        p.b.sample=original
        if holder is not None:os.killpg(holder.pid,signal.SIGTERM);holder.wait(timeout=2)
        p.b.release()
    before=orchestration(OLD,'old-prechild','admission-error')
    check('original2bb P1 continuation reproduced without launching a compiler',before['dispatch_calls']==2 and before['resource_qualification']=='pass' and not before['popen_attempts'])
    after=orchestration(NEW,'fixed-prechild','admission-error')
    check('fixed admission exception records nonpass and stops after first row',after['dispatch_calls']==1 and after['resource_qualification']=='inconclusive' and after['outcome']=='fail' and len(after['command_records'])==1 and after['command_records'][0]['child_started'] is False and after['command_records'][0]['admission'] is None and not after['popen_attempts'])
    ordinary=orchestration(NEW,'ordinary-validation','ordinary-validation')
    check('ordinary object validation failure is distinct from lost resource admission',ordinary['dispatch_calls']==2 and ordinary['resource_qualification']=='pass' and ordinary['object_outcomes']==['fail','fail'] and not ordinary['popen_attempts'])
    resume=orchestration(NEW,'resource-unqualified-resume','resume')
    check('genuine prior Mach-O/deps retain object pass but resource failure survives resume and stops dispatch',resume['dispatch_calls']==0 and resume['resource_qualification']=='inconclusive' and resume['outcome']=='fail' and resume['object_outcomes']==['pass'] and not resume['compiler_started'] and not resume['popen_attempts'])
    single=orchestration(NEW,'resource-unqualified-single-resume','resume-single')
    check('even complete selected object set cannot pass with inconclusive resource qualification',single['dispatch_calls']==0 and single['resource_qualification']=='inconclusive' and single['outcome']=='fail' and single['object_outcomes']==['pass'] and not single['popen_attempts'])
    report['after_host_sample']=supervise.sample()
    if report['after_host_sample']['MemAvailable_bytes']<4*e.GIB or supervise.pressured(report['after_host_sample']):raise RuntimeError('resource-deferred: postflight; no retry')
    report['outcome']='pass'
except Exception as error:
    report['error']=repr(error)
    if 'resource-deferred' in str(error):report['outcome']='resource-deferred'
finally:
    report.update(elapsed_seconds=time.monotonic()-started,controller_memory=e.actual_controller_memory())
    (HERE/'focused-control.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ['checks','orchestration_cases']}|{'checks':len(report['checks']),'orchestration_cases':len(report['orchestration_cases'])}))
raise SystemExit(0 if report['outcome']=='pass' else 1)
