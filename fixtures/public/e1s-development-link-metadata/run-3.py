"""Narrow STR032 serializer-only continuation caller. Root supplies and executes an exact reviewed grant.

Reuse accepted qemu_host supervision, owned_cancellation and work guard. No Make,
compiler, new shared process engine or Python metadata serialization.
"""
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import sys
import time
import tempfile
from types import SimpleNamespace

sys.dont_write_bytecode = True
WT = Path(__file__).resolve().parents[3]
MAIN = WT.parents[1]
OWNER = 'codex-e1s-development-link-metadata-20261106-sr32'
TASK = 'STR-032'
QUEUE = MAIN/'artifacts/team-coordination/20261106-team/resource-queue.json'

def require(value, message):
    if not value: raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def bound(path,digest):
    require(sha(path)==digest,'Changed binding: '+str(path))
    return json.loads(Path(path).read_text())

def dump(path,value):
    Path(path).write_text(json.dumps(value,indent=2)+'\n')

def atomic_queue_write(path,value):
    """Only call under the existing queue lock; never truncate the live file."""
    path=Path(path)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.STR032-',dir=path.parent)
    try:
        os.fchmod(fd,path.stat().st_mode&0o777)
        with os.fdopen(fd,'w') as stream:
            json.dump(value,stream,indent=2);stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(name,path)
        directory=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(directory)
        finally:os.close(directory)
    finally:
        try:os.unlink(name)
        except FileNotFoundError:pass

def publish_lease(queue_path,lock_path,lease,out):
    # The caller defers cancellation across persistence AND local bookkeeping.
    with Path(lock_path).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        queue=json.loads(Path(queue_path).read_text())
        require(not queue['heavy'] and not queue['light_compile'] and not queue['qemu'],'Resource queue must be clear')
        out.mkdir(parents=True,exist_ok=False);dump(out/'grant.json',lease)
        queue['light_compile']=lease;atomic_queue_write(queue_path,queue)

def release_lease(queue_path,lock_path,lease,release):
    # Always inspect fresh shared state, even when publish raised after replace.
    with Path(lock_path).open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        queue=json.loads(Path(queue_path).read_text())
        slot=queue['light_compile']
        if slot==lease:
            queue['light_compile']=None;queue['last_light_compile_release']=release
            atomic_queue_write(queue_path,queue)
            return True
        require(not (slot and slot.get('id')==lease['id']),'Own lease ID has inconsistent contents; preserve it for root')
        return False

def load(binding,name):
    require(sha(binding['path'])==binding['sha256'],'Changed accepted helper')
    spec=importlib.util.spec_from_file_location(name,binding['path'])
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def tree(value):
    """Type-sensitive plist comparison. This reads; it never serializes metadata."""
    if type(value) is dict:
        require(all(type(k) is str for k in value),'Non-string plist key')
        return ('dict',tuple((k,tree(v)) for k,v in sorted(value.items())))
    if type(value) is list:return ('array',tuple(map(tree,value)))
    if type(value) in (str,bool,int,float,bytes,datetime.datetime):return (type(value).__name__,value)
    raise ValueError('Unsupported plist type: '+str(type(value)))

def read_plist(path):
    p=Path(path)
    require(p.is_file() and p.stat().st_size<=16*1024**2,'Bounded plist required')
    with p.open('rb') as stream:
        data=stream.read(16*1024**2+1)
    require(len(data)<=16*1024**2,'Growing/oversize plist')
    return plistlib.loads(data)

