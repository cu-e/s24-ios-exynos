#!/usr/bin/env python3
"""Exact ROOT101 STR031 measurement adapter; source preparation never runs it.

Uses existing qemu_host/core/workguard APIs. No target execution or new timer.
Requires separately supplied root grant bound to this adapter and frozen plan.
"""
import argparse
from datetime import datetime, timezone
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
PLAN=WT/'artifacts/e1s-boot-log-builder/prepare-003/plan.json'
PLAN_SHA='3c94d5b33c2ca7d8ecc25f0d4064a7964adcc7e6c2cb58296b5238dd20bfe73c'
OUT=WT/'artifacts/e1s-boot-log-builder/measure-root101-001'
QUEUE=MAIN/'artifacts/team-coordination/20261106-team/resource-queue.json'
OWNER='codex-e1s-boot-log-builder-20261106-sr31'
TASK='STR-031'
EXPERIMENT='STR031BUILD-001'
LEASE='e1s-loader-log-builder-20261106-101'
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

def parsed_json(path):
    body=captured(path)
    return json.loads(body),dict(path=str(path),sha256=hashlib.sha256(body).hexdigest(),size=len(body))

def bound_json(path,digest):
    value,observed=parsed_json(path)
    need(observed['sha256']==digest,'Changed bound JSON '+str(path));return value

def load_helper(name):
    path,digest=HELPERS[name];body=captured(path)
    need(hashlib.sha256(body).hexdigest()==digest,'Changed qualified helper '+name)
    module=ModuleType('str031_root101_'+name);module.__file__=str(path)
    sys.modules[module.__name__]=module
    exec(compile(body,str(path),'exec'),module.__dict__)
    return module

def input_bindings(plan):
    actual={}
    for name,expected in plan['input_bindings'].items():
        row=binding(expected['path'],expected['size'])
        need(row==expected,'Changed frozen input '+name);actual[name]=row
    return actual

def root_lease(grant):
    queue,observed=parsed_json(QUEUE)
    need(not queue['light_compile'] and not queue['qemu'],'Root lease must remain exclusive')
    heavy=queue.get('heavy');need(isinstance(heavy,dict),'Active root heavy lease required')
    for key in ['id','task','owner','experiment','plan_sha256','runner_sha256',
                'actual_output','max_jobs','max_owned_rss_bytes','whole_seconds']:
        need(heavy.get(key)==grant[key],'Exact active root lease '+key)
    expiry=datetime.fromisoformat(grant['expires_at'])
    need(expiry>datetime.now(timezone.utc),'Unexpired root lease approval')
    return observed

