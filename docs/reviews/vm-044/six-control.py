#!/usr/bin/env python3
"""Independent six-controller budget comparison; only Python and sleep actors."""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
resource.setrlimit(resource.RLIMIT_AS, (256*1024**2, 256*1024**2))


def module(path):
    spec = importlib.util.spec_from_file_location('reviewed_budget', path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def save(path, body):
    path.write_text(json.dumps(body, indent=2)+'\n')


def wait_for(path, seconds=45):
    end = time.monotonic()+seconds
    while not path.exists():
        if time.monotonic() >= end:
            raise TimeoutError(str(path))
        time.sleep(.005)


def identity(pid):
    try:
        fields = Path('/proc', str(pid), 'stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def actor(config_path, index):
    config = json.loads(config_path.read_text())
    root = Path(config['root']); e = module(config['tool'])
    report = {'pid': os.getpid(), 'identity': identity(os.getpid()), 'transactions': [], 'samples': [], 'outcome': 'fail'}
    trace = None
    original_transaction = e.ProjectBudget.transaction
    original_flock = e.fcntl.flock
    original_scan = e.process_table
    original_live = e.ProjectBudget.check_live
    original_fsync = e.os.fsync

    def flock(*args):
        if trace is not None and args[1] & e.fcntl.LOCK_EX:
            trace.setdefault('first_attempt_at', time.monotonic())
        result = original_flock(*args)
        if trace is not None and args[1] & e.fcntl.LOCK_EX:
            trace['acquired_at'] = time.monotonic()
        return result

    def timed(label, function, *args, **kwargs):
        start = time.monotonic()
        try:
            return function(*args, **kwargs)
        finally:
            if trace is not None:
                trace.setdefault(label, []).append(time.monotonic()-start)

    def transaction(self, operation, lock_timeout=.5):
        nonlocal trace
        trace = {'started_at': time.monotonic(), 'lock_timeout': lock_timeout}
        try:
            result = original_transaction(self, operation, lock_timeout=lock_timeout)
            trace['outcome'] = 'pass'
            return result
        except Exception as error:
            trace.update(outcome='fail', error=repr(error))
            raise
        finally:
            end = time.monotonic()
            trace['elapsed_seconds'] = end-trace['started_at']
            if 'acquired_at' in trace:
                trace['wait_seconds'] = trace['acquired_at']-trace['first_attempt_at']
                trace['held_upper_seconds'] = end-trace['acquired_at']
            elif 'first_attempt_at' in trace:
                trace['failed_acquisition_elapsed_seconds'] = end-trace['first_attempt_at']
            report['transactions'].append(trace)
            trace = None

    e.fcntl.flock = flock
    e.process_table = lambda: timed('proc_scan_seconds', original_scan)
    e.ProjectBudget.check_live = lambda self: timed('check_live_seconds', original_live, self)
    e.os.fsync = lambda *args: timed('fsync_seconds', original_fsync, *args)
    e.ProjectBudget.transaction = transaction
    slot = config['slots'][index]
    args = types.SimpleNamespace(main=root, out=root/slot['actual_output'], **{k: slot[k] for k in ['task', 'owner', 'experiment', 'shard']})
    child = None; budget = None
    try:
        budget = e.project_approval(args, config['approvals'][index])
        budget.reserve()
        child = subprocess.Popen(['sleep', '90'], cwd=root, start_new_session=True)
        report['child'] = identity(child.pid)
        save(root/f'child-{index}.json', report['child'])
        budget.sample(child.pid)
        (root/f'ready-{index}').touch()
        for number in range(config['rounds']):
            wait_for(root/f'round-{number}')
            start = time.monotonic()
            row = {'round': number}
            try:
                result = budget.sample(child.pid)
                row.update(outcome='pass', violations=result['violations'], project_rss_bytes=result['project_rss_bytes'], project_swap_bytes=result['project_swap_bytes'], pswpin=result['pswpin'], pswpout=result['pswpout'], MemAvailable_bytes=result['MemAvailable_bytes'])
            except Exception as error:
                row.update(outcome='fail', error=repr(error))
            row['elapsed_seconds'] = time.monotonic()-start
            report['samples'].append(row)
            (root/f'done-{number}-{index}').touch()
        wait_for(root/'stop-children')
        os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=2)
        (root/f'child-stopped-{index}').touch()
        wait_for(root/f'release-{index}')
        budget.release()
        report['outcome'] = 'pass' if all(row['outcome']=='pass' and not row['violations'] for row in report['samples']) else 'fail'
        (root/f'released-{index}').touch()
        wait_for(root/'finish')
    except Exception as error:
        report['error'] = repr(error)
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=2)
        report['controller_memory'] = e.actual_controller_memory()
        save(root/f'actor-{index}.json', report)
    return 0 if report['outcome']=='pass' else 1


