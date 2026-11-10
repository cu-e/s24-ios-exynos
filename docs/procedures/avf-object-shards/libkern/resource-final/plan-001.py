#!/usr/bin/env python3
"""One final-resource source plan through the existing qualified supervisor."""
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WORKTREE = MAIN / 'worktrees/vm-014-resource-final-20261106'
ENGINE = MAIN / 'worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py'
PIN = '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def main():
    guard = WORKTREE / 'artifacts/avf-object-shards/libkern/resource-final/plan-001'
    guard.mkdir(parents=True, exist_ok=False)
    if sha(ENGINE) != PIN:
        raise ValueError('Canonical accepted EV executor changed')
    fixture = ENGINE.parents[2] / 'fixtures/public/avf-resource-profile/inputs.json'
    profile = json.loads(fixture.read_text())['profile']
    spec = importlib.util.spec_from_file_location('vm014_final_resource_executor', ENGINE)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    argv = [sys.executable, '-s', str(ENGINE), '--mode', 'plan', '--main', str(MAIN),
            '--task', 'VM-014', '--owner', 'codex-guest-exec-20261106-cw',
            '--experiment', 'VMLIBRESOURCEFINAL-001', '--resource-profile', 'project-budget-v1']
    for name in ('manifest', 'qualification', 'selectors'):
        argv += ['--' + name, profile[name]['path'], '--' + name + '-sha256', profile[name]['sha256']]
    argv += ['--shard', 'libkern', '--out', str(guard / 'runner')]
    write(guard / 'invocation.json', {'recorded_at': datetime.now(timezone.utc).isoformat(),
                                     'argv': argv, 'engine_sha256': PIN,
                                     'profile_fixture': str(fixture), 'profile_fixture_sha256': sha(fixture)})
    command = engine.run_child(argv, str(WORKTREE), guard, 'source-plan',
                               engine.supervisor(MAIN), timeout=120, admit=True)
    write(guard / 'supervision.json', command)
    result = {'kind': 'host-test', 'origin': 'local-host', 'recorded_at': datetime.now(timezone.utc).isoformat(),
              'outcome': command['outcome'], 'task': 'VM-014',
              'owner': 'codex-guest-exec-20261106-cw', 'experiment': 'VMLIBRESOURCEFINAL-001',
              'phase': 'source-only final resource plan', 'engine_sha256': PIN,
              'commands': [command], 'compiler_started': False, 'objects_produced': 0,
              'future_actual_output': str(guard.parent / 'build-001')}
    if command['outcome'] == 'pass':
        raw = json.loads((guard / 'runner/evidence.json').read_text())
        plan = json.loads((guard / 'runner/execution-plan.json').read_text())
        if raw['outcome'] != 'pass' or raw['compiler_started'] or raw['commands'] or raw['objects']:
            raise ValueError('Source-only plan did not pass without compiler commands')
        if len(plan['selected']) != 77 or plan.get('resource_profile') != 'project-budget-v1':
            raise ValueError('Wrong libkern selection/resource policy')
        result.update(plan=str(guard / 'runner/execution-plan.json'),
                      plan_sha256=sha(guard / 'runner/execution-plan.json'), selected_count=77,
                      input_bindings_sha256=sha(guard / 'runner/input-bindings.json'),
                      namespace_sha256=raw['provenance']['namespace_sha256'],
                      raw_evidence_sha256=sha(guard / 'runner/evidence.json'),
                      planner_exec_image_hwm_bytes=raw['controller_peak_rss_bytes'])
    result['artifacts'] = [str(path) for path in guard.rglob('*') if path.is_file()]
    result['sha256'] = {name: sha(Path(name)) for name in result['artifacts']}
    write(guard / 'evidence.json', result)
    print(json.dumps({key: result.get(key) for key in ('outcome', 'plan', 'plan_sha256', 'input_bindings_sha256',
                                                      'namespace_sha256', 'selected_count', 'future_actual_output')}, indent=2))
    return result['outcome'] != 'pass'


if __name__ == '__main__':
    sys.dont_write_bytecode = True
    raise SystemExit(main())