def validate_text(plan):
    out=Path(plan['actual_output']);version=plan['version_context']['master_version']
    for row in plan['setup']:
        original=read_plist(row['source']);actual=read_plist(row['destination'])
        require('###' not in Path(row['destination']).read_text(),'Unexpanded newvers placeholder')
        for key in ('CFBundleIdentifier','OSBundleCompatibleVersion'):
            require(actual[key]==original[key],'Changed original Info authority: '+key)
        require(actual['CFBundleVersion']==version,'Unexpected native version')
    combined=read_plist(out/'kernel/symbolsets.xml.plist')
    require(set(combined)=={'SymbolsSets','WeakRefFallbackSymbol'},'Changed genuine combined grammar')
    require(len(combined['SymbolsSets'])==9,'Nine genuine symbolsets required')
    require(combined['WeakRefFallbackSymbol']=={'SymbolName':'_gOSKextUnresolved'},'Changed source fallback metadata')
    for name,actual in zip(plan['symbol_order'],combined['SymbolsSets']):
        require(tree(actual)==tree(read_plist(out/'kernel/config'/(name+'.symbolset.plist'))),'Combined order/data mismatch')

def validate_exports(plan):
    """Independent source-line audit, without altering the genuine scripts."""
    lines=[line for path in plan['selected_exports'] for line in Path(path).read_text().splitlines()]
    exported=set();aliases=set()
    for line in lines:
        if ':' in line:
            fields=line.split(':');exported.update(fields[:2]);aliases.add(fields[1]+'  '+fields[0])
        else:exported.add(line)
    root=Path(plan['actual_output'])/'kernel'
    require((root/'all-kpi.exp').read_text().splitlines()==sorted(exported),'Export script lost or changed selected source lines')
    require((root/'all-alias.exp').read_text().splitlines()==sorted(aliases),'Alias direction/order differs from genuine recipe')

def accept_command(command,record,log_path):
    expected_outcome='pass' if record['exit_code']==0 else 'fail'
    accepted=(record['exit_code'] in command['accepted_exit_codes'] and record['outcome']==expected_outcome
        and all(e['event']=='resource-ready-before-spawn' for e in record['events']))
    record['expected_rejection']=command['expected_rejection']
    record['conversion_success']=False
    if command['expected_rejection']:
        log=Path(log_path).read_text()
        accepted=accepted and not Path(command['rejected_output']).exists()
        if 'required_log_exact' in command:accepted=accepted and log==command['required_log_exact']
        else:
            accepted=accepted and log.startswith(command['required_log_prefix'])
            accepted=accepted and all(line in log.splitlines() for line in command['required_usage_lines'])
        record['control_result']=command['rejection_kind'] if accepted else 'rejection-contract-failed'
    else:
        record['control_result']='conversion-completed' if accepted else 'conversion-failed'
        record['conversion_success']=accepted
    record['accepted_by_plan']=accepted
    require(accepted,'Unexpected raw exit/diagnostic/output/resource outcome: '+command['id'])

