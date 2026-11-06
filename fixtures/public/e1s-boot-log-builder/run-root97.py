#!/usr/bin/env python3
"""Exact ROOT97 STR031 measurement adapter; source preparation never runs it.

Uses existing qemu_host/core/workguard APIs. No target execution or new timer.
Requires separately supplied root grant bound to this adapter and frozen plan.
"""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType

sys.dont_write_bytecode=True
MAIN=Path('/home/egor/dev/pet/s24-ios-exynos')
WT=MAIN/'worktrees/str-031-e1s-boot-log-builder-20261106'
PLAN=WT/'artifacts/e1s-boot-log-builder/prepare-002/plan.json'
PLAN_SHA='1df5078c0420dc71b63cd1d0f4c7711c1991ea2a4ebc122b7432a21c2d6b6760'
OUT=WT/'artifacts/e1s-boot-log-builder/measure-root97-001'
QUEUE=MAIN/'artifacts/team-coordination/20261106-team/resource-queue.json'
OWNER='codex-e1s-boot-log-builder-20261106-sr31'
TASK='STR-031'
EXPERIMENT='STR031BUILD-001'
LEASE='e1s-loader-log-builder-20261106-97'
LIMIT=2*1024**3
WHOLE=600
EXTERNAL=690
HELPERS={
 'supervisor':(MAIN/'tools/build/qemu_host.py','faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99'),
 'core':(MAIN/'worktrees/vm-022-link-cursor-20261106/tools/build/avf_guest_link_inputs.py','9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5'),
 'guard':(MAIN/'worktrees/vm-022-diagnostic-20261106/fixtures/public/avf-guest-link-inputs/run-link-diagnostic.py','23b88dcc7c2ca20064b4ad8204d9cc713783f79f858d7e25791b85f58a8803d5')}

def need(ok,message):
    if not ok:raise ValueError(message)

def captured(path,limit=16*1024**2):
    with Path(path).open('rb') as stream:body=stream.read(limit+1)
    need(len(body)<=limit,'Bounded input '+str(path));return body

def binding(path,limit=LIMIT):
    digest=hashlib.sha256();size=0
    with Path(path).open('rb') as stream:
        while block:=stream.read(min(1024**2,limit-size+1)):
            size+=len(block);need(size<=limit,'Stream size bound '+str(path));digest.update(block)
    return dict(path=str(path),sha256=digest.hexdigest(),size=size)

def dump(path,value):path.write_text(json.dumps(value,indent=2)+'\n')

def bound_json(path,digest):
    body=captured(path);need(hashlib.sha256(body).hexdigest()==digest,'Changed bound JSON '+str(path))
    return json.loads(body)

def load_helper(name):
    path,digest=HELPERS[name];body=captured(path)
    need(hashlib.sha256(body).hexdigest()==digest,'Changed qualified helper '+name)
    module=ModuleType('str031_root97_'+name);module.__file__=str(path)
    sys.modules[module.__name__]=module
    exec(compile(body,str(path),'exec'),module.__dict__)
    return module

