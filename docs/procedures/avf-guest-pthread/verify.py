#!/usr/bin/env python3
"""Exercise real source-plan rejection controls without a compiler."""
from copy import deepcopy
from datetime import datetime, timezone
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('avf_guest_pthread', ROOT / 'tools/build/avf_guest_pthread.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.absolute()
    if out != out.resolve() or not out.is_relative_to(ROOT / 'artifacts/avf-guest-pthread'):
        raise ValueError('Fresh canonical owned controls output required')
    out.mkdir(parents=True, exist_ok=False)
    report = {'kind': 'host-test', 'origin': 'local-host', 'outcome': 'fail',
              'recorded_at': datetime.now(timezone.utc).isoformat(), 'argv': sys.argv,
              'verifier_sha256': module.digest(Path(__file__)), 'builder_sha256': module.digest(Path(module.__file__)),
              'plan_sha256': module.digest(args.plan), 'checks': [], 'compiler_executed': False,
              'callback_ABI_qualified': False, 'guest_executed': False}
    started = time.monotonic()

    def reject(name, operation):
        try:
            operation()
        except ValueError as error:
            report['checks'].append({'name': name, 'pass': True, 'rejection': str(error)})
        else:
            report['checks'].append({'name': name, 'pass': False})
            raise ValueError('Control unexpectedly accepted: ' + name)

    try:
        plan = module.load(args.plan)
        module.validate_plan(plan)
        report['checks'].append({'name': 'actual-source-plan-positive', 'pass': True})
        for row in plan['translation_units']:
            module.require_hash(Path(row['source']), row['source_sha256'])
        report['checks'].append({'name': 'three-actual-source-hashes-positive', 'pass': True})
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'].append('-DARM64_BOARD_CONFIG_E1S')
        reject('reject-E1S-board-input', lambda: module.validate_plan(wrong))
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'] += ['-I', '/actual/EXPORT_HDRS/bsd']
        reject('reject-raw-internal-kext-header-fallback', lambda: module.validate_plan(wrong))
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'].append('/historical/libpthread_kext.a')
        reject('reject-historical-archive-input', lambda: module.validate_plan(wrong))
        wrong = deepcopy(plan)
        wrong['translation_units'][0]['argv_template'].remove('-DXNU_NO_TYPE_BUILTINS=0')
        reject('reject-absent-real-type-builtins', lambda: module.validate_plan(wrong))
        wrong = deepcopy(plan)
        wrong['compiled_objects'] = ['unmeasured.o']
        reject('reject-forged-compiled-object-claim', lambda: module.validate_plan(wrong))
        wrong = deepcopy(plan)
        wrong['translation_units'].pop()
        reject('reject-missing-genuine-translation-unit', lambda: module.validate_plan(wrong))
        with tempfile.TemporaryDirectory(prefix='changed-source-', dir=out) as temporary:
            original = Path(plan['translation_units'][0]['source'])
            changed = Path(temporary) / original.name
            changed.write_bytes(original.read_bytes() + b'\n/* wrong-source control */\n')
            reject('reject-changed-source-bytes', lambda: module.require_hash(changed, plan['translation_units'][0]['source_sha256']))
        witness = module.load(args.plan.parent / 'callback-alias-source-witness.json')
        actual = Path(witness['source']).read_text()
        changed = actual.replace('int version;', 'long version;', 1)
        if changed == actual or module.fields(changed) == module.fields(actual):
            raise ValueError('Changed callback declaration was not detected')
        report['checks'].append({'name': 'detect-changed-real-callback-declaration', 'pass': True,
                                 'limit': 'Text declaration surface only; compiled ABI/type rejection remains unmeasured'})
        report['outcome'] = 'pass'
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        print(report['error'], file=sys.stderr)
    finally:
        report['elapsed_seconds'] = time.monotonic() - started
        report['current_process_VmHWM_KiB'] = int(re.search(r'^VmHWM:\s+(\d+)', Path('/proc/self/status').read_text(), re.M).group(1))
        module.dump(out / 'evidence.json', report)
    print(json.dumps({'outcome': report['outcome'], 'checks': len(report['checks'])}))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