def main():
    need(sys.flags.safe_path,'Controller requires safe-path launch (-P)')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root-grant',type=Path,required=True)
    parser.add_argument('--root-grant-sha256',required=True)
    args=parser.parse_args()
    plan=bound_json(PLAN,PLAN_SHA);self_binding=binding(__file__)
    need(plan['environment_overrides'].get('PYTHONSAFEPATH')=='1','Frozen safe Python child environment')
    need(plan['task']==TASK and plan['owner']==OWNER and plan['experiment']==EXPERIMENT,'Exact task context')
    need([c['id'] for c in plan['commands']]==['source-hook-controls','ordinary-builder'],'Exact planned stages')
    need(len(plan['expected_recorded_run_argv'])==23,'Exact 23 builder commands')
    grant,grant_binding=parsed_json(args.root_grant)
    need(grant_binding['sha256']==args.root_grant_sha256,'Changed root approval bytes')
    expected=dict(id=LEASE,task=TASK,owner=OWNER,experiment=EXPERIMENT,approved_by='root',approved=True,
        plan_sha256=PLAN_SHA,runner_sha256=self_binding['sha256'],actual_output=str(OUT),
        max_jobs=1,max_owned_rss_bytes=LIMIT,whole_seconds=WHOLE,external_seconds=EXTERNAL)
    need(all(grant.get(k)==v for k,v in expected.items()),'Exact separately approved ROOT101 grant')
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
    lease_observation=root_lease(grant)
    started=time.monotonic()
    report=dict(kind='host-test',origin='local-host',outcome='inconclusive',task=TASK,owner=OWNER,
        experiment=EXPERIMENT,plan_sha256=PLAN_SHA,runner=self_binding,root_grant=grant_binding,
        controller_pid=os.getpid(),controller_safe_path=sys.flags.safe_path,commands=[],input_bindings_before=before_inputs,parsed_output_bindings={},
        initial_samples=initial,root_lease_observations=[lease_observation],resource_queue_owned_by='root',target_executed=False,hardware_execution=False,compiler_started=False,
        no_native_ownership_or_marker_qualification=True)
    previous_env=dict(os.environ);pending=[];seen_sessions=set();created=False
    with core.owned_cancellation() as cancel,cancel.cleanup():
        try:
            OUT.mkdir(parents=True,exist_ok=False);created=True
            dump(OUT/'grant.json',grant);dump(OUT/'plan.json',plan)
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
                check();report['root_lease_observations'].append(root_lease(grant))
                sample=supervisor.sample()
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
                    controls,observed=parsed_json(source_out/'evidence.json')
                    report['parsed_output_bindings']['source_controls']=observed
                    need(controls['outcome']=='pass' and controls['source_controls']==8,'Eight actual source controls')
                    need(controls['target_or_compiler_executed'] is False,'No compiler in source controls')
                elif command['id']=='ordinary-builder':
                    build,observed=parsed_json(Path(plan['output']['report']))
                    report['parsed_output_bindings']['builder_report']=observed
                    need(build['outcome']=='pass' and len(build['commands'])==23,'Actual genuine ordinary builder')
                    need([c['argv'] for c in build['commands']]==plan['expected_recorded_run_argv'],'Actual old21 plus2 vectors')
                    report['completed_recorded_builder_commands']=len(build['commands'])
                    report['completed_compile_commands']=sum(c['argv'][:2]==['zig','cc'] and '-c' in c['argv'] for c in build['commands'])
                    report['compiler_started']=report['completed_compile_commands']>0
                    report['post_build_observed']=dict(report=observed,
                        object=binding(Path(plan['output']['root'])/'loader/loader.c.o'))
                else:
                    inspection,observed=parsed_json(inspect_out)
                    report['parsed_output_bindings']['inspection']=observed
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
            report['output_bindings']=list(report['parsed_output_bindings'].values())
            parsed_paths={row['path'] for row in report['output_bindings']}
            report['terminal_unparsed_output_bindings']=[binding(p) for p in [source_out/'evidence.json',
                Path(plan['output']['report']),inspect_out] if str(p) not in parsed_paths and p.is_file()]
            report['output_binding_semantics']='Parsed JSON digest/size uses exactly parsed bytes; terminal unparsed files are observations only, with no current-path claim.'
            if survivors:report.update(outcome='fail',error='Owned survivors after finite cleanup')
            report['cancellation_signals']=list(cancel.signals)
            if cancel.signals:report.update(outcome='fail',error='Owned controller cancellation')
            if created:dump(OUT/'evidence.json',report)
        os.environ.clear();os.environ.update(previous_env)
        # Keep the original cancellation handler installed through terminal
        # publication. A cancellation during postwork/hash/finally is failure.
        if cancel.signals:
            report.update(outcome='fail',error='Owned controller cancellation',cancellation_signals=list(cancel.signals))
            if created:dump(OUT/'evidence.json',report)
        terminal_binding=binding(OUT/'evidence.json') if created and (OUT/'evidence.json').is_file() else None
        if list(cancel.signals)!=report['cancellation_signals']:
            report.update(outcome='fail',error='Owned controller cancellation',cancellation_signals=list(cancel.signals))
            if created:
                dump(OUT/'evidence.json',report);terminal_binding=binding(OUT/'evidence.json')
        print(json.dumps(dict(outcome=report['outcome'],error=report.get('error'),commands=len(report['commands']),
            evidence=terminal_binding,owned_survivors=len(report['owned_survivors']),
            cancellation_signals=report['cancellation_signals'],resource_queue_release='root-independent-only')))
        if cancel.signals:
            report.update(outcome='fail',error='Owned controller cancellation',cancellation_signals=list(cancel.signals))
            if created:dump(OUT/'evidence.json',report)
        return 0 if report['outcome']=='pass' and not cancel.signals else 1

if __name__=='__main__':sys.exit(main())
