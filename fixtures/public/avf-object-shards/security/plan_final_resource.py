#!/usr/bin/env python3
"""One original-owner source-only plan through the canonical accepted EV helper."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
WT = Path(__file__).resolve().parents[4]
OWNER = 'codex-guest-exec-20261106-dd'
EXECUTOR_SHA = '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755'
FIXTURE_SHA = '8946b29eb8760c1224b5f8a84b67cdb4f0cfb83811f5cdcc35c518fd4877009c'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', type=Path, required=True)
    parser.add_argument('--experiment', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    main_root = args.main.resolve()
    target = main_root / 'worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py'
    fixture = main_root / 'worktrees/vm-046-ev-20261106/fixtures/public/avf-resource-profile/inputs.json'
    if sha(target) != EXECUTOR_SHA or sha(fixture) != FIXTURE_SHA:
        raise ValueError('Canonical accepted EV helper or fixture changed')
    spec = importlib.util.spec_from_file_location('canonical_final_resource_helper', target)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    profile = engine.load_project(fixture, FIXTURE_SHA)['profile']
    if tuple(profile[name]['sha256'] for name in ['manifest', 'qualification', 'selectors']) != (
            engine.RESOURCE_MANIFEST, engine.RESOURCE_QUALIFICATION, engine.RESOURCE_SELECTORS
    ) or profile['namespace_digest'] != engine.RESOURCE_NAMESPACE:
        raise ValueError('EV fixture does not bind the exact final accepted tuple')
    out = engine.canonical_output_path(WT / args.out)
    actual = engine.canonical_output_path(WT / 'artifacts/avf-object-shards/security/final-resource-execute-001/runner')
    if not out.is_relative_to(WT / 'artifacts') or out == WT / 'artifacts' or out.exists() or actual.exists():
        raise ValueError('Fresh source output and absent proposed actual output required')
    out.mkdir(parents=True)
    argv = [sys.executable, '-s', target, '--mode', 'plan', '--main', main_root,
            '--task', 'VM-019', '--owner', OWNER, '--experiment', args.experiment,
            '--shard', 'security', '--resource-profile', 'project-budget-v1', '--out', out / 'runner']
    for name in ['manifest', 'qualification', 'selectors']:
        argv += ['--' + name, profile[name]['path'], '--' + name + '-sha256', profile[name]['sha256']]
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
              'recorded_at': engine.stamp(), 'summary': 'Final resource source plan incomplete',
              'task': 'VM-019', 'owner': OWNER, 'experiment': args.experiment,
              'argv': [sys.executable, *sys.argv], 'worktree': str(WT),
              'adapter_sha256': sha(__file__), 'canonical_executor': str(target),
              'executor_sha256': EXECUTOR_SHA, 'profile_fixture': str(fixture),
              'profile_fixture_sha256': FIXTURE_SHA, 'proposed_actual_output': str(actual),
              'actual_output_absent_before': not actual.exists(), 'compiler_started': False,
              'allocation_requested': False, 'resume_requested': False,
              'old_profile_key_credit': 0, 'commands': []}
    try:
        command = engine.run_child(argv, WT, out, 'final-source-plan', engine.supervisor(main_root),
                                   timeout=120, admit=True)
        report['commands'].append(command)
        if command['outcome'] != 'pass':
            raise ValueError('Final source-only helper did not pass')
        plan = engine.load_project(out / 'runner/execution-plan.json')
        evidence = engine.load_project(out / 'runner/evidence.json')
        selectors = engine.load_project(profile['selectors']['path'], profile['selectors']['sha256'])
        keys = engine.load_project(profile['keys']['path'], profile['keys']['sha256'])['keys']
        key_map = {row['id']: row['input_key'] for row in keys}
        if (plan.get('resource_profile') != 'project-budget-v1'
                or plan['provenance']['namespace_sha256'] != engine.RESOURCE_NAMESPACE
                or len(plan['selected']) != 23
                or [row['id'] for row in plan['selected']] != selectors['shards']['security']
                or any(row['input_key'] != key_map[row['id']] for row in plan['selected'])
                or evidence['compiler_started'] or evidence['commands'] or evidence['objects'] or actual.exists()):
            raise ValueError('Final tuple, exact23 keys, no-compiler boundary or absent actual output differs')
        report.update(outcome='pass', summary='One accepted final-resource full-namespace source plan for23 security IDs; no compiler or allocation',
                      source_plan=str(out / 'runner/execution-plan.json'),
                      source_plan_sha256=sha(out / 'runner/execution-plan.json'),
                      input_bindings_sha256=sha(out / 'runner/input-bindings.json'),
                      namespace_sha256=plan['provenance']['namespace_sha256'],
                      selected_count=len(plan['selected']), resource_profile=plan['resource_profile'],
                      input_keys={row['id']: row['input_key'] for row in plan['selected']},
                      controller_memory=evidence['controller_memory'],
                      owned_after=command['after']['owned_processes'])
    except Exception as error:
        report['error'] = repr(error)
    finally:
        report['actual_output_absent_after'] = not actual.exists()
        report['artifacts'] = [str(path) for path in out.rglob('*') if path.is_file()]
        report['sha256'] = {path: sha(path) for path in report['artifacts']}
        engine.write(out / 'evidence.json', report)
    print(json.dumps({key: report.get(key) for key in ['outcome', 'error', 'source_plan_sha256', 'input_bindings_sha256', 'selected_count', 'proposed_actual_output', 'actual_output_absent_after', 'owned_after']}, indent=2))
    return report['outcome'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
