#!/usr/bin/env python3
"""Continue the completed immutable plan prefix after an integer/boolean assumption."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
HERE = Path(__file__).resolve().parent
out = HERE / 'runs' / sys.argv[1]
out.mkdir(parents=True, exist_ok=False)
record = {'kind': 'source-review', 'origin': 'local-host', 'task': 'INT-003',
          'recorded_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
          'checks': [], 'bindings': {}, 'compiler_executed': False,
          'archiver_executed': False, 'guest_executed': False, 'registry_mutated': False,
          'original_source_matrix_repeated': False, 'execution_admitted': False}


def digest(path):
    path = Path(path)
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    record['bindings'][str(path)] = value
    return value


def check(name, condition):
    record['checks'].append({'name': name, 'pass': bool(condition)})
    if not condition:
        raise ValueError(name)


status = 0
try:
    parent_path = HERE / 'runs/plans1/evidence.json'
    digest(parent_path)
    digest(__file__)
    parent = json.loads(parent_path.read_text())
    check('exact preserved administrative stop', parent['outcome'] == 'fail' and
          parent['error'] == "ValueError('pthread unadmitted')" and
          len(parent['checks']) == 75 and
          all(x['pass'] for x in parent['checks'][:-1]))
    for path, expected in parent['bindings'].items():
        check('unchanged completed-prefix identity ' + path, digest(path) == expected)
    record['completed_parent_checks'] = 74
    p = json.loads((MAIN / 'worktrees/vm-021-20261106/fixtures/public/avf-guest-pthread/compile-plan.json').read_text())
    check('pthread explicitly unadmitted and zero executed commands',
          p['status'] == 'proposed-not-executable' and
          type(p['compiler_archive_commands_executed']) is int and
          p['compiler_archive_commands_executed'] == 0 and p['actual_output_hashes'] is None)
    ledger = json.loads((MAIN / 'state/lab.json').read_text())
    experiments = ledger['experiments']
    experiments = list(experiments.values()) if isinstance(experiments, dict) else experiments
    record['original_owner_registrations'] = []
    for identity, owner in [('AVFFH-001', 'codex-guest-exec-20261106-cx'),
                            ('AVFPTH-003', 'codex-guest-exec-20261106-cy')]:
        rows = [x for x in experiments if x['id'] == identity]
        check(identity + ' original planned registration', len(rows) == 1 and
              rows[0]['owner'] == owner and rows[0]['status'] == 'planned')
        record['original_owner_registrations'].append(rows[0])
    old_runner = MAIN / 'worktrees/vm-009-20261106/tools/build/avf_kernel_objects.py'
    new_runner = MAIN / 'tools/build/avf_kernel_objects.py'
    check('historical physical process tool', digest(old_runner) ==
          '13213539409bade16162173c7b39709dbb3c7e78426fe1410b3f940ea01e4e47')
    check('accepted current process tool', digest(new_runner) ==
          '5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8')
    trees = [{x.name: ast.dump(x, include_attributes=False) for x in ast.parse(q.read_text()).body
              if isinstance(x, ast.FunctionDef)} for q in [old_runner, new_runner]]
    for name in ['run_child', 'landlock', 'stable_memory', 'supervisor', 'actual_controller_memory']:
        check('unchanged process helper AST ' + name, trees[0][name] == trees[1][name])
    check('accepted supervisor', digest(MAIN / 'tools/build/qemu_host.py') ==
          'faaa9b707a8bb48b1ee502a2c58c9b876eb7859ad5b0ff6541bae27c20ed9f99')
    record.update(outcome='pass', summary='Exact four-command units and original registrations pass bounded source intake. Adapter/runtime closure remains unadmitted; no source matrix/build replay.')
except Exception as error:
    record.update(outcome='fail', error=repr(error))
    status = 1
finally:
    record['exit_code'] = status
    record['finished_at'] = datetime.now(timezone.utc).isoformat()
    record['process_memory'] = [x for x in Path('/proc/self/status').read_text().splitlines()
                                if x.startswith(('VmRSS:', 'VmHWM:'))]
    (out / 'evidence.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'outcome': record['outcome'], 'evidence': str(out / 'evidence.json'),
                      'error': record.get('error')}))
sys.exit(status)
