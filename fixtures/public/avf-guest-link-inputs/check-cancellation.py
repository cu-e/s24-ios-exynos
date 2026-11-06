#!/usr/bin/env python3
"""Real Python-child cancellation controls; no production grant or target tools."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--main',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--controller',choices=['work','cleanup'])
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('tail_fix',root/'tools/build/avf_guest_link_inputs.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
args.out = args.out.resolve()

if args.controller:
    common = m.accepted_runner(args.main.resolve()); supervise = common.supervisor(args.main)
    prior = {n:signal.getsignal(n) for n in [signal.SIGTERM,signal.SIGINT]}
    report = dict(source_only=True,root_lease=None,callback_test_double=True,
                  production_resource_admission_qualified=False,outcome='fail')
    # Explicit callback-surface test double, not ProjectBudget, not an approval.
    # Its RSS/memory/swap counters are actual controller/owned-child observations.
    class CallbackProbe:
        rss_limit = 256*1024**2
        identity = {'pid':os.getpid()}
        args = SimpleNamespace(task='VM022-PYTHON-CONTROL')
        seen = False
        def sample(self,session=None,lock_timeout=.5):
            if session is not None:self.seen = True
            if args.controller == 'cleanup' and self.seen and session is None and not (args.out/'cleanup-barrier').exists():
                (args.out/'cleanup-barrier').write_text('actual AF193 final budget callback\n')
                until = time.monotonic()+4
                while not state.signals and time.monotonic()<until:time.sleep(.01)
            sample = supervise.sample(session)
            counters = dict(line.split() for line in Path('/proc/vmstat').read_text().splitlines())
            return dict(sample,violations=[],workloads=[dict(task=self.args.task,processes=[{'pid':os.getpid()}])],
                project_rss_bytes=m.proc_status()['VmRSS_bytes']+sample['owned_tree_rss_bytes'],
                project_swap_bytes=0,pswpin=int(counters['pswpin']),pswpout=int(counters['pswpout']))
    probe = CallbackProbe()
    child = "import os,signal,sys,time;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path(sys.argv[1]).write_text(str(os.getpid()));time.sleep(float(sys.argv[2]))"
    with m.owned_cancellation() as state:
        try:
            m.run_owned_child(common,state,[sys.executable,'-s','-c',child,str(args.out/'child.pid'),
                '30' if args.controller == 'work' else '.2'],args.out,args.out,'python-child',supervise,timeout=15,budget=probe)
            report['error'] = 'Cancellation not propagated'
        except m.OwnedCancellation as error:
            report.update(outcome='pass',cancelled=True,error=repr(error),actual_command=getattr(error,'command',None))
        finally:
            with state.cleanup():
                (args.out/'caller-cleanup-barrier').write_text('caller evidence/release cleanup scope\n')
                time.sleep(.25)
                report['signals'] = state.signals
                report['caller_cleanup_completed'] = True
                report['final_process'] = m.proc_status()
                (args.out/'controller-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    report['handlers_restored'] = all(signal.getsignal(n)==handler for n,handler in prior.items())
    (args.out/'controller-evidence.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(0 if report['outcome']=='pass' and report['handlers_restored'] else 1)

args.out.mkdir(parents=True,exist_ok=False)
report = dict(kind='host-test',origin='local-host',source_only=True,outcome='fail',commands=[],checks=[],
    compiler_executed=False,section_tool_executed=False,archive_executed=False,linker_executed=False,
    guest_executed=False,root_execution_lease=None,callback_test_double=True,executor_sha256=m.sha(root/'tools/build/avf_guest_link_inputs.py'))
def alive(pid):
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0] != 'Z'
    except FileNotFoundError:return False
try:
    for mode in ['work','cleanup']:
        out = args.out/mode;out.mkdir()
        argv = [sys.executable,'-s',str(Path(__file__).resolve()),'--main',str(args.main),'--out',str(out),'--controller',mode]
        with (out/'controller.stdout').open('w') as stdout,(out/'controller.stderr').open('w') as stderr:
            controller = subprocess.Popen(argv,stdout=stdout,stderr=stderr,start_new_session=True)
            child_pid = None
            try:
                until = time.monotonic()+12
                marker = out/('child.pid' if mode=='work' else 'cleanup-barrier')
                while not marker.exists() and controller.poll() is None and time.monotonic()<until:time.sleep(.01)
                if not marker.exists():raise AssertionError('Actual controller/child barrier absent: '+mode)
                child_pid = int((out/'child.pid').read_text())
                os.kill(controller.pid,signal.SIGTERM)
                # Cleanup controller remains in its protected caller scope for
                # .25s. Do not deliver test signals after that scope completed.
                until = time.monotonic()+(.5 if mode=='work' else .15)
                while controller.poll() is None and time.monotonic()<until:
                    time.sleep(.02)
                    try:os.kill(controller.pid,signal.SIGINT);os.kill(controller.pid,signal.SIGTERM)
                    except ProcessLookupError:break
                code = controller.wait(timeout=8)
                measured = json.loads((out/'controller-evidence.json').read_text())
                report['commands'].append(dict(argv=argv,exit_code=code,child_pid=child_pid,child_alive=alive(child_pid),
                    evidence=str(out/'controller-evidence.json'),sha256=m.sha(out/'controller-evidence.json')))
                if code or not measured['caller_cleanup_completed'] or not measured['handlers_restored'] or alive(child_pid):
                    raise AssertionError('Cancellation cleanup/restoration failure: '+mode)
                report['checks'].append('actual '+mode+' cancellation plus repeated signals leaves no live owned Python child')
            finally:
                if controller.poll() is None:controller.kill();controller.wait(timeout=3)
                if child_pid and alive(child_pid):
                    os.killpg(child_pid,signal.SIGKILL)
                    raise AssertionError('Watchdog cleanup required for recorded owned session; control failed')
    raw = args.out/'raw-small.bin'; changed = args.out/'oversized-sparse.bin'
    raw.write_bytes(bytes(32))
    with changed.open('wb') as stream:stream.truncate(257*1024**2)
    try:m.constructor_snapshots(raw,changed)
    except ValueError:report['checks'].append('real sparse257MiB transformed file rejected before bounded snapshots')
    else:raise AssertionError('Oversized transformed file admitted')
    changed.unlink();changed.symlink_to(raw)
    try:m.constructor_snapshots(raw,changed)
    except OSError:report['checks'].append('symlink transformed path rejected by O_NOFOLLOW')
    else:raise AssertionError('Symlink transformed file admitted')
    changed.unlink()
    for mutation in ['growth','path-swap']:
        changed.write_bytes(bytes(32))
        real_fstat = os.fstat
        fired = [False]
        def mutate_after_real_fstat(fd):
            result = real_fstat(fd)
            if not fired[0] and os.readlink('/proc/self/fd/'+str(fd)) == str(changed):
                fired[0] = True
                if mutation == 'path-swap':changed.rename(args.out/'old-inode.bin')
                with changed.open('wb') as stream:stream.truncate(257*1024**2)
            return result
        os.fstat = mutate_after_real_fstat
        try:
            try:m.constructor_snapshots(raw,changed)
            except ValueError:report['checks'].append('real post-fstat '+mutation+' refused with actual bounded FD reads')
            else:raise AssertionError('Post-fstat mutation admitted: '+mutation)
            if not fired[0]:raise AssertionError('Real post-fstat mutation barrier not reached')
        finally:os.fstat = real_fstat
        changed.unlink()
    # Actual AF193 reserve method with a local transaction-surface test double.
    # No ProjectBudget constructor, canonical queue or root grant is fabricated.
    common = m.accepted_runner(args.main)
    class ReserveProbe:
        args = SimpleNamespace(task='VM022-RESERVE-CONTROL')
        registered = False
        identity = {'pid':os.getpid()}
        def snapshot(self,state):return {'violations':[]}
        def transaction(self,operation):
            state = {'entries':{}}
            operation(state)
            temp = args.out/'local-reservation.tmp'; final = args.out/'local-reservation.json'
            temp.write_text(json.dumps(state))
            os.replace(temp,final)
            os.kill(os.getpid(),signal.SIGTERM)  # real post-replace/pre-registered window
    probe = ReserveProbe(); reserved = False
    with m.owned_cancellation() as state:
        try:
            with state.cleanup():
                common.ProjectBudget.reserve(probe)
                reserved = True
            state.check()
        except m.OwnedCancellation:
            if not probe.registered or not reserved:raise AssertionError('Persisted reservation window interrupted')
            report['checks'].append('real post-replace cancellation deferred through registered/local ownership flags')
        else:raise AssertionError('Pending reservation cancellation not propagated')
    report['outcome'] = 'pass'
except Exception as error:report['error'] = repr(error)
finally:
    report['final_process'] = m.proc_status()
    (args.out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
raise SystemExit(0 if report['outcome']=='pass' else 1)
