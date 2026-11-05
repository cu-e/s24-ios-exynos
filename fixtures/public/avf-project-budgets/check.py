#!/usr/bin/env python3
"""Isolated resource-governance controls; never starts a compiler or guest."""
import argparse
import ast
import copy
import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import types
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('budget_executor', ROOT/'tools/build/avf_kernel_objects.py')
e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args(); out = args.out.resolve()
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():
        raise ValueError('Fresh original worktree artifact output required')
    out.mkdir(parents=True); checks = []; commands = []
    def check(name, passed):
        checks.append({'name': name, 'pass': bool(passed)})
        if not passed:
            raise ValueError('Control failed: '+name)
    def rejects(name, callback):
        try:
            callback()
        except (ValueError, KeyError, TypeError, OSError) as error:
            checks.append({'name': name, 'pass': True, 'rejection': repr(error)})
        else:
            raise ValueError('Invalid input accepted: '+name)
    fake = out/'project'; (fake/'artifacts').mkdir(parents=True)
    queue_path = fake/e.RESOURCE_QUEUE; queue_path.parent.mkdir(parents=True)
    source_plan = fake/'artifacts/plan.json'; e.write(source_plan, {'resource_profile': e.PROJECT_PROFILE})
    approval = {'schema': e.PROJECT_PROFILE, 'reviewed_executor_sha256': e.sha(e.__file__), 'runner_reviewed': True,
                'root_lease': 'synthetic-only', 'root_lease_path': 'artifacts/allocation.json', 'root_lease_sha256': '',
                'resource_queue_path': e.RESOURCE_QUEUE, 'max_jobs_per_executor': 1, 'task': 'VM-SYNTHETIC',
                'owner': 'fixture-owner', 'experiment': 'SYNTHETIC-001', 'shard': 'security',
                'source_plan_sha256': e.sha(source_plan), 'qemu_allowed': False}
    ns = types.SimpleNamespace(main=fake, out=fake/'artifacts/execute', task=approval['task'], owner=approval['owner'], experiment=approval['experiment'], shard=approval['shard'])
    slot = {k: approval[k] for k in ['task', 'owner', 'experiment', 'shard', 'source_plan_sha256']}
    slot.update(source_plan='artifacts/plan.json', actual_output='artifacts/execute', reviewed_executor_sha256=e.sha(e.__file__), max_jobs=1, max_owned_rss_bytes=e.EXECUTOR_RSS)
    grant = {'schema': e.PROJECT_PROFILE, 'id': approval['root_lease'], 'policy_sha256': e.sha(e.__file__),
             'expires_at': (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=10)).isoformat(),
             'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6*e.GIB, 'slots': [slot],
             'existing_work': [], 'light_rss_budget_bytes': 2*e.GIB, 'six_job_measurement': None}
    def install(value):
        (fake/'artifacts/allocation.json').write_text(json.dumps(value))
        approval['root_lease_sha256'] = e.sha(fake/'artifacts/allocation.json')
        queue_path.write_text(json.dumps({'heavy': {'id': value['id'], 'allocation_path': approval['root_lease_path'], 'allocation_sha256': approval['root_lease_sha256'], 'slots': value['slots']}}))
    def fresh():
        for suffix in ['.reservations.json', '.tmp']:
            (fake/'artifacts/allocation.json').with_suffix(suffix).unlink(missing_ok=True)
        install(grant)
        return e.project_approval(ns, approval)
    report = {'kind': 'host-test', 'origin': 'synthetic-local-resource-controls', 'outcome': 'fail',
              'recorded_at': e.stamp(), 'argv': [sys.executable, *sys.argv], 'base_commit': '12a43eef4a00da24bed6604655854ef533d2bbb2', 'compiler_started': False, 'guest_executed': False, 'checks': checks, 'commands': commands}
    try:
        budget = fresh(); budget.reserve()
        snapshot = budget.sample()
        check('real controller PID/start identity and RSS accounted once', sum(p['pid'] == os.getpid() for p in snapshot['project_processes']) == 1 and snapshot['project_rss_bytes'] > 0)
        check('actual host swap counters and process swap separately recorded', all(type(snapshot[k]) is int for k in ['pswpin', 'pswpout', 'project_swap_bytes']))
        rejects('concurrent duplicate slot fails under stable flock', lambda: e.project_approval(ns, approval).reserve())
        lock_inode = budget.lock_path.stat().st_ino
        budget.release(); check('release keeps stable lock inode', budget.lock_path.stat().st_ino == lock_inode)
        rejects('completed slot cannot be silently reused', lambda: e.project_approval(ns, approval).reserve())
        for name, mutate in [
            ('boolean job count', lambda v: v.update(max_compiler_jobs_total=True)),
            ('seven job escalation', lambda v: v.update(max_compiler_jobs_total=7)),
            ('eight jobs without measured six', lambda v: v.update(max_compiler_jobs_total=8)),
            ('total greater than6GiB', lambda v: v.update(max_total_project_rss_bytes=7*e.GIB)),
            ('missing dynamic light reservation', lambda v: v.update(light_rss_budget_bytes=0)),
            ('duplicate allocation task', lambda v: v['slots'].append(copy.deepcopy(v['slots'][0]))),
            ('two compilers in one executor', lambda v: v['slots'][0].update(max_jobs=2)),
            ('unbounded executor RSS', lambda v: v['slots'][0].update(max_owned_rss_bytes=e.GIB)),
            ('alternate output', lambda v: v['slots'][0].update(actual_output='artifacts/other')),
            ('expired root allocation', lambda v: v.update(expires_at='2000-01-01T00:00:00+00:00')),
            ('unknown allocation field', lambda v: v.update(extra=True)),
        ]:
            value = copy.deepcopy(grant); mutate(value); install(value)
            rejects(name, lambda: e.project_approval(ns, approval))
        value = copy.deepcopy(grant)
        value['slots'] = [dict(slot, task='TASK-'+str(i), owner='owner-'+str(i)) for i in range(7)]
        install(value); rejects('seven allocated global jobs despite one each', lambda: e.project_approval(ns, approval))
        install(grant)
        for key, value in [('owner', 'other-owner'), ('experiment', 'other-experiment'), ('max_jobs_per_executor', True), ('runner_reviewed', 1), ('qemu_allowed', 0)]:
            changed = dict(approval); changed[key] = value
            rejects('strict approval binding '+key, lambda: e.project_approval(ns, changed))
        changed = dict(approval, root_lease_path='../outside')
        rejects('allocation traversal', lambda: e.project_approval(ns, changed))
        budget = fresh(); budget.reserve()
        queue = json.loads(queue_path.read_text()); queue['heavy']['allocation_sha256'] = '0'*64
        queue_path.write_text(json.dumps(queue))
        rejects('live queue stale allocation rejects', lambda: budget.sample())
        install(grant); budget.release()
        budget = fresh(); budget.reserve()
        stale = e.load(budget.state_path); stale['entries'][ns.task]['identity']['start_ticks'] += 1
        budget.state_path.write_text(json.dumps(stale))
        rejects('PID reuse identity fails closed', lambda: budget.sample())
        budget = fresh()
        sentinel_state = out/'state-sentinel'; sentinel_state.write_text('unchanged')
        budget.state_path.symlink_to(sentinel_state)
        rejects('runtime state symlink rejected without write', lambda: budget.reserve())
        check('runtime symlink sentinel preserved', sentinel_state.read_text() == 'unchanged')
        budget.state_path.unlink()
        changed = dict(approval, resource_queue_path='artifacts/other-queue.json')
        rejects('alternate resource queue cannot split global broker', lambda: e.project_approval(ns, changed))
        # A separate process, outside an executor reservation, is discovered by
        # its real project cwd; its child changes cwd and remains accounted.
        helper_pid_file = fake/'helper.pid'
        launcher = subprocess.run([sys.executable, '-c', "import os,pathlib,subprocess,time;pid=os.fork();\nif pid:os._exit(0)\nos.setsid();pathlib.Path('helper.pid').write_text(str(os.getpid()));subprocess.Popen(['sleep','10'],cwd='/tmp');time.sleep(10)"], cwd=fake, check=True)
        until = time.monotonic()+2
        while (not helper_pid_file.exists() or not helper_pid_file.read_text()) and time.monotonic() < until:
            time.sleep(.01)
        helper_pid = int(helper_pid_file.read_text())
        try:
            time.sleep(.15); budget = fresh(); budget.reserve(); snap = budget.sample()
            rows = {p['pid']: p for p in snap['project_processes']}
            check('dynamic light helper and outside-cwd descendant discovered', helper_pid in rows and any(p['ppid'] == helper_pid and p['cwd'] == '/tmp' for p in rows.values()) and snap['light_rss_bytes'] > 0)
            budget.release()
        finally:
            os.killpg(helper_pid, 15)
        # Real child commands retain confinement, bounded timeout and finite cleanup.
        supervise = e.supervisor(args.main.resolve())
        sandbox = out/'sandbox'; sandbox.mkdir(); sentinel = out/'sentinel'; sentinel.write_text('unchanged')
        budget = fresh(); budget.reserve()
        code = "import pathlib,sys;p=pathlib.Path(sys.argv[1]);p.joinpath('inside').write_text('owned');\ntry:pathlib.Path(sys.argv[2]).write_text('forbidden')\nexcept PermissionError:sys.exit(0)\nsys.exit(9)"
        result = e.run_child([sys.executable, '-c', code, sandbox, sentinel], ROOT, sandbox, 'landlock', supervise, timeout=5, budget=budget)
        commands.append(result)
        check('prospective real child keeps write confinement', result['outcome'] == 'pass' and sentinel.read_text() == 'unchanged' and (sandbox/'inside').read_text() == 'owned')
        result = e.run_child([sys.executable, '-c', 'import time;time.sleep(20)'], ROOT, sandbox, 'timeout', supervise, timeout=.25, admit=False, budget=budget)
        commands.append(result)
        check('prospective real timeout leaves no owned session', result['outcome'] == 'timeout' and not result['after']['owned_processes'])
        check('project peak elapsed and host swap deltas retained', result['peak_project_rss_bytes'] > 0 and result['elapsed_seconds'] > 0 and set(result['host_swap_counter_deltas']) == {'pswpin', 'pswpout'})
        budget.release()
        budget = fresh(); budget.reserve(); budget.rss_limit = 1024**2
        result = e.run_child([sys.executable, '-c', 'import time;time.sleep(20)'], ROOT, sandbox, 'rss-stop', supervise, timeout=5, admit=False, budget=budget)
        commands.append(result)
        check('actual sampled RSS stop defers and cleans only owned session', result['outcome'] == 'resource-deferred' and result['stop_reason'] == 'rss-budget' and not result['after']['owned_processes'])
        budget.release()
        budget = fresh(); budget.reserve()
        survivor = subprocess.Popen(['sleep', '10'], cwd=fake, start_new_session=True)
        try:
            budget.sample(survivor.pid); budget.sample()
            rejects('release retains and refuses a live last child session', lambda: budget.release())
        finally:
            supervise.terminate(survivor)
        budget.release()
        # Race two independent real controllers for one root-issued slot.
        fresh()
        worker_code = "import importlib.util,json,pathlib,sys,time,types;s=importlib.util.spec_from_file_location('e',sys.argv[1]);e=importlib.util.module_from_spec(s);s.loader.exec_module(e);a=json.loads(sys.argv[2]);a['main']=pathlib.Path(a['main']);a['out']=pathlib.Path(a['out']);b=e.project_approval(types.SimpleNamespace(**a),json.loads(sys.argv[3]));\ntry:b.reserve()\nexcept ValueError:sys.exit(7)\ntime.sleep(.2);b.release()"
        worker_args = {key: str(value) if isinstance(value, Path) else value for key, value in vars(ns).items()}
        workers = [subprocess.Popen([sys.executable, '-c', worker_code, e.__file__, json.dumps(worker_args), json.dumps(approval)], cwd=fake, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        returns = []
        for worker in workers:
            stdout, stderr = worker.communicate(timeout=5); returns.append(worker.returncode)
            commands.append({'kind': 'synthetic-admission-race', 'pid': worker.pid, 'exit_code': worker.returncode, 'stdout': stdout.decode(), 'stderr': stderr.decode()})
        check('two real concurrent controllers admit exactly one slot', sorted(returns) == [0, 7])
        class LowMemory:
            def sample(self):return {'MemAvailable_bytes': 3*e.GIB}
        admitted = e.stable_memory(LowMemory(), seconds=0)
        check('no stable4GiB floor truthfully defers', admitted['admitted'] is False)
        # Read the accepted legacy executor as immutable data and load a local
        # copy solely for recipe/key comparison, without invoking its main.
        legacy = out/'legacy-executor.py'
        original = subprocess.run(['git', 'show', '12a43eef:tools/build/avf_kernel_objects.py'], cwd=args.main, stdout=subprocess.PIPE, check=True).stdout
        legacy.write_bytes(original)
        ls = importlib.util.spec_from_file_location('legacy_budget_executor', legacy)
        old = importlib.util.module_from_spec(ls); ls.loader.exec_module(old)
        for function in ['expand', 'canonical', 'select', 'validate_graph', 'reusable', 'namespace', 'landlock', 'owned_out', 'task_shards']:
            a = next(n for n in ast.parse(original).body if isinstance(n, ast.FunctionDef) and n.name == function)
            b = next(n for n in ast.parse(Path(e.__file__).read_text()).body if isinstance(n, ast.FunctionDef) and n.name == function)
            check('legacy function AST unchanged '+function, ast.dump(a) == ast.dump(b))
        pins = e.load(ROOT/'fixtures/public/avf-kernel-objects/inputs.json')
        rows = e.load(pins['manifest']['path'], e.PIN)
        check('all1080 frozen recipe expansion and recipe digests identical', all(e.expand(row, out/'next') == old.expand(row, out/'next') and e.canonical(row['next_owned_compile_argv_template']) == old.canonical(row['next_owned_compile_argv_template']) for row in rows))
        # Verify the original input-key expression itself is unchanged, including
        # its complete genuine source/config/recipe/provenance operands.
        def identity_ast(text):
            bind = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == 'bind')
            return next(n for n in ast.walk(bind) if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'identity' for t in n.targets))
        check('legacy complete input-key expression unchanged', ast.dump(identity_ast(original)) == ast.dump(identity_ast(Path(e.__file__).read_text())))
        report.update(outcome='pass', summary='Prospective governance process/tempFS and legacy recipe/key controls passed; synthetic grants only, no compiler trial')
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['source_hashes'] = {str(p): e.sha(p) for p in [Path(__file__), Path(e.__file__)]}
        report['artifact_hashes'] = {str(p): e.sha(p) for p in out.rglob('*') if p.is_file()}; report['artifacts'] = list(report['artifact_hashes']); report['sha256'] = report['artifact_hashes']
        e.write(out/'evidence.json', report)
    print(json.dumps({'outcome': report['outcome'], 'checks': len(checks), 'error': report.get('error')}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
