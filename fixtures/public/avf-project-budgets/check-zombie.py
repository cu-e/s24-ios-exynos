#!/usr/bin/env python3
"""Narrow real registered-zombie/orphan regression; no compiler or guest."""
import argparse
import ast
import datetime
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
ROOT = Path(__file__).resolve().parents[3]
TOOL = ROOT/'tools/build/avf_kernel_objects.py'
spec = importlib.util.spec_from_file_location('zombie_policy', TOOL)
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); out = args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():
        raise ValueError('Fresh own worktree artifact output required')
    out.mkdir(parents=True); project = out/'project'; (project/'artifacts').mkdir(parents=True)
    checks = []; worker = None; orphan = None; started = time.monotonic()
    report = {'kind': 'host-test', 'origin': 'synthetic-local-resource-controls', 'outcome': 'fail',
              'recorded_at': e.stamp(), 'argv': [sys.executable, *sys.argv], 'checks': checks,
              'compiler_started': False, 'guest_executed': False, 'common_started': False}
    def check(name, passed):
        checks.append({'name': name, 'pass': bool(passed)})
        if not passed:raise ValueError('Control failed: '+name)
    try:
        prior = ROOT.parent/'vm-037-ea-fix1-20261106/tools/build/avf_kernel_objects.py'
        check('preserved fix1 helper identity unchanged', e.sha(prior) == '6caa0872750874937c1343b26a168c0d016fa4c98677f54303546e7d194f915a')
        original = prior.read_text(); corrected = TOOL.read_text()
        before = "if entry['identity']['pid'] not in table:"
        after = "if entry['identity']['pid'] not in table or table[entry['identity']['pid']]['state'] == 'Z':"
        check('entire helper differs only by active-zombie predicate', original.count(before) == 1 and corrected == original.replace(before, after))
        check('all legacy functions AST unchanged from reviewed fix1', all(ast.dump(a) == ast.dump(b) for a, b in zip([n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef)], [n for n in ast.parse(corrected).body if isinstance(n, ast.FunctionDef)])))
        plan = project/'artifacts/plan.json'; e.write(plan, {'resource_profile': e.PROJECT_PROFILE})
        caller = e.sha(__file__)
        base = {'owner': 'synthetic-owner', 'experiment': 'SYNTHETIC-ZOMBIE', 'shard': 'synthetic-component',
                'source_plan': 'artifacts/plan.json', 'source_plan_sha256': e.sha(plan),
                'reviewed_executor_sha256': caller, 'max_jobs': 1, 'max_owned_rss_bytes': e.EXECUTOR_RSS}
        slots = [dict(base, task=task, actual_output='artifacts/'+task.lower()) for task in ['OBSERVER', 'WORKER']]
        allocation = project/'artifacts/allocation.json'
        grant = {'schema': e.PROJECT_PROFILE, 'id': 'synthetic-zombie-only', 'policy_sha256': e.sha(TOOL),
                 'expires_at': (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=3)).isoformat(),
                 'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6*e.GIB, 'slots': slots,
                 'existing_work': [], 'light_rss_budget_bytes': 2*e.GIB, 'six_job_measurement': None}
        e.write(allocation, grant)
        queue = project/e.RESOURCE_QUEUE; queue.parent.mkdir(parents=True)
        e.write(queue, {'heavy': {'id': grant['id'], 'allocation_path': 'artifacts/allocation.json', 'allocation_sha256': e.sha(allocation), 'slots': slots}})
        approval = {'schema': e.PROJECT_PROFILE, 'reviewed_executor_sha256': caller, 'runner_reviewed': True,
                    'root_lease': grant['id'], 'root_lease_path': 'artifacts/allocation.json', 'root_lease_sha256': e.sha(allocation),
                    'resource_queue_path': e.RESOURCE_QUEUE, 'max_jobs_per_executor': 1, 'task': 'OBSERVER',
                    'owner': base['owner'], 'experiment': base['experiment'], 'shard': base['shard'],
                    'source_plan_sha256': base['source_plan_sha256'], 'qemu_allowed': False}
        observer_args = SimpleNamespace(main=project, out=project/'artifacts/observer', task='OBSERVER',
                                        owner=base['owner'], experiment=base['experiment'], shard=base['shard'])
        observer = e.project_approval(observer_args, approval, executor_path=__file__); observer.reserve()
        check('live original observer reservation samples normally', any(w.get('task') == 'OBSERVER' for w in observer.sample()['workloads']))
        worker_args = dict(vars(observer_args), task='WORKER', out=project/'artifacts/worker')
        worker_args = {key: str(value) if isinstance(value, Path) else value for key, value in worker_args.items()}
        worker_approval = dict(approval, task='WORKER'); pidfile = out/'orphan.pid'
        code = "import importlib.util,json,pathlib,subprocess,sys,types,os;s=importlib.util.spec_from_file_location('p',sys.argv[1]);p=importlib.util.module_from_spec(s);s.loader.exec_module(p);a=json.loads(sys.argv[2]);a['main']=pathlib.Path(a['main']);a['out']=pathlib.Path(a['out']);b=p.project_approval(types.SimpleNamespace(**a),json.loads(sys.argv[3]),executor_path=sys.argv[4]);b.reserve();child=subprocess.Popen(['sleep','8'],cwd='/tmp');pathlib.Path(sys.argv[5]).write_text(str(child.pid));os._exit(0)"
        worker = subprocess.Popen([sys.executable, '-c', code, TOOL, json.dumps(worker_args), json.dumps(worker_approval), __file__, pidfile], cwd='/tmp', start_new_session=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        until = time.monotonic()+3; controller = None
        while time.monotonic() < until:
            controller = e.process_table().get(worker.pid)
            if controller and controller['state'] == 'Z' and pidfile.exists() and pidfile.read_text():break
            time.sleep(.01)
        check('real registered controller remains unreaped zombie', controller is not None and controller['state'] == 'Z')
        orphan = e.process_table().get(int(pidfile.read_text()))
        check('never-sampled outside-cwd orphan is genuinely alive', orphan is not None and orphan['state'] != 'Z' and orphan['ppid'] != worker.pid and orphan['cwd'] == '/tmp')
        accepted = False; error = None
        try:observer.sample(); accepted = True
        except ValueError as exc:error = repr(exc)
        report.update(controller_identity=controller, orphan_identity=orphan, sample_accepted=accepted, rejection=error)
        check('observer fails closed on zombie active controller', not accepted and 'Stale executor reservation' in error)
        check('sample rejection does not kill another owned slot', e.process_table().get(orphan['pid'], {}).get('start_ticks') == orphan['start_ticks'])
        report.update(outcome='pass', summary='One-predicate active-zombie rejection passed real registered-controller/orphan regression and exact source/legacy equivalence controls')
    except Exception as error:report['error'] = repr(error)
    finally:
        if worker is not None:
            current = e.process_table().get(orphan['pid']) if orphan else None
            if current and current['start_ticks'] == orphan['start_ticks']:
                try:os.killpg(worker.pid, signal.SIGTERM)
                except ProcessLookupError:pass
            stdout, stderr = worker.communicate(timeout=3)
            report['worker_result'] = {'exit_code': worker.returncode, 'stdout': stdout.decode(), 'stderr': stderr.decode()}
            until = time.monotonic()+1
            while time.monotonic() < until and any(p['state'] != 'Z' and p['session'] == worker.pid for p in e.process_table().values()):time.sleep(.01)
            report['owned_after'] = [p for p in e.process_table().values() if p['state'] != 'Z' and p['session'] == worker.pid]
            if report['owned_after']:report.update(outcome='fail', cleanup_error='Created session survived cleanup')
        report['elapsed_seconds'] = time.monotonic()-started
        report['controller_memory'] = e.actual_controller_memory()
        report['source_hashes'] = {str(p): e.sha(p) for p in [TOOL, Path(__file__)]}
        report['artifact_hashes'] = {str(p): e.sha(p) for p in out.rglob('*') if p.is_file()}
        report['artifacts'] = list(report['artifact_hashes']); report['sha256'] = report['artifact_hashes']
        e.write(out/'evidence.json', report)
    print(json.dumps({'outcome': report['outcome'], 'checks': len(checks), 'error': report.get('error')}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':raise SystemExit(main())
