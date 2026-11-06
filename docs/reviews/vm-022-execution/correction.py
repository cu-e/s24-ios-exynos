#!/usr/bin/env python3
"""Focused REVTAIL-002 real-file and cancellation controls; no target tools."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import signal
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def load_module(path, expected):
    assert sha(path) == expected, 'Frozen corrected source changed'
    spec = importlib.util.spec_from_file_location('rev039_corrected', path)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    return module


def object_bytes():
    header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 1, 1, 152, 0, 0)
    segment = struct.pack('<II16s4Q4I', 25, 152, b'', 0, 8, 184, 8, 7, 3, 1, 0)
    section = struct.pack('<16s16sQQ8I', b'__mod_init_func', b'__DATA', 0, 8, 184, 3, 0, 0, 9, 0, 0, 0)
    return header + segment + section + b'12345678'


def constructor_worker(args):
    # This contains any regression before it can allocate a large sparse file.
    resource.setrlimit(resource.RLIMIT_AS, (192 * 1024**2, 192 * 1024**2))
    module = load_module(args.source, args.source_sha256)
    args.out.mkdir(parents=True, exist_ok=False)
    raw, transformed = args.out / 'raw.bin', args.out / 'transformed.bin'
    original = object_bytes()
    converted = bytearray(original)
    converted[120:136] = b'__LASTDATA_CONST'[:16].ljust(16, b'\0')
    raw.write_bytes(original)
    transformed.write_bytes(converted)
    case = args.worker
    target = raw if case.startswith('raw-') else transformed
    before = target.stat()
    mutation = []
    real_fstat = os.fstat

    def mutate():
        if case.endswith('growth'):
            with target.open('r+b') as stream:
                stream.truncate(257 * 1024**2)
        elif case.endswith('shrink'):
            with target.open('r+b') as stream:
                stream.truncate(64)
        elif case.endswith('same-bytes-swap'):
            replacement = args.out / 'replacement.bin'
            replacement.write_bytes(converted if target == transformed else original)
            replacement.replace(target)
        elif case.endswith('changed-bytes-swap'):
            replacement = args.out / 'replacement.bin'
            data = bytearray(converted if target == transformed else original)
            data[-1] ^= 1
            replacement.write_bytes(data)
            replacement.replace(target)
        elif case.endswith('retained-inode-symlink-swap'):
            retained = args.out / 'retained-original.bin'
            target.rename(retained)
            target.symlink_to(retained.name)
        elif case.endswith('symlink-swap'):
            replacement = args.out / 'replacement.bin'
            replacement.write_bytes(converted if target == transformed else original)
            target.unlink()
            target.symlink_to(replacement.name)
        else:
            raise AssertionError(case)
        mutation.append({'real_mutation': case, 'path': str(target),
                         'old_inode': before.st_ino, 'new_lstat_inode': target.lstat().st_ino,
                         'new_lstat_size': target.lstat().st_size})

    def observed_fstat(fd):
        observed = real_fstat(fd)
        if case != 'exact-size' and not mutation and (observed.st_dev, observed.st_ino) == (before.st_dev, before.st_ino):
            # Real stat returned; mutate the real file before the real read.
            # No read implementation is mocked, intercepted or bypassed.
            mutate()
        return observed

    os.fstat = observed_fstat
    failure = None
    safe_rejection = False
    returned = None
    fd_count_before = len(os.listdir('/proc/self/fd'))
    started = time.monotonic()
    try:
        returned = module.verify_constructor_transform(raw, transformed)
    except BaseException as error:
        failure = {'type': type(error).__name__, 'text': str(error)}
        safe_rejection = isinstance(error, (ValueError, OSError))
    finally:
        os.fstat = real_fstat
    fd_count_after = len(os.listdir('/proc/self/fd'))
    passed = (returned == ['__mod_init_func'] and not failure) if case == 'exact-size' else bool(mutation and safe_rejection)
    passed = passed and fd_count_before == fd_count_after
    result = {'case': case, 'pass': passed, 'returned': returned, 'exception': failure,
              'actual_post_fstat_mutations': mutation, 'read_mocked_or_bypassed': False,
              'elapsed_seconds': time.monotonic() - started,
              'fd_count_before': fd_count_before, 'fd_count_after': fd_count_after,
              'address_space_limit_bytes': 192 * 1024**2, 'current_image_memory': module.proc_status()}
    write(args.out / 'result.json', result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


def synthetic_budget(out, source, module, common):
    """Actual policy API; explicitly synthetic fixture, never a production grant."""
    root = out / 'policy-fixture'
    (root / 'artifacts/team-coordination/20261106-team').mkdir(parents=True)
    source_plan = root / 'artifacts/fixture-plan.json'
    write(source_plan, {'resource_profile': 'project-budget-v1', 'fixture_only': True})
    args = SimpleNamespace(main=root, out=root / 'owned-output', task='VM-022', owner=module.OWNER,
                           experiment='REVIEW-FIXTURE-NOT-A-LEASE', shard='guest-link-tails')
    slot = {'task': args.task, 'owner': args.owner, 'experiment': args.experiment, 'shard': args.shard,
            'source_plan': 'artifacts/fixture-plan.json', 'source_plan_sha256': sha(source_plan),
            'actual_output': 'owned-output', 'reviewed_executor_sha256': sha(source), 'max_jobs': 1,
            'max_owned_rss_bytes': 256 * 1024**2}
    allocation = root / 'artifacts/fixture-allocation.json'
    grant = {'schema': 'project-budget-v1', 'id': 'REVIEW-FIXTURE-NOT-A-LEASE',
             'policy_sha256': sha(common.__file__),
             'expires_at': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=2)).isoformat(),
             'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6 * 1024**3,
             'slots': [slot], 'existing_work': [], 'light_rss_budget_bytes': 2 * 1024**3,
             'six_job_measurement': None}
    write(allocation, grant)
    write(root / common.RESOURCE_QUEUE,
          {'heavy': {'id': grant['id'], 'allocation_path': 'artifacts/fixture-allocation.json',
                     'allocation_sha256': sha(allocation), 'slots': [slot]}})
    approval = {'schema': 'project-budget-v1', 'reviewed_executor_sha256': sha(source), 'runner_reviewed': True,
                'root_lease': grant['id'], 'root_lease_path': 'artifacts/fixture-allocation.json',
                'root_lease_sha256': sha(allocation), 'resource_queue_path': common.RESOURCE_QUEUE,
                'max_jobs_per_executor': 1, 'task': args.task, 'owner': args.owner,
                'experiment': args.experiment, 'shard': args.shard,
                'source_plan_sha256': sha(source_plan), 'qemu_allowed': False}
    return common.project_approval(args, approval, executor_path=source)


def cancellation_worker(args):
    module = load_module(args.source, args.source_sha256)
    common = module.accepted_runner(MAIN)
    supervise = common.supervisor(MAIN)
    out = args.out
    budget = synthetic_budget(out, args.source, module, common)
    original_sample, original_release = budget.sample, budget.release
    seen_session = False
    final_barrier = False
    release_completed = False
    original_replace = os.replace
    prior_handlers = {int(number): signal.getsignal(number) for number in (signal.SIGTERM, signal.SIGINT)}
    result = {'fixture_only': True, 'production_authority': False, 'mode': args.cancel,
              'outcome': 'inconclusive', 'commands': []}
    reserved = False

    def sample(session=None, lock_timeout=.5):
        nonlocal seen_session, final_barrier
        value = original_sample(session, lock_timeout=lock_timeout)
        if session is not None:
            seen_session = True
        elif seen_session and args.cancel == 'first-final' and not final_barrier:
            final_barrier = True
            write(out / 'final-callback-ready.json', {'actual_budget_callback': True})
            time.sleep(.4)
        return value

    def release():
        nonlocal release_completed
        write(out / 'caller-cleanup-ready.json', {'actual_release_next': True})
        time.sleep(.3)
        value = original_release()
        release_completed = True
        return value

    def replace(source, destination):
        value = original_replace(source, destination)
        if args.cancel == 'first-reserve' and Path(destination) == budget.state_path and not budget.registered:
            write(out / 'reservation-committed-ready.json', {'actual_replace': True, 'registered': budget.registered})
            time.sleep(.4)
        return value

    budget.sample, budget.release, os.replace = sample, release, replace
    try:
        with module.owned_cancellation() as cancellation:
            try:
                # Exact corrected reservation boundary; real AF193 state commit.
                with cancellation.cleanup():
                    budget.reserve()
                    reserved = True
                cancellation.check()
                if args.cancel == 'work':
                    script = ("import os,signal,time;from pathlib import Path;"
                              "signal.signal(signal.SIGTERM,lambda *a:Path('child-term-seen').write_text('yes'));"
                              "Path('child-ready.json').write_text(str(os.getpid()));time.sleep(30)")
                else:
                    script = "import time;time.sleep(.1)"
                command = module.run_owned_child(common, cancellation,
                    [sys.executable, '-s', '-c', script], out, out, 'child', supervise,
                    timeout=4, admit=False, budget=budget)
                result['commands'].append(command)
                result['outcome'] = command['outcome']
            except Exception as error:
                if getattr(error, 'command', None) is not None:
                    result['commands'].append(error.command)
                result.update(outcome='fail', error_type=type(error).__name__, error=str(error))
            finally:
                with cancellation.cleanup():
                    if reserved or budget.registered:
                        budget.release()
                    if cancellation.signals:
                        result.update(outcome='fail', cancelled_signals=list(cancellation.signals))
                    write(out / 'worker-evidence.json', result)
    finally:
        os.replace = original_replace
    result.update(release_completed=release_completed,
                  previous_handlers_restored=all(signal.getsignal(number) == prior for number, prior in prior_handlers.items()),
                  reservation_state=json.loads(budget.state_path.read_text()),
                  current_image_memory=module.proc_status())
    write(out / 'worker-final.json', result)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--worker')
    parser.add_argument('--cancel', choices=['work', 'first-final', 'first-reserve'])
    args = parser.parse_args()
    args.out = args.out.absolute()
    if args.worker:
        return constructor_worker(args)
    if args.cancel:
        return cancellation_worker(args)
    expected_source = '99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060'
    assert args.source_sha256 == expected_source, 'Only the preregistered final correction is reviewed'
    args.out.mkdir(parents=True, exist_ok=False)
    module = load_module(args.source, args.source_sha256)
    common = module.accepted_runner(MAIN)
    supervise = common.supervisor(MAIN)
    started = time.monotonic()
    checks, commands = [], []

    def check(name, passed, **detail):
        checks.append({'name': name, 'pass': bool(passed), **detail})

    root = args.source.resolve().parents[2]
    plan_path = root / 'artifacts/avf-guest-link-inputs/tail-fix-plan-2/execution-plan.json'
    plan_hash = '6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569'
    plan = common.load_project(plan_path, plan_hash)
    rebuilt = module.tail_plan(SimpleNamespace(main=MAIN, vm008=MAIN / 'worktrees/vm-008-20261105',
                                               execute_out=Path(plan['actual_output'])), common)
    check('corrected deterministic plan matches exact new freeze', rebuilt == plan)
    old_root = MAIN / 'worktrees/vm-022-execution-20261106'
    old_path = old_root / 'artifacts/avf-guest-link-inputs/tail-plan-3/execution-plan.json'
    old = common.load_project(old_path, 'd67ab9e647c7f468a1cd8b789884c5f97e3ddaa3d0a26e0831e24af66e65d499')

    def normalized(value):
        if isinstance(value, str):
            return value.replace(str(old_root), str(root)).replace(
                '67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f', expected_source)
        if isinstance(value, list):
            return [normalized(item) for item in value]
        if isinstance(value, dict):
            return {normalized(key): normalized(item) for key, item in value.items()}
        return value

    check('only new executor/output identity changed in full original plan', normalized(old) == plan)
    check('corrected production output still absent', not Path(plan['actual_output']).exists())
    bindings = {str(args.source): expected_source, str(plan_path): plan_hash}
    for path, digest in plan['input_bindings'].items():
        check('unchanged or exact new bound input: ' + path, sha(path) == digest)
        bindings[path] = digest
    descriptor_path = root / 'fixtures/public/avf-guest-link-inputs/tail-cancellation.json'
    descriptor = common.load_project(descriptor_path)
    evidence_path = root / descriptor['evidence']['path']
    check('correction evidence capsule hash', sha(evidence_path) == descriptor['evidence']['sha256'])
    evidence = common.load_project(evidence_path, descriptor['evidence']['sha256'])
    bindings[str(descriptor_path)] = sha(descriptor_path)
    bindings[str(evidence_path)] = sha(evidence_path)
    for path, digest in evidence['artifact_hashes'].items():
        check('preserved corrected/failed author artifact: ' + path, sha(path) == digest)
        bindings[path] = digest
    # Valid large Mach-O premise: streaming parser does not cap whole file size.
    large = args.out / 'valid-large-object.bin'
    large.write_bytes(object_bytes())
    with large.open('r+b') as stream:
        stream.truncate(257 * 1024**2)
    parsed = common.macho(large)
    check('valid sparse large object reaches streaming parser', parsed['file_size'] == 257 * 1024**2)
    constructor_results = []
    for case in ['exact-size', 'raw-growth', 'transformed-growth', 'raw-shrink', 'transformed-shrink',
                 'raw-same-bytes-swap', 'transformed-same-bytes-swap', 'raw-changed-bytes-swap',
                 'transformed-changed-bytes-swap', 'raw-symlink-swap', 'transformed-symlink-swap',
                 'raw-retained-inode-symlink-swap', 'transformed-retained-inode-symlink-swap']:
        out = args.out / case
        argv = [sys.executable, '-s', __file__, '--source', str(args.source), '--source-sha256', args.source_sha256,
                '--out', str(out), '--worker', case]
        before = time.monotonic()
        with (args.out / (case + '.stdout.txt')).open('xb') as stdout, (args.out / (case + '.stderr.txt')).open('xb') as stderr:
            process = subprocess.run(argv, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, timeout=8)
        result = json.loads((out / 'result.json').read_text())
        constructor_results.append(result)
        commands.append({'argv': argv, 'exit_code': process.returncode, 'elapsed_seconds': time.monotonic() - before})
        check('actual FD snapshot: ' + case, process.returncode == 0 and result['pass'], result=result)
    cancellation_results = []
    for mode in ['work', 'first-final', 'first-reserve']:
        out = args.out / ('cancellation-' + mode)
        out.mkdir()
        argv = [sys.executable, '-s', __file__, '--source', str(args.source), '--source-sha256', args.source_sha256,
                '--out', str(out), '--cancel', mode]
        before = time.monotonic()
        stdout = (out / 'stdout.txt').open('xb')
        stderr = (out / 'stderr.txt').open('xb')
        process = subprocess.Popen(argv, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL, start_new_session=True)
        identity = common.process_identity(process.pid)
        observed, signal_log = {}, []
        peak = 0
        stage = 0
        marker = {'work': 'child-ready.json', 'first-final': 'final-callback-ready.json',
                  'first-reserve': 'reservation-committed-ready.json'}[mode]
        rescued = False
        while process.poll() is None and time.monotonic() - before < 8:
            table = common.process_table()
            rows = common.owned_processes(identity, [], table)
            observed.update((row['pid'], row['start_ticks']) for row in rows)
            combined = module.proc_status().get('VmRSS_bytes', 0) + sum(row['rss_bytes'] for row in rows)
            peak = max(peak, combined)
            if combined >= 256 * 1024**2:
                rescued = True
                break
            if stage == 0 and (out / marker).exists():
                os.kill(process.pid, signal.SIGTERM)
                signal_log.append({'signal': 'SIGTERM', 'boundary': marker, 'elapsed_seconds': time.monotonic() - before})
                stage = 1
            elif stage == 1 and ((mode == 'work' and (out / 'child-term-seen').exists()) or
                                  mode != 'work'):
                os.kill(process.pid, signal.SIGINT)
                os.kill(process.pid, signal.SIGTERM)
                signal_log.extend([{'signal': 'SIGINT', 'boundary': 'shared cleanup'},
                                   {'signal': 'SIGTERM', 'boundary': 'shared cleanup'}])
                stage = 2
            elif stage == 2 and (out / 'caller-cleanup-ready.json').exists():
                os.kill(process.pid, signal.SIGINT)
                os.kill(process.pid, signal.SIGTERM)
                signal_log.extend([{'signal': 'SIGINT', 'boundary': 'caller release cleanup'},
                                   {'signal': 'SIGTERM', 'boundary': 'caller release cleanup'}])
                stage = 3
            time.sleep(.015)
        if process.poll() is None:
            rescued = True
            supervise.terminate(process)
        code = process.wait(timeout=2)
        table = common.process_table()
        live = [table[pid] for pid, start in observed.items()
                if pid in table and table[pid]['start_ticks'] == start and table[pid]['state'] != 'Z']
        if live:
            rescued = True
            for row in live:
                os.kill(row['pid'], signal.SIGKILL)
            time.sleep(.1)
        after = common.process_table()
        remaining = [after[pid] for pid, start in observed.items()
                     if pid in after and after[pid]['start_ticks'] == start and after[pid]['state'] != 'Z']
        stdout.close(); stderr.close()
        path = out / 'worker-final.json'
        final = json.loads(path.read_text()) if path.exists() else {}
        passed = (not rescued and not remaining and code == 0 and stage == 3 and
                  final.get('outcome') == 'fail' and final.get('error_type') == 'OwnedCancellation' and
                  final.get('release_completed') is True and final.get('previous_handlers_restored') is True and
                  final.get('reservation_state', {}).get('entries', {}).get('VM-022', {}).get('status') == 'complete' and
                  len(final.get('cancelled_signals', [])) >= 3)
        record = {'mode': mode, 'pass': passed, 'argv': argv, 'exit_code': code,
                  'elapsed_seconds': time.monotonic() - before, 'signals_sent': signal_log,
                  'peak_combined_owned_rss_bytes': peak, 'external_rescue_required': rescued,
                  'remaining_owned': remaining, 'worker': final}
        write(out / 'parent-observations.json', record)
        commands.append({key: record[key] for key in ['argv', 'exit_code', 'elapsed_seconds']})
        cancellation_results.append(record)
        check('actual cancellation boundary: ' + mode, passed, observation=record)
    check('old failed source still immutable',
          sha(old_root / 'tools/build/avf_guest_link_inputs.py') == '67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f')
    check('corrected source still immutable', sha(args.source) == expected_source)
    write(args.out / 'input-hashes.json', bindings)
    findings = [item for item in checks if not item['pass']]
    report = {'task': 'REV-039', 'experiment': 'REVTAIL-002', 'kind': 'host-test', 'origin': 'local-host',
              'outcome': 'fail' if findings else 'pass', 'source_sha256': expected_source, 'plan_sha256': plan_hash,
              'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'checks': checks, 'findings': findings, 'commands': commands,
              'elapsed_seconds': time.monotonic() - started, 'current_image_memory': module.proc_status(),
              'compiler_executed': False, 'section_tool_executed': False, 'linker_executed': False,
              'guest_executed': False, 'actual_tail_production': False,
              'fixture_policy_is_production_authority': False}
    write(args.out / 'report.json', report)
    print(json.dumps({key: value for key, value in report.items() if key not in ['checks', 'findings', 'commands']}, indent=2))
    print(json.dumps({'check_count': len(checks), 'findings': [item['name'] for item in findings]}, indent=2))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