def execute(args):
    plan=bound(args.plan,args.plan_sha256)
    grant=bound(args.grant,args.grant_sha256)
    require(plan['task']==TASK and plan['owner']==OWNER,'Wrong task/owner')
    require(grant['approved_by']=='root' and grant['approved'] is True,'External root grant required')
    require(grant['task']==TASK and grant['owner']==OWNER,'Wrong grant task/owner')
    require(grant['runner_sha256']==sha(__file__) and grant['plan_sha256']==args.plan_sha256,'Exact runner/plan grant required')
    require(grant['phase']==args.phase and grant['experiment']==args.experiment,'Wrong phase/experiment grant')
    out=Path(plan['actual_output'])
    require(str(out)==str(out.resolve()) and out==WT/'artifacts/e1s-development-link-metadata/generate-2' and not out.exists(),'Fresh canonical owned output required')
    require(grant['actual_output']==str(out),'Wrong granted output')
    for path,digest in plan['input_sha256'].items():require(sha(path)==digest,'Changed input: '+path)
    for path,identity in plan['tool_identity'].items():
        p=Path(path)
        require(str(p.resolve())==identity['resolved_path'] and p.stat().st_mode&0o777==identity['mode'] and os.access(p,os.X_OK),'Host tool mode/identity changed')
    require(not Path('/usr/bin/plutil').exists() and not Path('/usr/local/swift/usr/bin/plutil').exists() and not Path('/opt/swift/usr/bin/plutil').exists(),'New native plutil requires source review')
    commands=plan['commands']
    require(args.phase=='serializer' and len(commands)==14,'Exact serializer-only continuation required')
    require(plan['adopted']['whole_parent_outcome']=='fail' and plan['setup']==[],'No generator replay or parent outcome relabelling')
    require(not any(any(v.endswith(s) for v in c['argv'] for s in plan['forbidden_generator_scripts']) for c in commands),'Genuine generator replay forbidden')
    require(len(commands)==plan['phases'][args.phase],'Phase command count differs')
    ledger=json.loads((MAIN/'state/lab.json').read_text())
    task=next(t for t in ledger['tasks'] if t['id']==TASK)
    require(task['owner']==OWNER and task['status']=='in_progress' and (MAIN/task['worktree']).resolve()==WT,'Original active ownership required')
    require(any(e['id']==args.experiment and e['task']==TASK and e['owner']==OWNER and e['status']=='planned' for e in ledger['experiments']),'Preregistered experiment required')
    supervisor=load(plan['helpers']['supervisor'],'metadata_supervisor')
    core=load(plan['helpers']['cancellation'],'metadata_cancel')
    guard=load(plan['helpers']['work_guard'],'metadata_work_guard')
    os.environ.clear();os.environ.update(PATH='/usr/bin:/bin',LC_ALL='C',LANG='C',PYTHONUTF8='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',GIT_NO_LAZY_FETCH='1',GIT_OPTIONAL_LOCKS='0',GIT_TERMINAL_PROMPT='0')
    initial=[]
    for _ in range(3):
        sample=supervisor.sample();require(supervisor.recovered(sample),'Three actual recovered observations required')
        initial.append(sample);time.sleep(1)
    lease=dict(grant,initial_samples=initial)
    started=time.monotonic();pending=[];sessions=set()
    report=dict(kind='host-test',task=TASK,owner=OWNER,experiment=args.experiment,outcome='inconclusive',
        plan_sha256=args.plan_sha256,runner_sha256=sha(__file__),grant_sha256=args.grant_sha256,phase=args.phase,
        commands=[],phase_results={},adopted=plan['adopted'],portable_serializer_qualified=False,native_plutil_oracle_qualified=False,
        object_ABI_provider_image_runtime_hardware_qualified=False,controller_pid=os.getpid())
    with core.owned_cancellation() as cancel,cancel.cleanup():
        registered=False
        try:
            with cancel.cleanup():
                publish_lease(QUEUE,MAIN/'state/.integration.lock',lease,out)
                registered=True
            inherited=guard.install_work_guard(supervisor,core,cancel,started,pending)
            def check():
                inherited()
                if time.monotonic()-started>180:raise TimeoutError('Metadata whole deadline180s')
            original=supervisor.sample
            def sample(session=None):
                result=original(session)
                if session is not None:
                    sessions.add(session)
                    if result['owned_tree_rss_bytes']+core.proc_status().get('VmRSS_bytes',0)>plan['limits']['owned_rss_bytes']:
                        pending.append('Combined owned RSS exceeded256MiB')
                return result
            supervisor.sample=sample
            def sleep(seconds):
                if seconds==.5:check()
                time.sleep(seconds)
            supervisor.time=SimpleNamespace(monotonic=time.monotonic,sleep=sleep)
            for name in ['tmp','home','kernel/config','serializer-controls','validation']:(out/name).mkdir(parents=True,exist_ok=True)
            if args.phase!='exports':
                for row in plan['setup']:
                    check();src=Path(row['source']);dst=Path(row['destination'])
                    require(dst.is_relative_to(out) and not dst.exists(),'Fresh owned Info copy required')
                    dst.parent.mkdir(parents=True,exist_ok=True)
                    with src.open('rb') as inp,dst.open('xb') as target:
                        while block:=inp.read(1024**2):target.write(block)
                    require(sha(src)==sha(dst)==row['sha256'],'Info copy identity differs')
            for command in commands:
                check();report['active_command']=command['id']
                if command['expected_rejection']:require(not Path(command['rejected_output']).exists(),'Fresh rejected output must be absent before control')
                with cancel.cleanup():
                    record=supervisor.run(command['argv'],out,out,command['id'],seconds=min(20,max(.001,180-(time.monotonic()-started))),build_limit=True)
                    record['id']=command['id'];report['commands'].append(record)
                check()
                accept_command(command,record,out/(command['id']+'.log'))
                for p in command['outputs']:require(Path(p).is_file() and Path(p).stat().st_size>0,'Missing generated output: '+p)
                if command['id']=='aliases':
                    validate_exports(plan);report['phase_results']['exports']='pass'
                if command['id']=='combine':
                    validate_text(plan);report['phase_results']['xml']='pass'
                report.pop('active_command',None);dump(out/'progress.json',report)
            if args.phase=='serializer':
                for equality in plan['typed_tree_equalities']:
                    trees=[tree(read_plist(path)) for path in equality]
                    require(all(t==trees[0] for t in trees),'Serializer typed-tree mismatch')
                for path in map(Path,plan['binary_products']):
                    with path.open('rb') as stream:require(stream.read(8)==b'bplist00','Not a real binary plist')
                report['portable_serializer_qualified']=True;report['phase_results']['serializer']='pass'
            for path,digest in plan['input_sha256'].items():require(sha(path)==digest,'Input changed during generation: '+path)
            report['outcome']='pass'
        except BaseException as error:report.update(outcome='fail',error=repr(error))
        finally:
            survivors=None
            try:
                report['terminal_sessions']=[supervisor.sample(s) for s in sorted(sessions)]
                survivors=[p for s in report['terminal_sessions'] for p in s['owned_processes'] if p['state']!='Z']
                report.update(owned_survivors=survivors,pending_resource_stops=pending,
                    elapsed_seconds=time.monotonic()-started,controller_status=core.proc_status(),publication_returned=registered)
                report['output_sha256']={p:sha(p) for c in commands for p in c['outputs'] if Path(p).is_file()}
                report['log_sha256']={str(p):sha(p) for p in sorted(out.glob('*.log'))}
            except BaseException as error:
                report.update(outcome='fail',evidence_cleanup_error=repr(error))
            finally:
                # Do not let evidence/hash errors bypass lease cleanup. When no
                # session was spawned, admission cleanup needs no process probe.
                if survivors==[] or not sessions:
                    try:
                        report['queue_lease_released']=release_lease(QUEUE,MAIN/'state/.integration.lock',lease,
                            dict(id=grant['id'],task=TASK,outcome=report['outcome'],
                                 evidence=str((out/'evidence.json').relative_to(MAIN)),
                                 evidence_sha256=None,evidence_hash_pending_final_cleanup=True,owned_survivors=0))
                        require(report['queue_lease_released'] or not registered,'Published own lease unexpectedly absent/replaced')
                    except BaseException as error:
                        report.update(outcome='fail',queue_cleanup_error=repr(error))
                else:report.update(outcome='fail',queue_lease_retained='Owned session cleanup not proven')
                report['controller_signals']=list(cancel.signals)
                if survivors or pending or cancel.signals:
                    report.update(outcome='fail',final_stop='Survivors, resource stop or cancellation')
                # Final evidence includes release result. The queue deliberately
                # leaves its hash pending; root binds these finalized bytes.
                if out.exists():
                    dump(out/'evidence.json',report)
                    if cancel.signals and report['outcome']=='pass':
                        report.update(outcome='fail',final_stop='Cancelled during final evidence cleanup',controller_signals=list(cancel.signals))
                        dump(out/'evidence.json',report)
    print(json.dumps(dict(outcome=report['outcome'],commands=len(report['commands']),evidence=str(out/'evidence.json'),sha256=sha(out/'evidence.json') if (out/'evidence.json').is_file() else None)))
    return 0 if report['outcome']=='pass' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ['plan','plan-sha256','grant','grant-sha256','experiment']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--phase',choices=['serializer'],required=True)
    sys.exit(execute(parser.parse_args()))
