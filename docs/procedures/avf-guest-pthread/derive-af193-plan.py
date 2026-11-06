#!/usr/bin/env python3
"""Run exactly one original-owner source-plan CLI through accepted AF193."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
ADAPTER = 'worktrees/vm-036-dz-af193-20261106/tools/build/avf_guest_components.py'
ENGINE = 'worktrees/vm-039-ej-20261106/tools/build/avf_kernel_objects.py'
PINS = {
    ADAPTER: 'e62d7592fc35cdc3c011eac2ee537bdcfa09e3ab9308cf17d422e0b7f39e29aa',
    'worktrees/vm-036-dz-af193-20261106/fixtures/public/avf-guest-components/policy.json':
        '748db1c0cc69fdf618fa0167e40ca411629b960377139950c90f34f8f7aa6348',
    ENGINE: 'af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0',
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--main', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    main = args.main.resolve(strict=True)
    out = args.out.absolute()
    if out != out.resolve() or not out.is_relative_to(ROOT/'artifacts/avf-guest-pthread') or out.exists():
        raise ValueError('Fresh canonical original-owner source intake directory required')
    target = ROOT/'artifacts/avf-guest-pthread/compile-1'
    if target.exists():
        raise ValueError('Original component execution output must remain absent')
    for name, expected in PINS.items():
        if sha(main/name) != expected:
            raise ValueError('Frozen source changed: ' + name)
    marker = json.loads((main/'artifacts/team-coordination/20261106-team/components-root-acceptance.json').read_text())
    if (marker['published_head'] != '27352788619e594314a1a85a12f07e82fc279184'
            or marker['common_evidence_sha256'] != 'c92f2b3ccbae80907df4bb1fc35b861184088331b7c172657e09ed0e582a5c6c'
            or marker['common_tests'] != 170 or marker['common_exit'] != 0
            or marker['fresh_original_owner_source_plans_allowed'] is not True
            or marker['actual_component_compile_granted'] is not False):
        raise ValueError('Exact source-plan-only root acceptance required')
    spec = importlib.util.spec_from_file_location('pthread_source_plan_AF193', main/ENGINE)
    engine = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(engine)
    out.mkdir(parents=True)
    argv = [sys.executable, '-s', str(main/ADAPTER), '--mode', 'plan', '--main', str(main),
            '--component', 'pthread', '--task', 'VM-021', '--owner', 'codex-guest-exec-20261106-cy',
            '--experiment', 'AVFPTH-004', '--out', str(out/'plan')]
    record = engine.run_child(argv, ROOT, out, 'source-plan', engine.supervisor(main),
                              timeout=120, admit=True, budget=None)
    record.update(launcher_sha256=sha(Path(__file__)), frozen_sources=PINS,
                  root_marker_sha256=sha(main/'artifacts/team-coordination/20261106-team/components-root-acceptance.json'),
                  source_only=True, actual_experiment='AVFPTH-004', actual_experiment_left_planned=True,
                  original_execution_output_exists=target.exists())
    for name, expected in PINS.items():
        if sha(main/name) != expected:
            raise ValueError('Frozen source changed during source-only child')
    engine.write(out/'supervised.json', record)
    print(json.dumps({k:record.get(k) for k in ['outcome', 'exit_code', 'elapsed_seconds',
                                              'peak_total_owned_rss_bytes', 'original_execution_output_exists']}))
    return 0 if record['outcome'] == 'pass' and not target.exists() else 1


if __name__ == '__main__':
    raise SystemExit(main())
