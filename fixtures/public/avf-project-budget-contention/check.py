#!/usr/bin/env python3
"""Bounded six-process temporary broker monitor with per-interpreter timings."""
import argparse
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
TEST = Path(__file__).resolve()


def engine(path):
    spec = importlib.util.spec_from_file_location('measured_budget', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def save(path, value):
    path.write_text(json.dumps(value, indent=2)+'\n')


def wait_file(path, seconds):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if path.is_file():return
        time.sleep(.01)
    raise TimeoutError('Timed out waiting for '+str(path))


def worker(args):
    e = engine(args.engine); work = args.worker; root = args.project
    metrics = []; active = None; original_flock = e.fcntl.flock
    original_scan = e.process_table; original_live = e.ProjectBudget.check_live
    original_transaction = e.ProjectBudget.transaction; original_fsync = e.os.fsync
    def flock(fd, flags):
        nonlocal active
        now = time.monotonic()
        if active is not None:
            active.setdefault('first_lock_attempt', now); active['attempts'] = active.get('attempts', 0)+1
        result = original_flock(fd, flags)
        if active is not None:active['acquired'] = time.monotonic()
        return result
    def scan():
        began = time.monotonic()
        try:return original_scan()
        finally:
            if active is not None:active.setdefault('scan_seconds', []).append(time.monotonic()-began)
    def live(self):
        began = time.monotonic()
        try:return original_live(self)
        finally:
            if active is not None:active.setdefault('live_validation_seconds', []).append(time.monotonic()-began)
    def fsync(fd):
        began = time.monotonic()
        try:return original_fsync(fd)
        finally:
            if active is not None:active.setdefault('fsync_seconds', []).append(time.monotonic()-began)
    def transaction(self, operation, lock_timeout=.5):
        nonlocal active
        record = {'started': time.monotonic(), 'lock_timeout': lock_timeout}; active = record
        try:return original_transaction(self, operation, lock_timeout=lock_timeout)
        except Exception as error:record['error'] = repr(error); raise
        finally:
            record['finished'] = time.monotonic()
            if 'acquired' in record:
                record['wait_seconds'] = record['acquired']-record['first_lock_attempt']
                record['held_upper_seconds'] = record['finished']-record['acquired']
            elif 'first_lock_attempt' in record:record['wait_seconds'] = record['finished']-record['first_lock_attempt']
            metrics.append(record); active = None
    e.fcntl.flock = flock; e.process_table = scan; e.ProjectBudget.check_live = live
    e.ProjectBudget.transaction = transaction; e.os.fsync = fsync
    data = e.load_project(root/'approvals'/('worker-'+str(work)+'.json'))
    own = SimpleNamespace(main=root, out=root/'outputs'/str(work), task='WORKER-'+str(work), owner='synthetic-'+str(work), experiment='MONITOR-CONTENTION', shard='synthetic')
    budget = e.project_approval(own, data, executor_path=TEST); child = None
    report = {'worker': work, 'outcome': 'fail', 'metrics': metrics, 'samples': [], 'errors': []}
    try:
        budget.reserve()
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(45)'], cwd='/tmp', start_new_session=True)
        save(root/('ready-'+str(work)), {'pid': os.getpid(), 'child': child.pid, 'child_identity': e.process_identity(child.pid), 'identity': budget.identity})
        wait_file(root/'go', 30)
        for number in range(8):
            began = time.monotonic()
            try:
                snapshot = budget.sample(child.pid)
                report['samples'].append({k: snapshot[k] for k in ['recorded_at', 'project_rss_bytes', 'MemAvailable_bytes', 'project_swap_bytes', 'pswpin', 'pswpout', 'violations']})
            except Exception as error:report['errors'].append({'round': number, 'error': repr(error)})
            metrics[-1]['monitor_elapsed_seconds'] = time.monotonic()-began
            time.sleep(.025)
        save(root/('done-'+str(work)), {'rounds': 8})
        wait_file(root/('release-'+str(work)), 30)
        os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=3)
        budget.release()
        report['outcome'] = 'pass' if not report['errors'] else 'measured-contention' if all('Project budget lock acquisition timed out' in item['error'] for item in report['errors']) else 'fail'
        save(root/('released-'+str(work)), {'outcome': report['outcome']})
        wait_file(root/'exit', 20)
    except Exception as error:report['error'] = repr(error)
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM); child.wait(timeout=3)
        report['controller_memory'] = e.actual_controller_memory()
        report['owned_after'] = [p for p in e.process_table().values() if child is not None and p['state'] != 'Z' and p['session'] == child.pid]
        save(root/('worker-'+str(work)+'.json'), report)
    return 0 if report['outcome'] in ['pass', 'measured-contention'] and not report['owned_after'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path)
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--worker', type=int)
    parser.add_argument('--project', type=Path)
    args = parser.parse_args(); args.engine = args.engine.resolve()
    if args.worker is not None:return worker(args)
    out = args.out.resolve(); e = engine(args.engine)
    if not out.is_relative_to(ROOT/'artifacts') or out.exists():raise ValueError('Fresh own output required')
    out.mkdir(parents=True); root = out/'project'; root.mkdir(); workers = []
    report = {'kind': 'host-test', 'origin': 'synthetic-local-process-controls', 'outcome': 'fail', 'recorded_at': e.stamp(),
              'argv': [sys.executable, *sys.argv], 'engine_sha256': e.sha(args.engine), 'compiler_started': False, 'guest_executed': False, 'commands': []}
    started = time.monotonic()
    try:
        supervisor = e.supervisor(args.main.resolve()); samples = []
        for _ in range(3):
            sample = supervisor.sample(); samples.append(sample)
            if sample['MemAvailable_bytes'] < 4*e.GIB or supervisor.pressured(sample):
                report.update(outcome='resource-deferred', admission=samples)
                return 2
            time.sleep(1)
        report['admission'] = samples
        (root/'artifacts').mkdir(); (root/'approvals').mkdir()
        plan = root/'artifacts/plan.json'; save(plan, {'resource_profile': e.PROJECT_PROFILE})
        slots = []
        for i in range(6):
            slots.append({'task': 'WORKER-'+str(i), 'owner': 'synthetic-'+str(i), 'experiment': 'MONITOR-CONTENTION', 'shard': 'synthetic',
                          'source_plan': 'artifacts/plan.json', 'source_plan_sha256': e.sha(plan), 'actual_output': 'outputs/'+str(i),
                          'reviewed_executor_sha256': e.sha(TEST), 'max_jobs': 1, 'max_owned_rss_bytes': e.EXECUTOR_RSS})
        allocation = root/'artifacts/allocation.json'
        grant = {'schema': e.PROJECT_PROFILE, 'id': 'synthetic-contention-only', 'policy_sha256': e.sha(args.engine),
                 'expires_at': (datetime.datetime.now(datetime.timezone.utc)+datetime.timedelta(minutes=3)).isoformat(),
                 'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6*e.GIB, 'slots': slots,
                 'existing_work': [dict(e.process_identity(os.getpid()), max_owned_rss_bytes=512*1024**2, compiler_jobs=0, label='harness-and-descendants')],
                 'light_rss_budget_bytes': 2*e.GIB, 'six_job_measurement': None}
        save(allocation, grant); queue = root/e.RESOURCE_QUEUE; queue.parent.mkdir(parents=True)
        save(queue, {'heavy': {'id': grant['id'], 'allocation_path': 'artifacts/allocation.json', 'allocation_sha256': e.sha(allocation), 'slots': slots}})
        for i, slot in enumerate(slots):
            approval = {'schema': e.PROJECT_PROFILE, 'reviewed_executor_sha256': e.sha(TEST), 'runner_reviewed': True, 'root_lease': grant['id'],
                        'root_lease_path': 'artifacts/allocation.json', 'root_lease_sha256': e.sha(allocation), 'resource_queue_path': e.RESOURCE_QUEUE,
                        'max_jobs_per_executor': 1, 'task': slot['task'], 'owner': slot['owner'], 'experiment': slot['experiment'], 'shard': slot['shard'],
                        'source_plan_sha256': slot['source_plan_sha256'], 'qemu_allowed': False}
            save(root/'approvals'/('worker-'+str(i)+'.json'), approval)
            stdout = (out/('worker-'+str(i)+'.stdout')).open('xb'); stderr = (out/('worker-'+str(i)+'.stderr')).open('xb')
            proc = subprocess.Popen([sys.executable, TEST, '--engine', args.engine, '--worker', str(i), '--project', root], cwd=root, stdout=stdout, stderr=stderr)
            stdout.close(); stderr.close(); workers.append(proc); wait_file(root/('ready-'+str(i)), 10)
        (root/'go').touch()
        for i in range(6):wait_file(root/('done-'+str(i)), 20)
        for i in range(6):(root/('release-'+str(i))).touch(); wait_file(root/('released-'+str(i)), 5)
        (root/'exit').touch()
        for proc in workers:report['commands'].append({'pid': proc.pid, 'exit_code': proc.wait(timeout=5)})
        results = [e.load_project(root/('worker-'+str(i)+'.json')) for i in range(6)]
        transactions = [record for result in results for record in result['metrics']]
        timeouts = [record for record in transactions if 'lock acquisition timed out' in record.get('error', '')]
        report.update(outcome='pass' if all(c['exit_code'] == 0 for c in report['commands']) else 'fail', workers=results,
                      timeout_count=len(timeouts), transaction_count=len(transactions), max_acquisition_wait_seconds=max(r.get('wait_seconds', 0) for r in transactions),
                      max_held_upper_seconds=max(r.get('held_upper_seconds', 0) for r in transactions),
                      summary='Actual six-process broker monitoring boundary measured; monitor timeouts are retained observations, not compiler results')
        report['after_resources'] = supervisor.sample()
        if report['after_resources']['MemAvailable_bytes'] < 4*e.GIB or supervisor.pressured(report['after_resources']):
            report['outcome'] = 'resource-deferred'
    except Exception as error:report['error'] = repr(error)
    finally:
        for proc in workers:
            if proc.poll() is None:proc.terminate()
        for proc in workers:
            try:proc.wait(timeout=3)
            except subprocess.TimeoutExpired:proc.kill(); proc.wait(timeout=3)
        # A worker interrupted by the harness cannot leave its separately owned
        # child session behind. Validate recorded starts before signalling.
        children = []
        for ready in root.glob('ready-*'):
            record = e.load_project(ready); child = record['child_identity']; children.append(child)
            current = e.process_table().get(child['pid'])
            if current and current['start_ticks'] == child['start_ticks'] and current['state'] != 'Z':
                try:os.killpg(child['pid'], signal.SIGTERM)
                except ProcessLookupError:pass
        time.sleep(.05)
        report['owned_after'] = [p for p in e.process_table().values() if p['state'] != 'Z' and any(p['session'] == c['pid'] for c in children)]
        if report['owned_after']:report.update(outcome='fail', cleanup_error='Created child session survived cleanup')
        report['elapsed_seconds'] = time.monotonic()-started
        report['controller_memory'] = e.actual_controller_memory()
        report['source_hashes'] = {str(p): e.sha(p) for p in [args.engine, TEST]}
        report['artifact_hashes'] = {str(p): e.sha(p) for p in out.rglob('*') if p.is_file()}; report['artifacts'] = list(report['artifact_hashes']); report['sha256'] = report['artifact_hashes']
        save(out/'evidence.json', report)
        print(json.dumps({k: report.get(k) for k in ['outcome', 'timeout_count', 'transaction_count', 'max_acquisition_wait_seconds', 'max_held_upper_seconds', 'error']}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':raise SystemExit(main())
