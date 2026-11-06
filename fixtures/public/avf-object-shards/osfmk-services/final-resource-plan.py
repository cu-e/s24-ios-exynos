#!/usr/bin/env python3
"""Run one original-owner source plan through the accepted process boundary."""
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HELPER = MAIN/'worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py'
PIN = '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def deadline(signum, frame):
    raise KeyboardInterrupt('Root source-plan whole deadline of120seconds')


def main():
    if sha(HELPER) != PIN:
        raise ValueError('Accepted physical EV helper changed')
    spec = importlib.util.spec_from_file_location('accepted_ev_executor', HELPER)
    executor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(executor)
    request_path = Path(__file__).with_name('final-resource-input-request.json')
    with request_path.open() as stream:
        request = json.load(stream)
    out = ROOT/'artifacts/avf-object-shards/osfmk-services/final-resource-source-plan-001'
    if out.exists() or Path(request['proposed_actual_output']).exists():
        raise ValueError('Source plan and proposed actual output must be fresh')
    out.mkdir(parents=True)
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
              'task': request['task'], 'owner': request['owner'], 'experiment': request['experiment'],
              'recorded_at': executor.stamp(), 'helper_sha256': PIN,
              'request_sha256': sha(request_path), 'wrapper_sha256': sha(Path(__file__)),
              'commands': [], 'compiler_started': False, 'guest_executed': False}
    argv = [sys.executable, '-s', str(HELPER), '--mode', 'plan', '--main', str(MAIN),
            '--task', request['task'], '--owner', request['owner'], '--experiment', request['experiment'],
            '--shard', request['shard'], '--resource-profile', 'project-budget-v1',
            '--out', request['source_plan_output']]
    for name, item in request['inputs'].items():
        argv += ['--'+name, item['path'], '--'+name+'-sha256', item['sha256']]
    try:
        supervise = executor.supervisor(MAIN)
        signal.signal(signal.SIGALRM, deadline)
        signal.setitimer(signal.ITIMER_REAL, 120)
        try:
            command = executor.run_child(argv, ROOT, out, 'qualified-source-plan', supervise,
                                         timeout=120, admit=True)
            report['commands'].append(command)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
        if command['outcome'] != 'pass':
            raise RuntimeError('Qualified source plan did not pass: '+command['outcome'])
        target = Path(request['source_plan_output'])
        with (target/'evidence.json').open() as stream:
            actual = json.load(stream)
        with (target/'execution-plan.json').open() as stream:
            plan = json.load(stream)
        if actual['outcome'] != 'pass' or actual['compiler_started'] or actual['objects'] or len(plan['selected']) != 123:
            raise ValueError('Source-plan receipt did not establish the assigned123 noncompiler rows')
        report.update(outcome='pass', summary='One qualified final resource source-only plan passed123 rows; no actual compiler allocation',
                      selected_count=123, namespace_sha256=plan['provenance']['namespace_sha256'],
                      source_plan=str(target/'execution-plan.json'), source_plan_sha256=sha(target/'execution-plan.json'),
                      input_bindings_sha256=sha(target/'input-bindings.json'),
                      runner_evidence_sha256=sha(target/'evidence.json'),
                      selected_ids=actual['selected_ids'], controller_memory=actual['controller_memory'],
                      proposed_actual_output=request['proposed_actual_output'], proposed_actual_output_absent=not Path(request['proposed_actual_output']).exists())
    except BaseException as error:
        report.update(outcome='inconclusive', error=repr(error))
    report['wrapper_current_process_memory'] = executor.actual_controller_memory()
    report['artifacts'] = [str(path) for path in sorted(out.rglob('*')) if path.is_file()]
    report['sha256'] = {name: sha(Path(name)) for name in report['artifacts']}
    executor.write(out/'source-plan-evidence.json', report)
    print(json.dumps({key: report.get(key) for key in ['outcome', 'error', 'source_plan_sha256', 'input_bindings_sha256', 'selected_count', 'proposed_actual_output_absent']}))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