def exercise(tool, out, rounds):
    e = module(tool)
    root = out.resolve(); root.mkdir()
    (root/'artifacts').mkdir()
    queue = root/e.RESOURCE_QUEUE; queue.parent.mkdir(parents=True)
    plan = root/'artifacts/plan.json'; save(plan, {'resource_profile': e.PROJECT_PROFILE})
    slots = []
    for i in range(6):
        slots.append({'task': f'REVIEW-{i}', 'owner': f'eq-{i}', 'experiment': 'REVCONTEND-001', 'shard': 'security', 'source_plan': 'artifacts/plan.json', 'source_plan_sha256': e.sha(plan), 'actual_output': f'artifacts/out-{i}', 'reviewed_executor_sha256': e.sha(tool), 'max_jobs': 1, 'max_owned_rss_bytes': e.EXECUTOR_RSS})
    grant = {'schema': e.PROJECT_PROFILE, 'id': 'isolated-six-controller-review', 'policy_sha256': e.sha(tool), 'expires_at': (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=5)).isoformat(), 'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6*e.GIB, 'slots': slots, 'existing_work': [], 'light_rss_budget_bytes': 2*e.GIB, 'six_job_measurement': None}
    allocation = root/'artifacts/allocation.json'; save(allocation, grant)
    save(queue, {'heavy': {'id': grant['id'], 'allocation_path': 'artifacts/allocation.json', 'allocation_sha256': e.sha(allocation), 'slots': slots}})
    approvals = []
    for slot in slots:
        approvals.append({'schema': e.PROJECT_PROFILE, 'reviewed_executor_sha256': e.sha(tool), 'runner_reviewed': True, 'root_lease': grant['id'], 'root_lease_path': 'artifacts/allocation.json', 'root_lease_sha256': e.sha(allocation), 'resource_queue_path': e.RESOURCE_QUEUE, 'max_jobs_per_executor': 1, **{k:slot[k] for k in ['task', 'owner', 'experiment', 'shard', 'source_plan_sha256']}, 'qemu_allowed': False})
    config = root/'config.json'; save(config, {'root':str(root), 'tool':str(tool.resolve()), 'slots':slots, 'approvals':approvals, 'rounds':rounds})
    actors = []; streams = []; report = {'source':str(tool), 'source_sha256':e.sha(tool), 'rounds':rounds, 'outcome':'fail'}
    started = time.monotonic()
    try:
        for i in range(6):
            stream = (root/f'actor-{i}.log').open('w'); streams.append(stream)
            process = subprocess.Popen([sys.executable, '-s', str(Path(__file__).resolve()), '--actor', str(config), str(i)], cwd=root, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            actors.append(process); wait_for(root/f'ready-{i}', 12)
        lock = allocation.with_suffix('.budget.lock'); inode_before = lock.stat().st_ino
        for number in range(rounds):
            (root/f'round-{number}').touch()
            for i in range(6):wait_for(root/f'done-{number}-{i}', 8)
        (root/'stop-children').touch()
        for i in range(6):wait_for(root/f'child-stopped-{i}', 5)
        for i in range(6):
            (root/f'release-{i}').touch(); wait_for(root/f'released-{i}', 8)
        (root/'finish').touch()
        report['exit_codes'] = [process.wait(timeout=5) for process in actors]
        report['actors'] = [json.loads((root/f'actor-{i}.json').read_text()) for i in range(6)]
        report['stable_lock_inode'] = inode_before == lock.stat().st_ino
        report['final_state'] = json.loads(allocation.with_suffix('.reservations.json').read_text())
        report['outcome'] = 'pass' if all(code==0 for code in report['exit_codes']) else 'fail'
    except Exception as error:
        report['error'] = repr(error)
    finally:
        for process in actors:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
        for child_path in root.glob('child-*.json'):
            child = json.loads(child_path.read_text()); current = identity(child['pid'])
            if current and current['start_ticks']==child['start_ticks'] and current['state']!='Z':
                os.killpg(child['pid'], signal.SIGTERM)
        for process in actors:
            try:process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=2)
        for stream in streams:stream.close()
        owned = [identity(process.pid) for process in actors]
        owned += [identity(json.loads(path.read_text())['pid']) for path in root.glob('child-*.json')]
        report['owned_after'] = [row for row in owned if row and row['state']!='Z']
        report['elapsed_seconds'] = time.monotonic()-started
        report['controller_memory'] = e.actual_controller_memory()
        save(root/'result.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--actor', type=Path)
    parser.add_argument('index', nargs='?', type=int)
    parser.add_argument('--tool', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--main', type=Path, default=Path('/home/egor/dev/pet/s24-ios-exynos'))
    parser.add_argument('--rounds', type=int, default=8)
    args = parser.parse_args()
    if args.actor:return actor(args.actor, args.index)
    e = module(args.tool); supervise = e.supervisor(args.main)
    admission = {'samples': [], 'outcome': 'resource-deferred', 'criterion': 'three samples one second apart: MemAvailable >=4GiB, memory PSI full.avg10<2 and some.avg10<10; host-control boundary only'}
    for number in range(3):
        if number:time.sleep(1)
        sample = supervise.sample()
        sample['monotonic'] = time.monotonic()
        sample['host_vmstat'] = {row.split()[0]:int(row.split()[1]) for row in Path('/proc/vmstat').read_text().splitlines() if row.startswith(('pswpin ', 'pswpout '))}
        admission['samples'].append(sample)
    admitted = all(row['MemAvailable_bytes']>=4*e.GIB and not supervise.pressured(row) for row in admission['samples'])
    admission['outcome'] = 'pass' if admitted else 'resource-deferred'
    save(args.out.with_name(args.out.name+'-admission.json'), admission)
    if not admitted:
        print(json.dumps(admission));return 2
    report = exercise(args.tool, args.out, args.rounds)
    report['after_host_sample'] = supervise.sample()
    if supervise.pressured(report['after_host_sample']) or report['after_host_sample']['MemAvailable_bytes']<4*e.GIB:
        report['workload_outcome'] = report['outcome']; report['outcome'] = 'resource-deferred'
    save(args.out/'result.json', report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['actors', 'final_state']}))
    return 0 if report['outcome']=='pass' else 1


if __name__=='__main__':raise SystemExit(main())
