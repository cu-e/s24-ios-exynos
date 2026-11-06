#!/usr/bin/env python3
"""Inspect only ROOT120's new records; join already reviewed BSD consumers."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import struct
import sys

sys.dont_write_bytecode = True
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
WT = Path(__file__).resolve().parents[4]
PRODUCER = MAIN / 'worktrees/str-018-e1s-development-providers-20261106'
OUT = WT / 'artifacts/native-provider-final-qualification-review/numeric-002'
PINS = {}
CHECKS = 0

def require(value, note):
    global CHECKS
    CHECKS += 1
    if not value:
        raise ValueError(note)
    status = Path('/proc/self/status').read_text()
    rss = int(next(line.split()[1] for line in status.splitlines() if line.startswith('VmRSS:'))) * 1024
    if rss > 256 * 1024**2:
        raise ValueError('Review RSS cap exceeded')

def pin(path, expected=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), str(path))
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    with path.open('rb') as f:
        before = os.fstat(f.fileno())
        digest = hashlib.file_digest(f, 'sha256').hexdigest()
        after = os.fstat(f.fileno())
    require(identity(before) == identity(after) == identity(path.stat()), 'Changed input: ' + str(path))
    require(expected is None or digest == expected, 'Hash mismatch: ' + str(path))
    PINS[str(path)] = digest
    return digest

def load(path, expected):
    pin(path, expected)
    require(Path(path).stat().st_size < 16 * 1024**2, 'Oversized JSON')
    return json.loads(Path(path).read_bytes())

def module(path, expected, name):
    pin(path, expected)
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def main():
    # Python3.14 starts near256MiB virtual space; retain256MiB actual RSS cap.
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2,) * 2)
    OUT.mkdir(parents=True, exist_ok=False)
    plan = load(PRODUCER / 'artifacts/e1s-development-providers/layout-plan-003/execution-plan.json',
                '931a7f8bde90b9c348aaa1a7ab6f41abcb10106356d13b4e3e4d21074d35555d')
    raw = load(PRODUCER / 'artifacts/e1s-development-providers/layout-probe-001/evidence.json',
               '2ff3a1f7c44839000e6441757f086ee32b5c583278b91d2503900b3cb5e0936d')
    root = load(MAIN / 'artifacts/team-coordination/20261106-team/native-layout120/evidence.json',
                'c3cd0e91153ebdaa21d2465d27a43326c11a4655e2ac2aed5b3e535e46349c94')
    control = load(MAIN / 'artifacts/team-coordination/20261106-team/native-layout120/control-plan-v2.json',
                   'fde8baed524273a277c33d54aefbaf9dfa751ec846046e84d40841538fc9c295')
    pin(control['source_review']['path'], control['source_review']['sha256'])
    require(root['outcome'] == raw['outcome'] == 'pass', 'Actual/root outcome')
    require(root['released'] and root['owned_survivors'] == [] and root['stop_reason'] is None, 'Root cleanup')
    require(root['commands'][0]['exit_code'] == 0 and root['commands'][0]['evidence_sha256'] ==
            PINS[str(PRODUCER / 'artifacts/e1s-development-providers/layout-probe-001/evidence.json')], 'Root/raw relation')
    require(raw['source_plan_sha256'] == PINS[str(PRODUCER / 'artifacts/e1s-development-providers/layout-plan-003/execution-plan.json')], 'Source/raw relation')
    require(len(raw['commands']) == len(raw['objects']) == len(plan['commands']) == 2, 'Two records only')
    require(control['commands'] == plan['commands'], 'Root/source commands')
    require(raw['owned_survivors'] == [] and raw['own_reservation_released'] and
            raw['layout_differences'] == [] and raw['layout_agreement'], 'Child cleanup/agreement')
    catalog = load(plan['dependency_source_catalog']['path'], plan['dependency_source_catalog']['sha256'])
    expected = {**plan['source_bindings_sha256'], **catalog['sha256_by_path']}
    api = plan['inspection']['existing_core_API']
    core = module(api['path'], api['sha256'], 'cn_numeric_core')
    common = module(MAIN / 'worktrees/vm-046-ev-20261106/tools/build/avf_kernel_objects.py',
                    '9929a7d6f1e748770f54abf3e101350648092027a18c419a242d0348f620f755', 'cn_numeric_common')
    records = []
    for row, cmd, item in zip(plan['commands'], raw['commands'], raw['objects']):
        require(cmd['argv'] == row['argv'] and cmd['cwd'] == row['cwd'], 'Exact command/cwd')
        require(cmd['exit_code'] == 0 and cmd['execution_outcome'] == cmd['resource_qualification'] == cmd['outcome'] == 'pass', 'Actual compile/resource outcome')
        require(cmd['after']['owned_processes'] == [], 'Per-command cleanup')
        pin(row['object'], item['sha256'])
        pin(row['depfile'], item['MD_sha256'])
        deps = common.dependencies(row['depfile'], row['cwd'], row['object'])
        require(set(deps) == set(item['actual_dependencies']) and row['source']['path'] in deps, 'Actual MD target/TU/set')
        for path in deps:
            require(path in expected and item['actual_dependencies'][path] == expected[path], 'Qualified actual MD identity')
            if path not in PINS:
                pin(path, expected[path])
        with core.macho_snapshot(row['object']) as (snapshot, view):
            symbols = list(view['external_symbols'].items())
            require(len(symbols) == 1 and symbols[0][0] == row['symbol'], 'One expected external symbol')
            sym = symbols[0][1]
            require(not sym['undefined'] and sym['section'] > 0, 'Defined record')
            sec = view['sections'][sym['section'] - 1]
            require(sec == item['section'] and sec['segment'] == '__DATA_CONST' and sec['name'] == '__s24fh' and
                    sec['size'] == 224 and sec['align'] >= 3 and sec['flags'] & 255 == 0 and
                    sec['relocation_count'] == 0 and sym['value'] == sec['address'], 'Exact file-backed nonrelocated record')
            require(not any(s['name'] == '__text' and s['size'] for s in view['sections']), 'No functions')
            data = snapshot.read_range(sec['offset'], 224)
            values = list(struct.unpack('<28Q', data))
            record = dict(zip(plan['record']['columns'], values))
            require(values == item['words'] and record == item['record'], 'Physical record agrees with raw')
            require(hashlib.sha256(data).hexdigest() == item['record_sha256'], 'Record hash')
            require(all(record[k] == v for k, v in {**plan['record']['required_metadata'], **plan['record']['required_tuple']}.items()), 'Measured required metadata/CPU tuple')
            records.append({'id': row['id'], 'object': row['object'], 'sha256': item['sha256'],
                            'actual_MD_count': len(deps), 'record': record, 'record_sha256': item['record_sha256']})
    require(all(records[0]['record'][plan['record']['columns'][i]] == records[1]['record'][plan['record']['columns'][i]]
                for i in plan['record']['compare_equal_column_indexes']), 'Actual structural field equality')
    cm = MAIN / 'worktrees/int-e1s-profile-20261106/artifacts/integration-gate/e1s-source-review-20261106/native115-actual-001'
    accepted = load(cm / 'final-review.json', 'efc8e00a2d955950fd9e8c2f41c59fbf1f26c6dfb477dce0791eb34bb2e873b1')
    consumers = load(cm / 'native-consumers.json', '1098c5f9d191bfdef08d6c9300ccbe96057db4d585d9ca89b0102f731b470531')
    observed = load(PRODUCER / 'artifacts/e1s-development-providers/consumer-read-001/observations.json',
                    'b3274ce3a034e786a533a75faee82f5c7276c3068dc90ac6bae71396ffbc14bd')
    require(accepted['outcome'] == 'ACCEPT new158 and original-origin complete170 BSD-b native objects', 'Independent actual consumer authority')
    for authority, observation in zip(consumers, observed['products']):
        require(authority['id'] == observation['id'], 'Consumer ID')
        require(authority['object'] == observation['object']['path'] and authority['object_sha256'] == observation['object']['sha256'], 'Consumer object tuple')
        require(authority['depfile'] == observation['MD']['path'] and authority['depfile_sha256'] == observation['MD']['sha256'], 'Consumer MD tuple')
        require(authority['actual_MD_dependencies'] == observation['actual_MD_dependencies_sha256'], 'Reuse independent actual MD closure')
        require(set(authority['strong_definitions']) == set(observation['external_definitions']) and
                set(authority['imports_retained']) == set(observation['external_imports']), 'Independent consumer symbol facts')
    pin(__file__)
    result = {'kind': 'source-review', 'task': 'INT-003', 'owner': 'codex-integrator-platform-20261106-cn',
              'outcome': 'ACCEPT actual auxiliary numeric records and native consumer identity/symbol join only',
              'checks': CHECKS, 'numeric_records': records, 'native_consumers': [{k:o[k] for k in ('id','object','MD')} for o in observed['products']],
              'old_product_or_consumer_decoder_replayed': False, 'new_numeric_objects_inspected_with_existing_core': True,
              'limits': ['Auxiliary probes do not enter archives or final kernel.', 'Source capacity tuple10/4/9 is not measured live topology or hardware.',
                         'Final owner semantic/alias descriptor and exact task-criteria assessment pending.', 'Full private ABI/link/image/runtime/hardware and STR018 closure unqualified.'],
              'RSS_cap_bytes': 256 * 1024**2, 'RLIMIT_AS_bytes': 512 * 1024**2,
              'prior_reviewer_import_failure_preserved': str(OUT.parent / 'numeric-001/failure.json'),
              'VmHWM_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024, 'artifact_sha256': PINS}
    output = OUT / 'evidence.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'outcome': result['outcome'], 'checks': CHECKS, 'bindings': len(PINS), 'VmHWM_bytes': result['VmHWM_bytes'],
                      'path': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}))

if __name__ == '__main__':
    main()
