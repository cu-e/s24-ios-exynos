#!/usr/bin/env python3
"""Independent REV-039 light controls; never execute a target-production tool."""
import argparse
import copy
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
AUTHOR = MAIN / 'worktrees/vm-022-execution-20261106'
SOURCE = AUTHOR / 'tools/build/avf_guest_link_inputs.py'
SOURCE_SHA = '67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f'
PLAN = AUTHOR / 'artifacts/avf-guest-link-inputs/tail-plan-3/execution-plan.json'
PLAN_SHA = 'd67ab9e647c7f468a1cd8b789884c5f97e3ddaa3d0a26e0831e24af66e65d499'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def load_source():
    assert sha(SOURCE) == SOURCE_SHA
    spec = importlib.util.spec_from_file_location('frozen_rev039_author', SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.dont_write_bytecode = True
    spec.loader.exec_module(module)
    common = module.accepted_runner(MAIN)
    return module, common


def controller(out):
    module, common = load_source()
    supervise = common.supervisor(MAIN)
    script = "import os,time;from pathlib import Path;Path('child.json').write_text(str(os.getpid()));time.sleep(30)"
    try:
        result = common.run_child([sys.executable, '-s', '-c', script], out, out,
                                  'child', supervise, timeout=5, admit=False)
        write(out / 'controller-result.json', result)
        return 0
    except BaseException as error:
        write(out / 'controller-exception.json', {'exception': repr(error)})
        return 3


def object_bytes(sections):
    size = 72 + 80 * len(sections)
    offset = 32 + size
    head = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 1, 1, size, 0, 0)
    seg = struct.pack('<II16s4Q4I', 25, size, b'', 0, 8 * len(sections), offset,
                      8 * len(sections), 7, 3, len(sections), 0)
    rows = b''
    for number, (name, segment, flags) in enumerate(sections):
        rows += struct.pack('<16s16sQQ8I', name, segment, number * 8, 8,
                            offset + number * 8, 3, 0, 0, flags, 0, 0, 0)
    return head + seg + rows + b'12345678' * len(sections)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--controller', action='store_true')
    args = parser.parse_args()
    args.out = args.out.absolute()
    if args.controller:
        return controller(args.out)
    args.out.mkdir(parents=True, exist_ok=False)
    began = time.monotonic()
    module, common = load_source()
    records, findings = [], []

    def check(name, condition, **detail):
        item = {'name': name, 'pass': bool(condition), **detail}
        records.append(item)
        if not condition:
            findings.append(item)

    def reject(name, call):
        try:
            call()
        except (ValueError, KeyError, OSError, struct.error, UnicodeError) as error:
            check(name, True, rejection=repr(error))
        else:
            check(name, False, error='Unexpected admission')

    assert sha(PLAN) == PLAN_SHA
    plan = common.load_project(PLAN, PLAN_SHA)
    input_hashes = {str(SOURCE): SOURCE_SHA, str(PLAN): PLAN_SHA}
    for path, digest in plan['input_bindings'].items():
        actual = sha(path)
        check('bound bytes: ' + path, actual == digest)
        input_hashes[path] = actual
    fixture = common.load_project(AUTHOR / 'fixtures/public/avf-guest-link-inputs/tail-executor.json')
    for item in (fixture['source_plan'], fixture['source_only_evidence']):
        path = MAIN / item['path'] if item['path'].startswith('worktrees/') else AUTHOR / item['path']
        check('capsule binding: ' + str(path), sha(path) == item['sha256'])
        input_hashes[str(path)] = sha(path)
    evidence = common.load_project(AUTHOR / 'docs/procedures/avf-guest-link-inputs/tail-plan-evidence.json')
    for path, digest in evidence['artifact_hashes'].items():
        check('historical artifact: ' + path, sha(path) == digest)
        input_hashes[path] = digest
    check('no production tail output exists', not Path(plan['actual_output']).exists())
    rebuilt = module.tail_plan(SimpleNamespace(main=MAIN, vm008=MAIN / 'worktrees/vm-008-20261105',
                                               execute_out=Path(plan['actual_output'])), common)
    check('deterministic complete plan equals frozen bytes', rebuilt == plan)
    check('exact ordered four tails', tuple(row['target'] for row in plan['commands']) == module.TAILS)
    for row in plan['commands']:
        actual, original = row['argv'], row['original_argv']
        changes = {change['position']: change for change in row['substitutions']}
        check(row['target'] + ': only exact recorded changes plus object output',
              len(actual) == len(original) + 2 and actual[-2:] == ['-o', row['object']] and
              all((original[i] == actual[i] and i not in changes) or
                  (i in changes and changes[i] == {'position': i, 'original': original[i], 'resolved': actual[i]})
                  for i in range(len(original))))
        check(row['target'] + ': actual source and dependency output', actual[-3] == row['source'] and
              actual[actual.index('-MF') + 1] == row['dependency_file'])
        check(row['target'] + ': no LTO or export/undefined relaxation',
              not any(token == '-flto' or token.startswith('-exported_symbols_list') or token == '-undefined'
                      for token in actual))
    # Original-owner checks use a declared synthetic ledger snapshot; no real ledger changes.
    base_args = SimpleNamespace(main=MAIN, out=Path(plan['actual_output']), task='VM-022', owner=module.OWNER,
                                shard='guest-link-tails', experiment='REVIEW-SYNTHETIC', vm008=MAIN / 'worktrees/vm-008-20261105')
    ledger = {'tasks': [{'id': 'VM-022', 'owner': module.OWNER, 'status': 'in_progress',
                         'worktree': 'worktrees/vm-022-execution-20261106'}],
              'experiments': [{'id': 'REVIEW-SYNTHETIC', 'task': 'VM-022', 'owner': module.OWNER, 'status': 'planned'}]}

    def common_with_ledger(value):
        proxy = SimpleNamespace(**vars(common))
        proxy.load_project = lambda path, expected=None: copy.deepcopy(value) if Path(path) == MAIN / 'state/lab.json' else common.load_project(path, expected)
        return proxy

    module.tail_ownership(copy.copy(base_args), common_with_ledger(ledger))
    check('synthetic exact original-owner ledger admitted without writes', not Path(plan['actual_output']).exists())
    for name, mutate in (
            ('wrong owner', lambda x: x['tasks'][0].update(owner='other')),
            ('blocked task', lambda x: x['tasks'][0].update(status='blocked')),
            ('different worktree', lambda x: x['tasks'][0].update(worktree='worktrees/elsewhere')),
            ('completed experiment', lambda x: x['experiments'][0].update(status='pass')),
            ('missing experiment', lambda x: x.update(experiments=[]))):
        changed = copy.deepcopy(ledger)
        mutate(changed)
        reject('ownership rejects ' + name, lambda changed=changed: module.tail_ownership(copy.copy(base_args), common_with_ledger(changed)))
    changed_plan = copy.deepcopy(plan)
    changed_plan['commands'][0]['argv'].append('-DUNREVIEWED=1')
    changed_path = args.out / 'changed-plan.json'
    write(changed_path, changed_plan)
    execute_args = copy.copy(base_args)
    execute_args.source_plan, execute_args.source_plan_sha256 = changed_path, sha(changed_path)
    reject('execute rejects changed command plan before any output',
           lambda: module.execute_tails(execute_args, common_with_ledger(ledger)))
    check('changed plan refusal left author output absent', not Path(plan['actual_output']).exists())
    # Real small Mach-O/dependency and namespace parser controls.
    raw, converted = args.out / 'raw.bin', args.out / 'converted.bin'
    content = object_bytes([(b'__mod_init_func', b'__DATA', 9), (b'__debug', b'__DATA', 0x02000000)])
    raw.write_bytes(content)
    result = bytearray(content)
    result[120:136] = b'__LASTDATA_CONST'[:16].ljust(16, b'\0')
    converted.write_bytes(result)
    common.macho(raw)
    common.macho(converted)
    check('constructor conversion exactly matches source-defined eligible section',
          module.verify_constructor_transform(raw, converted) == ['__mod_init_func'])
    result[-1] ^= 1
    converted.write_bytes(result)
    reject('constructor rejects changed payload', lambda: module.verify_constructor_transform(raw, converted))
    result = bytearray(content)
    result[120:136] = b'__LASTDATA_CONST'[:16].ljust(16, b'\0')
    result[200:216] = b'__LASTDATA_CONST'[:16].ljust(16, b'\0')
    converted.write_bytes(result)
    reject('constructor rejects changing S_ATTR_DEBUG section', lambda: module.verify_constructor_transform(raw, converted))
    wrong_cpu = args.out / 'wrong-cpu.bin'
    changed = bytearray(content)
    struct.pack_into('<I', changed, 4, 7)
    wrong_cpu.write_bytes(changed)
    reject('object parser rejects foreign architecture', lambda: common.macho(wrong_cpu))
    truncated = args.out / 'truncated.bin'
    truncated.write_bytes(content[:-1])
    reject('object parser rejects truncated section', lambda: common.macho(truncated))
    dep = args.out / 'space.d'
    dep.write_text('object\\ name.o: source\\ name.c \\\n header.h\n')
    check('dependency parser preserves escaped space and continuation',
          common.dependencies(dep, args.out, args.out / 'object name.o') ==
          sorted([str(args.out / 'source name.c'), str(args.out / 'header.h')]))
    reject('dependency target mismatch', lambda: common.dependencies(dep, args.out, args.out / 'foreign.o'))
    ns = args.out / 'namespace'
    ns.mkdir()
    source = ns / 'source.c'
    source.write_text('/* authored parser fixture */\n')
    rows = [{'cwd': str(ns), 'bound_source': str(source), 'next_owned_compile_argv_template': ['-I' + str(ns)]}]
    index = {str(source): sha(source)}
    cache = common.Digests()
    common.namespace(rows, index, cache)
    shadow = ns / 'new.h'
    shadow.write_text('/* unbound shadow */\n')
    reject('namespace rejects newly shadowing file', lambda: common.namespace(rows, index, cache))
    shadow.unlink()
    source.write_text('/* changed byte fixture */\n')
    reject('namespace rejects source change after cached hash', lambda: common.namespace(rows, index, cache))
    source.unlink()
    reject('namespace rejects missing qualified source', lambda: common.namespace(rows, index, cache))
    # Avoid a prohibited large allocation: observe the attempted read of a sparse output.
    sparse = args.out / 'oversized-transformed.bin'
    with sparse.open('wb') as stream:
        stream.truncate(257 * 1024 * 1024)
    original_read = Path.read_bytes
    attempted_large_read = []
    def observed_read(path):
        if path == sparse:
            attempted_large_read.append(path.stat().st_size)
            raise RuntimeError('review observer prevented oversized read')
        return original_read(path)
    Path.read_bytes = observed_read
    try:
        try:
            module.verify_constructor_transform(raw, sparse)
        except (ValueError, RuntimeError):
            pass
    finally:
        Path.read_bytes = original_read
    check('constructor rejects oversized transformed file before read', not attempted_large_read,
          attempted_unbounded_read_sizes=attempted_large_read,
          observer='Read observer prevents allocation; real sparse file and actual frozen verifier')
    # Accepted ProjectBudget, with synthetic allocation/queue only under reviewer output.
    fake_main = args.out / 'synthetic-main'
    (fake_main / 'artifacts/team-coordination/20261106-team').mkdir(parents=True)
    allocation_path = fake_main / 'artifacts/review-allocation.json'
    plan_path = fake_main / 'artifacts/review-plan.json'
    write(plan_path, {'resource_profile': 'project-budget-v1', 'fixture': True})
    budget_args = SimpleNamespace(main=fake_main, out=fake_main / 'owned-output', task='VM-022',
                                 owner=module.OWNER, experiment='SYNTHETIC-REVIEW', shard='guest-link-tails')
    slot = {'task': budget_args.task, 'owner': budget_args.owner, 'experiment': budget_args.experiment,
            'shard': budget_args.shard, 'source_plan': 'artifacts/review-plan.json', 'source_plan_sha256': sha(plan_path),
            'actual_output': 'owned-output', 'reviewed_executor_sha256': SOURCE_SHA, 'max_jobs': 1,
            'max_owned_rss_bytes': 256 * 1024**2}
    allocation = {'schema': 'project-budget-v1', 'id': 'SYNTHETIC-REVIEW-NOT-A-ROOT-LEASE',
                  'policy_sha256': sha(common.__file__),
                  'expires_at': (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=5)).isoformat(),
                  'max_compiler_jobs_total': 6, 'max_total_project_rss_bytes': 6 * 1024**3,
                  'slots': [slot], 'existing_work': [], 'light_rss_budget_bytes': 2 * 1024**3,
                  'six_job_measurement': None}
    write(allocation_path, allocation)
    queue_path = fake_main / common.RESOURCE_QUEUE
    queue = {'heavy': {'id': allocation['id'], 'allocation_path': 'artifacts/review-allocation.json',
                       'allocation_sha256': sha(allocation_path), 'slots': allocation['slots']}}
    write(queue_path, queue)
    approval = {'schema': 'project-budget-v1', 'reviewed_executor_sha256': SOURCE_SHA, 'runner_reviewed': True,
                'root_lease': allocation['id'], 'root_lease_path': 'artifacts/review-allocation.json',
                'root_lease_sha256': sha(allocation_path), 'resource_queue_path': common.RESOURCE_QUEUE,
                'max_jobs_per_executor': 1, 'task': budget_args.task, 'owner': budget_args.owner,
                'experiment': budget_args.experiment, 'shard': budget_args.shard,
                'source_plan_sha256': sha(plan_path), 'qemu_allowed': False}
    budget = common.project_approval(budget_args, approval, executor_path=SOURCE)
    budget.reserve()
    sample = budget.sample()
    check('synthetic allocation reserves exact caller and samples real process',
          not sample['violations'] and any(w.get('task') == 'VM-022' for w in sample['workloads']))
    with budget.lock_path.open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        began_lock = time.monotonic()
        reject('budget lock contention has finite deadline', lambda: budget.sample(lock_timeout=.08))
        check('budget lock deadline bounded', time.monotonic() - began_lock < .5)
    budget.release()
    check('synthetic reservation releases complete', json.loads(budget.state_path.read_text())['entries']['VM-022']['status'] == 'complete')
    reject('completed allocation cannot reserve again', budget.reserve)
    bad_approval = copy.deepcopy(approval)
    bad_approval['owner'] = 'wrong-owner'
    reject('approval rejects wrong owner', lambda: common.project_approval(budget_args, bad_approval, executor_path=SOURCE))
    bad_approval = copy.deepcopy(approval)
    bad_approval['reviewed_executor_sha256'] = '0' * 64
    reject('approval rejects different caller bytes', lambda: common.project_approval(budget_args, bad_approval, executor_path=SOURCE))
    stale = copy.deepcopy(queue)
    stale['heavy']['allocation_sha256'] = '0' * 64
    write(queue_path, stale)
    reject('budget rejects stale queue allocation', budget.check_live)
    write(queue_path, queue)
    # Actual isolated Python children through the accepted process engine.
    supervise = common.supervisor(MAIN)
    child_records = []
    for name, script, timeout in (
            ('success', "print('review Python control')", 2),
            ('nonzero', 'raise SystemExit(7)', 2),
            ('write-escape', "from pathlib import Path;Path(" + repr(str(args.out / 'forbidden-write')) + ").write_text('no')", 2),
            ('deadline-groups', "import os,signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);p=os.fork();os.setpgid(0,0) if p==0 else None;time.sleep(30)", .25)):
        out = args.out / ('python-' + name)
        out.mkdir()
        record = common.run_child([sys.executable, '-s', '-c', script], out, out, 'child', supervise,
                                  timeout=timeout, admit=False)
        write(out / 'record.json', record)
        child_records.append(record)
        want = 'pass' if name == 'success' else 'timeout' if name == 'deadline-groups' else 'fail'
        check('actual Python ' + name, record['outcome'] == want and
              not any(p['state'] != 'Z' for p in record['after']['owned_processes']), record=record)
    check('write confinement left external sentinel absent', not (args.out / 'forbidden-write').exists())
    for sig in (signal.SIGINT, signal.SIGTERM):
        out = args.out / ('controller-' + sig.name)
        out.mkdir()
        stdout = (out / 'stdout.txt').open('wb')
        stderr = (out / 'stderr.txt').open('wb')
        proc = subprocess.Popen([sys.executable, '-s', __file__, '--out', str(out), '--controller'],
                                stdout=stdout, stderr=stderr, start_new_session=True)
        ready = out / 'child.json'
        deadline = time.monotonic() + 4
        while not ready.exists() and time.monotonic() < deadline and proc.poll() is None:
            time.sleep(.01)
        if not ready.exists():
            supervise.terminate(proc)
            check(sig.name + ' controller starts actual child', False)
            stdout.close(); stderr.close()
            continue
        child_pid = int(ready.read_text())
        identity = common.process_identity(child_pid)
        os.kill(proc.pid, sig)
        try:
            code = proc.wait(timeout=4)
        except subprocess.TimeoutExpired:
            supervise.terminate(proc)
            code = proc.returncode
        before_cleanup = supervise.sample(child_pid)
        survivors = [p for p in before_cleanup['owned_processes'] if p['state'] != 'Z']
        check(sig.name + ' controller cleanup leaves no owned child', not survivors,
              controller_exit=code, owned_child_identity=identity, before_reviewer_cleanup=before_cleanup)
        if survivors:
            current = common.process_table().get(child_pid)
            assert current and current['start_ticks'] == identity['start_ticks'], 'Refuse reused child PID'
            supervise.group_signal(child_pid, signal.SIGCONT)
            supervise.group_signal(child_pid, signal.SIGTERM)
            time.sleep(.1)
            supervise.group_signal(child_pid, signal.SIGKILL)
            time.sleep(.1)
        after_cleanup = supervise.sample(child_pid)
        check(sig.name + ' external reviewer cleanup verified',
              not any(p['state'] != 'Z' for p in after_cleanup['owned_processes']), after=after_cleanup,
              external_cleanup_required=bool(survivors))
        stdout.close(); stderr.close()
    write(args.out / 'input-hashes.json', input_hashes)
    report = {'task': 'REV-039', 'experiment': 'REVTAIL-001', 'kind': 'host-test', 'origin': 'local-host',
              'outcome': 'fail' if findings else 'pass', 'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'source_sha256': SOURCE_SHA, 'plan_sha256': PLAN_SHA,
              'checks': records, 'findings': findings, 'elapsed_seconds': time.monotonic() - began,
              'current_image_memory': module.proc_status(), 'target_tools_executed': False,
              'compiler_executed': False, 'linker_executed': False, 'guest_executed': False}
    write(args.out / 'report.json', report)
    print(json.dumps({key: value for key, value in report.items() if key not in ['checks', 'findings']}, indent=2))
    print(json.dumps({'check_count': len(records), 'findings': [item['name'] for item in findings]}, indent=2))
    return 1 if findings else 0


if __name__ == '__main__':
    raise SystemExit(main())