def input_bindings(plan):
    actual={}
    for name,expected in plan['input_bindings'].items():
        row=binding(expected['path'],expected['size'])
        need(row==expected,'Changed frozen input '+name);actual[name]=row
    return actual

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-grant',type=Path,required=True)
    parser.add_argument('--root-grant-sha256',required=True)
    args=parser.parse_args()
    plan=bound_json(PLAN,PLAN_SHA);self_binding=binding(__file__)
    need(plan['task']==TASK and plan['owner']==OWNER and plan['experiment']==EXPERIMENT,'Exact task context')
    need([c['id'] for c in plan['commands']]==['source-hook-controls','ordinary-builder'],'Exact planned stages')
    need(len(plan['expected_recorded_run_argv'])==23,'Exact 23 builder commands')
    grant=bound_json(args.root_grant,args.root_grant_sha256)
    expected=dict(id=LEASE,task=TASK,owner=OWNER,experiment=EXPERIMENT,approved_by='root',approved=True,
        plan_sha256=PLAN_SHA,runner_sha256=self_binding['sha256'],actual_output=str(OUT),
        max_jobs=1,max_owned_rss_bytes=LIMIT,whole_seconds=WHOLE,external_seconds=EXTERNAL)
    need(all(grant.get(k)==v for k,v in expected.items()),'Exact separately approved ROOT97 grant')
    expiry=datetime.fromisoformat(grant['expires_at'])
    need(expiry.tzinfo is not None and expiry>datetime.now(timezone.utc),'Unexpired root grant')
    before_inputs=input_bindings(plan)
    need(not OUT.exists() and not Path(plan['output']['root']).exists(),'Fresh actual output namespaces')
    source_out=Path(plan['commands'][0]['argv'][-1])
    inspect_argv=[PLAN_SHA if x=='@PLAN_SHA256@' else x for x in plan['inspector_template']['argv']]
    inspect_out=Path(inspect_argv[inspect_argv.index('--out')+1])
    need(not source_out.exists() and not inspect_out.parent.exists(),'Fresh controls/inspection namespaces')
    ledger=json.loads(captured(MAIN/'state/lab.json'))
    need(any(t['id']==TASK and t['owner']==OWNER and t['status']=='in_progress' for t in ledger['tasks']),'Original active owner')
    need(any(e['id']==EXPERIMENT and e['task']==TASK and e['owner']==OWNER and e['status']=='planned' for e in ledger['experiments']),'Prospectively registered experiment')
    supervisor=load_helper('supervisor');core=load_helper('core');guard=load_helper('guard')
    initial=[]
    for number in range(3):
        sample=supervisor.sample();initial.append(sample)
        need(sample['MemAvailable_bytes']>=4*1024**3 and not supervisor.pressured(sample),'Stable root admission')
        if number<2:time.sleep(1)
    with (MAIN/'state/.integration.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);queue=json.loads(QUEUE.read_text())
        need(not queue['heavy'] and not queue['light_compile'] and not queue['qemu'],'Exclusive clear queue')
        need(expiry>datetime.now(timezone.utc),'Root grant expired before reservation')
        OUT.mkdir(parents=True,exist_ok=False)
        dump(OUT/'grant.json',grant);dump(OUT/'plan.json',plan)
        queue['heavy']=dict(grant,recorded_at=supervisor.now(),initial_samples=initial)
        dump(QUEUE,queue)
    started=time.monotonic()
    report=dict(kind='host-test',origin='local-host',outcome='inconclusive',task=TASK,owner=OWNER,
        experiment=EXPERIMENT,plan_sha256=PLAN_SHA,runner=self_binding,root_grant=binding(args.root_grant),
        controller_pid=os.getpid(),commands=[],input_bindings_before=before_inputs,
        initial_samples=initial,target_executed=False,hardware_execution=False,compiler_started=False,
        no_native_ownership_or_marker_qualification=True)
    previous_env=dict(os.environ);pending=[];seen_sessions=set()
    with core.owned_cancellation() as cancel,cancel.cleanup():
        try:
            (OUT/'home').mkdir();(OUT/'tmp').mkdir()
            environment=dict(PATH='/usr/bin:/bin',HOME=str(OUT/'home'),TMPDIR=str(OUT/'tmp'),
                TMP=str(OUT/'tmp'),TEMP=str(OUT/'tmp'),LANG='C',LC_ALL='C',PYTHONUTF8='1',PYTHONNOUSERSITE='1',
                ZIG_GLOBAL_CACHE_DIR=str(OUT/'zig-global-cache'),ZIG_LOCAL_CACHE_DIR=str(OUT/'zig-local-cache'))
            environment.update(plan['environment_overrides'])
            os.environ.clear();os.environ.update(environment);report['environment']=environment
            check=guard.install_work_guard(supervisor,core,cancel,started,pending)
            observed_sample=supervisor.sample
            def record_sample(session=None):
                row=observed_sample(session)
                if session is not None:
                    seen_sessions.add(session)
                    row['combined_owned_rss_bytes']=row['owned_tree_rss_bytes']+core.proc_status().get('VmRSS_bytes',0)
                return row
            supervisor.sample=record_sample
            commands=[*plan['commands'],dict(id='artifact-inspection',argv=inspect_argv,
                cwd=plan['inspector_template']['cwd'],timeout_seconds=120)]
            for command in commands:
                check();sample=supervisor.sample()
                need(sample['MemAvailable_bytes']>=4*1024**3 and not supervisor.pressured(sample),'Resource gate before child')
                need(core.proc_status().get('VmRSS_bytes',0)<=LIMIT,'Controller RSS gate')
                if command['id']=='ordinary-builder':report['ordinary_builder_started']=True
                record=dict(id=command['id'],assessment='pending');report['commands'].append(record)
                with cancel.cleanup():
                    row=supervisor.run(command['argv'],Path(command['cwd']),OUT,command['id'],
                        min(command['timeout_seconds'],max(.001,WHOLE-(time.monotonic()-started))),build_limit=False)
                    record['raw_command']=row
                check()
                need(row['outcome']=='pass' and row['exit_code']==0,'Unexpected child failure '+command['id'])
                need(not row['events'] and not any(p['state']!='Z' for p in row['after']['owned_processes']),'Child stop/cleanup event')
                record['assessment']='normal-command-pass'
                record['combined_log']=binding(OUT/(command['id']+'.log'))
                if command['id']=='source-hook-controls':
                    controls=json.loads(captured(source_out/'evidence.json'))
                    need(controls['outcome']=='pass' and controls['source_controls']==8,'Eight actual source controls')
                    need(controls['target_or_compiler_executed'] is False,'No compiler in source controls')
                elif command['id']=='ordinary-builder':
                    build=json.loads(captured(Path(plan['output']['report'])))
                    need(build['outcome']=='pass' and len(build['commands'])==23,'Actual genuine ordinary builder')
                    need([c['argv'] for c in build['commands']]==plan['expected_recorded_run_argv'],'Actual old21 plus2 vectors')
                    report['completed_recorded_builder_commands']=len(build['commands'])
                    report['completed_compile_commands']=sum(c['argv'][:2]==['zig','cc'] and '-c' in c['argv'] for c in build['commands'])
                    report['compiler_started']=report['completed_compile_commands']>0
                    report['post_build_observed']=dict(report=binding(Path(plan['output']['report'])),
                        object=binding(Path(plan['output']['root'])/'loader/loader.c.o'))
                else:
                    inspection=json.loads(captured(inspect_out))
                    need(inspection['outcome']=='pass' and len(inspection['negative_controls'])==12,'Actual layout and12 negative controls')
                    need(inspection['target_executed'] is False,'No target execution')
                    for name in ['report','object']:
                        need(inspection['captured_inputs'][name]==report['post_build_observed'][name],
                            'Inspector captured different post-build '+name)
            report['input_bindings_after']=input_bindings(plan)
            report['outcome']='pass'
        except BaseException as error:report.update(outcome='fail',error=repr(error))
        finally:
            report['seen_owned_sessions']=sorted(seen_sessions)
            report['terminal_sessions']=[supervisor.sample(s) for s in sorted(seen_sessions)]
            survivors=[p for s in report['terminal_sessions'] for p in s['owned_processes'] if p['state']!='Z']
            report['owned_survivors']=survivors;report['elapsed_seconds']=time.monotonic()-started
            report['controller_status']=core.proc_status()
            report['output_bindings']=[binding(p) for p in [source_out/'evidence.json',
                Path(plan['output']['report']),inspect_out] if p.is_file()]
            if survivors:report.update(outcome='fail',error='Owned survivors after finite cleanup')
            dump(OUT/'evidence.json',report)
            with (MAIN/'state/.integration.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX);queue=json.loads(QUEUE.read_text())
                need(queue['heavy']['id']==LEASE and queue['heavy']['owner']==OWNER,'Original owned reservation')
                if not survivors:
                    queue['heavy']=None
                    queue['last_heavy_release']=dict(id=LEASE,task=TASK,outcome=report['outcome'],
                        evidence=str((OUT/'evidence.json').relative_to(MAIN)),evidence_sha256=binding(OUT/'evidence.json')['sha256'],owned_survivors=0)
                    dump(QUEUE,queue)
    os.environ.clear();os.environ.update(previous_env)
    print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(report['commands']),
        evidence=binding(OUT/'evidence.json'),owned_survivors=len(report['owned_survivors']))))
    return 0 if report['outcome']=='pass' else 1

if __name__=='__main__':sys.exit(main())
