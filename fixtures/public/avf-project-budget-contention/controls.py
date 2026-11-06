#!/usr/bin/env python3
"""Focused strict-proc-resolution and final-sample qualification controls."""
import argparse
import ast
import datetime
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]; TEST = Path(__file__).resolve()
TOOL = ROOT/'tools/build/avf_kernel_objects.py'
spec = importlib.util.spec_from_file_location('contention_controls', TOOL)
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)


class Project:
    def __init__(self, root):
        self.root = root; (root/'artifacts').mkdir(parents=True)
        plan = root/'artifacts/plan.json'; e.write(plan, {'resource_profile': e.PROJECT_PROFILE})
        self.args = SimpleNamespace(main=root, out=root/'artifacts/child', task='CONTROL', owner='synthetic-control', experiment='CONTROL', shard='synthetic')
        slot = {k: getattr(self.args, k) for k in ['task', 'owner', 'experiment', 'shard']}
        slot.update(source_plan='artifacts/plan.json', source_plan_sha256=e.sha(plan), actual_output='artifacts/child', reviewed_executor_sha256=e.sha(TEST), max_jobs=1, max_owned_rss_bytes=e.EXECUTOR_RSS)
        allocation = root/'artifacts/allocation.json'
        grant = {'schema': e.PROJECT_PROFILE, 'id': 'synthetic-control-only', 'policy_sha256': e.sha(TOOL), 'expires_at': (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=3)).isoformat(), 'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6*e.GIB, 'slots': [slot], 'existing_work': [], 'light_rss_budget_bytes': 2*e.GIB, 'six_job_measurement': None}
        e.write(allocation, grant); self.queue = root/e.RESOURCE_QUEUE; self.queue.parent.mkdir(parents=True)
        e.write(self.queue, {'heavy': {'id': grant['id'], 'allocation_path': 'artifacts/allocation.json', 'allocation_sha256': e.sha(allocation), 'slots': [slot]}})
        approval = {'schema': e.PROJECT_PROFILE, 'reviewed_executor_sha256': e.sha(TEST), 'runner_reviewed': True, 'root_lease': grant['id'], 'root_lease_path': 'artifacts/allocation.json', 'root_lease_sha256': e.sha(allocation), 'resource_queue_path': e.RESOURCE_QUEUE, 'max_jobs_per_executor': 1, 'task': slot['task'], 'owner': slot['owner'], 'experiment': slot['experiment'], 'shard': slot['shard'], 'source_plan_sha256': slot['source_plan_sha256'], 'qemu_allowed': False}
        self.budget = e.project_approval(self.args, approval, executor_path=TEST); self.budget.reserve()


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--main', type=Path, required=True); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); out = args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():raise ValueError('Fresh own output required')
    out.mkdir(parents=True); checks = []; commands = []
    report = {'kind': 'host-test', 'origin': 'synthetic-local-process-controls', 'outcome': 'fail', 'recorded_at': e.stamp(), 'argv': [sys.executable, *sys.argv], 'checks': checks, 'commands': commands, 'compiler_started': False, 'guest_executed': False}
    def check(name, passed):
        checks.append({'name': name, 'pass': bool(passed)})
        if not passed:raise ValueError('Control failed: '+name)
    def rejects(name, callback):
        try:callback()
        except (ValueError, OSError) as error:checks.append({'name': name, 'pass': True, 'rejection': repr(error)})
        else:raise ValueError('Invalid boundary accepted: '+name)
    try:
        supervise = e.supervisor(args.main.resolve()); report['before_resources'] = supervise.sample()
        if report['before_resources']['MemAvailable_bytes'] < 4*e.GIB or supervise.pressured(report['before_resources']):
            report.update(outcome='resource-deferred'); return 2
        original = (args.main/'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py').read_text(); source = TOOL.read_text()
        def nodes(text):return {n.name: n for n in ast.parse(text).body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
        old_nodes = nodes(original); new_nodes = nodes(source)
        changed = [name for name in old_nodes if ast.dump(old_nodes[name]) != ast.dump(new_nodes[name])]
        check('only proc resolution and final child qualification functions changed', set(changed) == {'process_table', 'ProjectBudget', 'run_child', 'main'})
        old_methods = {n.name:n for n in old_nodes['ProjectBudget'].body if isinstance(n,ast.FunctionDef)}
        new_methods = {n.name:n for n in new_nodes['ProjectBudget'].body if isinstance(n,ast.FunctionDef)}
        check('only requested-session lookup changes inside broker class', [n for n in old_methods if ast.dump(old_methods[n]) != ast.dump(new_methods[n])] == ['sample'])
        check('all profile/key/recipe/ownership/allocation/finitewait/watchdog guard ASTs unchanged', all(ast.dump(old_nodes[n]) == ast.dump(new_nodes[n]) for n in old_nodes if n not in changed))
        first = out/'outside/ancestor/common'; first.mkdir(parents=True); inside = out/'new-project'; inside.mkdir()
        one = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(15)'], cwd=first, start_new_session=True)
        two = subprocess.Popen([sys.executable, '-c', "import subprocess,time;subprocess.Popen(['sleep','15'],cwd='/tmp');time.sleep(15)"], cwd=first, start_new_session=True)
        original_fsencode = e.os.fsencode; moved = inside/'moved'; seam = {'first': False, 'moved': False}
        def seam_encode(path):
            value = str(path)
            if value == '/proc/'+str(one.pid)+'/cwd':seam['first'] = True
            if value == '/proc/'+str(two.pid)+'/cwd' and seam['first'] and not seam['moved']:
                first.parent.rename(moved); first.parent.symlink_to(moved, target_is_directory=True); seam['moved'] = True
            return original_fsencode(path)
        try:
            time.sleep(.05); e.os.fsencode = seam_encode
            table = e.process_table(); e.os.fsencode = original_fsencode
            check('real ancestry rename and symlink substituted inside one scan', seam['moved'])
            check('second PID canonical cwd resolves freshly into project after substitution', table[two.pid]['cwd'] == str(moved/'common') == str(Path('/proc/'+str(two.pid)+'/cwd').resolve(strict=True)))
            check('current stat/start/executable fields preserved', table[two.pid]['pid'] == two.pid and table[two.pid]['start_ticks'] > 0 and table[two.pid]['executable'] == Path('/proc/'+str(two.pid)+'/exe').resolve(strict=True).name)
            check('outside-cwd descendant ownership link retained', any(p['ppid'] == two.pid and p['cwd'] == '/tmp' for p in table.values()))
            shutil.rmtree(moved/'common')
            after = e.process_table()
            check('deleted cwd resolves to failure rather than cached canonical path', after[one.pid]['cwd'] is None and after[two.pid]['cwd'] is None)
        finally:
            e.os.fsencode = original_fsencode
            for proc in [one, two]:
                try:os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:pass
                proc.wait(timeout=3)
        state = Project(out/'authority'); b = state.budget; saved = b.state_path.read_bytes(); queue_saved = state.queue.read_bytes()
        current = e.load_project(b.state_path); current['entries']['CONTROL']['identity']['start_ticks'] += 1; b.state_path.write_text(json.dumps(current))
        rejects('changed live controller start identity still rejected', b.sample); b.state_path.write_bytes(saved)
        current = e.load_project(b.state_path); current['entries']['CONTROL']['identity']['pid'] = 2**31-1; b.state_path.write_text(json.dumps(current))
        rejects('stale absent controller still rejected', b.sample); b.state_path.write_bytes(saved)
        queue = json.loads(queue_saved); queue['heavy']['id'] = 'wrong'; state.queue.write_text(json.dumps(queue))
        rejects('invalid live root allocation still rejected', b.sample); state.queue.write_bytes(queue_saved)
        b.release()
        single = Project(out/'single-request'); child = subprocess.Popen(['sleep','8'],cwd='/tmp',start_new_session=True)
        original_table = e.process_table; calls = []
        def count_table():calls.append(time.monotonic());return original_table()
        try:
            e.process_table = count_table
            single.budget.sample(child.pid)
            check('requested-session sampling performs exactly one fresh full locked scan', len(calls) == 1)
            start = int(Path('/proc',str(child.pid),'stat').read_text().rsplit(') ',1)[1].split()[19])
            check('fresh requested PID start identity retained exactly', single.budget.observed_sessions[str(child.pid)] == start)
        finally:
            e.process_table = original_table; supervise.terminate(child); single.budget.release()
        for mode in ['timeout', 'violations', 'aggregate', 'floor']:
            project = Project(out/('after-'+mode)); base_budget = project.budget
            class FinalControl:
                def __init__(self):self.args=base_budget.args;self.identity=base_budget.identity;self.rss_limit=base_budget.rss_limit;self.seen=False;self.holder=None
                def sample(self, session=None, **kwargs):
                    if session is not None:self.seen=True
                    if session is None and self.seen:
                        if mode == 'timeout':
                            ready = out/('holder-'+mode)
                            self.holder = subprocess.Popen([sys.executable, '-c', "import fcntl,pathlib,sys,time;f=open(sys.argv[1],'a+');fcntl.flock(f,fcntl.LOCK_EX);pathlib.Path(sys.argv[2]).write_text('ready');time.sleep(1)", base_budget.lock_path, ready], cwd='/tmp')
                            deadline = time.monotonic()+2
                            while not ready.exists() and time.monotonic() < deadline:time.sleep(.005)
                            return base_budget.sample(**kwargs)
                        actual = base_budget.sample(**kwargs)
                        if mode == 'violations':actual['violations'] = ['synthetic-final-violation-control']
                        if mode == 'aggregate':actual['project_rss_bytes'] = 6*e.GIB+1
                        if mode == 'floor':actual['MemAvailable_bytes'] = 4*e.GIB-1
                        return actual
                    return base_budget.sample(session, **kwargs)
            proxy = FinalControl(); sandbox = project.args.out; sandbox.mkdir(parents=True)
            code = "from pathlib import Path;import sys;Path(sys.argv[1]).write_text('genuine owned Python child output')"
            try:
                result = e.run_child([sys.executable, '-c', code, sandbox/'product.txt'], ROOT, sandbox, 'after-'+mode, supervise, timeout=5, admit=mode == 'floor', budget=proxy); commands.append(result)
                check('final '+mode+' cannot qualify passing child/object credit', result['exit_code'] == 0 and result['execution_outcome'] == 'pass' and result['resource_qualification'] != 'pass' and result['outcome'] == 'resource-deferred' and (sandbox/'product.txt').read_text() == 'genuine owned Python child output' and not result['after']['owned_processes'])
                if mode == 'timeout':check('actual competing lock timeout retained in final sample error', 'Project budget lock acquisition timed out' in result['project_after_error'])
            finally:
                if proxy.holder is not None:proxy.holder.wait(timeout=3)
                base_budget.release()
        report['after_resources'] = supervise.sample()
        if report['after_resources']['MemAvailable_bytes'] < 4*e.GIB or supervise.pressured(report['after_resources']):report['outcome'] = 'resource-deferred'
        else:report.update(outcome='pass', summary='Fresh strict proc resolution and direct session-stat lookup, within-scan ancestry/deleted-path, unchanged guards, invalid/stale authority and separate child/resource verdict controls passed')
    except Exception as error:report['error'] = repr(error)
    finally:
        report['controller_memory'] = e.actual_controller_memory(); report['source_hashes'] = {str(p):e.sha(p) for p in [TOOL, TEST]}
        report['artifact_hashes'] = {str(p):e.sha(p) for p in out.rglob('*') if p.is_file() and not p.is_symlink()}; report['artifacts']=list(report['artifact_hashes']); report['sha256']=report['artifact_hashes']; (out/'evidence.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({k:report.get(k) for k in ['outcome','error','controller_memory']}|{'checks':len(checks)},indent=2))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
