#!/usr/bin/env python3
"""Focused frozen-plan predicate checks; never open source/header trees."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('pthread_predicate', ROOT / 'tools/build/avf_guest_pthread.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
BASELINE = 'f10dda9c713c7b6a1516ff77f9d62d8340205805'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.absolute()
    if out != out.resolve() or not out.is_relative_to(ROOT / 'artifacts/avf-guest-pthread'):
        raise ValueError('Fresh canonical owned predicate output required')
    out.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'argv': sys.argv,
              'builder_sha256': module.digest(Path(module.__file__)),
              'verifier_sha256': module.digest(Path(__file__)),
              'freeze_sha256': module.digest(module.EXECUTION_FREEZE),
              'plan_sha256_before': module.digest(args.plan), 'checks': [], 'commands': [],
              'source_or_header_tree_opened': False, 'compiler_executed': False,
              'archive_produced': False, 'guest_executed': False, 'compiled_ABI_accepted': False}

    def reject(name, wrong):
        try:
            module.validate_plan(wrong)
        except ValueError as error:
            report['checks'].append({'name': name, 'pass': True, 'rejection': str(error)})
        else:
            report['checks'].append({'name': name, 'pass': False})
            raise ValueError('Changed plan was accepted: ' + name)

    try:
        freeze = module.load(module.EXECUTION_FREEZE)
        if report['plan_sha256_before'] != freeze['source_plan_sha256']:
            raise ValueError('Original frozen plan bytes required')
        plan = module.load(args.plan)
        module.validate_plan(plan)
        report['checks'].append({'name': 'unchanged-original-frozen-plan', 'pass': True})
        module.validate_plan(json.loads(json.dumps(plan, sort_keys=True)))
        report['checks'].append({'name': 'equivalent-JSON-object-order', 'pass': True})

        argv = ['git', '-C', str(ROOT), 'show', BASELINE + ':tools/build/avf_guest_pthread.py']
        process = subprocess.run(argv, env=dict(os.environ, GIT_NO_LAZY_FETCH='1',
                                 GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0'),
                                 capture_output=True, timeout=10)
        legacy_path = out / 'original-builder.py'
        legacy_path.write_bytes(process.stdout)
        (out / 'original-builder.stderr').write_bytes(process.stderr)
        report['commands'].append({'argv': argv, 'exit_code': process.returncode, 'timeout_seconds': 10,
                                   'stdout': str(legacy_path), 'stdout_sha256': module.digest(legacy_path),
                                   'stderr': str(out / 'original-builder.stderr'),
                                   'stderr_sha256': module.digest(out / 'original-builder.stderr')})
        if process.returncode:
            raise ValueError('Original committed predicate unavailable')
        legacy_spec = importlib.util.spec_from_file_location('original_pthread_predicate', legacy_path)
        legacy = importlib.util.module_from_spec(legacy_spec)
        legacy_spec.loader.exec_module(legacy)
        wrong = deepcopy(plan)
        for row in wrong['translation_units']:
            row['argv_template'] = [a for a in row['argv_template'] if a not in ['-DMACH_ASSERT', '-DDEBUG']]
        legacy.validate_plan(wrong)
        report['checks'].append({'name': 'reproduce-original-missing-development-definitions-accepted',
                                 'pass': True, 'baseline_commit': BASELINE,
                                 'limit': 'This reproduces a validator defect, not a valid compilation profile.'})
        reject('reject-both-development-definitions-dropped-from-all-TUs', wrong)

        for flag in ['-DMACH_ASSERT', '-DDEBUG']:
            wrong = deepcopy(plan)
            wrong['translation_units'][1]['argv_template'].remove(flag)
            reject('reject-missing-' + flag[2:], wrong)
        for flag in ['-UDEBUG', '-UMACH_ASSERT', '-DDEBUG=0', '-DMACH_ASSERT=0', '-DDEBUG=1',
                     '-Wp,-UDEBUG', '@untrusted-response-file']:
            wrong = deepcopy(plan)
            wrong['translation_units'][2]['argv_template'].append(flag)
            reject('reject-added-override-' + flag, wrong)
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'] += ['-U', 'DEBUG']
        reject('reject-split-undefine', wrong)
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'] += ['-Xpreprocessor', '-UDEBUG']
        reject('reject-forwarded-undefine', wrong)
        for option in ['-o', '-MF']:
            wrong = deepcopy(plan)
            argv = wrong['translation_units'][0]['argv_template']
            argv[argv.index(option) + 1] = '@UNDECLARED_OUT@/redirected'
            reject('reject-output-redirection-' + option, wrong)
        wrong = deepcopy(plan)
        row = wrong['translation_units'][0]
        row['argv_template'][row['argv_template'].index(row['source'])] = '/other/source.c'
        row['source'] = '/other/source.c'
        reject('reject-source-namespace-change', wrong)
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'][0] = '/other/compiler'
        reject('reject-compiler-replacement', wrong)
        wrong = deepcopy(plan)
        wrong['variant'] = 'normal'
        reject('reject-nondevelopment-plan-metadata', wrong)

        report['plan_sha256_after'] = module.digest(args.plan)
        if report['plan_sha256_after'] != report['plan_sha256_before']:
            raise ValueError('Original plan bytes changed')
        report['checks'].append({'name': 'original-plan-byte-identity-preserved', 'pass': True})
        report['outcome'] = 'pass'
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        print(report['error'], file=sys.stderr)
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        report['current_process_VmHWM_KiB'] = int(re.search(r'^VmHWM:\s+(\d+)', Path('/proc/self/status').read_text(), re.M).group(1))
        report['controller_exit_code'] = 0 if report['outcome'] == 'pass' else 1
        module.dump(out / 'evidence.json', report)
    print(json.dumps({'outcome': report['outcome'], 'checks': len(report['checks'])}))
    return report['controller_exit_code']


if __name__ == '__main__':
    raise SystemExit(main())
