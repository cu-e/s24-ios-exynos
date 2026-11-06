#!/usr/bin/env python3
"""Source-only VM022 admission/recipe controls; never launch target tools."""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import resource
import struct
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--main', type=Path, required=True)
parser.add_argument('--vm008', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
path = root / 'tools/build/avf_guest_link_inputs.py'
spec = importlib.util.spec_from_file_location('vm022_tail_controls', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
args.out = args.out.absolute()
args.out.mkdir(parents=True, exist_ok=False)
report = dict(kind='host-test', outcome='fail', source_only=True, target_tool_executed=False,
              builder_sha256=module.sha(path), checks=[], initial_process=module.proc_status())
def require(name, condition):
    if not condition:
        raise AssertionError(name)
    report['checks'].append(name)
def reject(name, call):
    try:
        call()
    except (ValueError, KeyError):
        report['checks'].append(name)
        return
    raise AssertionError('Failed rejection: ' + name)
try:
    common = module.accepted_runner(args.main.resolve())
    future = root / 'artifacts/avf-guest-link-inputs/tails-execute-1'
    plan_args = SimpleNamespace(main=args.main, vm008=args.vm008, execute_out=future)
    plan = module.tail_plan(plan_args, common)
    require('all four genuine tails, ordered once', tuple(row['target'] for row in plan['commands']) == module.TAILS)
    require('no production output created', not future.exists())
    require('actual OBJROOT proved by original successful Make query',
            plan['original_OBJROOT_assignment'] == 'OBJROOT=' + plan['resolved_OBJROOT'])
    for row in plan['commands']:
        original, actual = row['original_argv'], row['argv']
        require(row['target'] + ': all original flags/positions preserved except declared substitutions',
                len(actual) == len(original)+2 and actual[-2:] == ['-o', row['object']] and
                {i for i, (a, b) in enumerate(zip(original, actual)) if a != b} ==
                {change['position'] for change in row['substitutions']})
        require(row['target'] + ': no extra include root or flag',
                sum(arg.startswith('-I') for arg in original) == sum(arg.startswith('-I') for arg in actual))
        require(row['target'] + ': real sanitizer and export roots exist',
                all(Path(arg[2:]).is_dir() for arg in actual if arg.startswith('-I'+plan['resolved_OBJROOT']+'/EXPORT_HDRS') and not arg.endswith('/libsa')) and
                all(Path(arg.split('=', 1)[1]).is_file() for arg in actual if arg.startswith('-fsanitize-ignorelist=')))
    row = plan['commands'][0]
    original = row['original_argv']
    import shlex
    descriptor = common.load_project(args.main / ('worktrees/vm-038-20261106/docs/procedures/'
        'avf-firehose-namespace/qualification-session1/qualified-component.json'), module.NAMESPACE_DESCRIPTOR_SHA)
    def resolve(tokens):
        return module.resolve_tail_argv(shlex.join(tokens), row['target'], Path(plan['original_query_root']),
            Path(plan['resolved_OBJROOT']), descriptor['old_root']['path'], descriptor['new_root']['path'], future)
    bad = original.copy(); bad[bad.index('-MF')+1] = 'foreign.d'
    reject('reject dependency-output mismatch', lambda: resolve(bad))
    reject('reject pre-existing compiler output redirect', lambda: resolve(original + ['-o', '/tmp/foreign.o']))
    reject('reject LTO profile change', lambda: resolve(original + ['-flto']))
    bad = [token for token in original if token != '-I'+descriptor['old_root']['path']]
    reject('reject missing accepted namespace transition', lambda: resolve(bad))
    bad = original + ['-I'+plan['original_query_root']+'/unreviewed']
    reject('reject unexplained query-root substitution', lambda: resolve(bad))
    invalid = SimpleNamespace(**vars(plan_args)); invalid.execute_out = args.main/'artifacts/foreign-tail-output'
    reject('reject output outside original owner worktree', lambda: module.tail_plan(invalid, common))
    # Small synthetic parser control only; never a production object or image.
    raw = args.out/'synthetic-rename-input.bin'
    transformed = args.out/'synthetic-rename-result.bin'
    header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 1, 1, 152, 0, 0)
    segment = struct.pack('<II16s4Q4I', 25, 152, b'', 0, 8, 184, 8, 7, 3, 1, 0)
    section = struct.pack('<16s16sQQ8I', b'__mod_init_func', b'__DATA', 0, 8, 184, 3, 0, 0, 9, 0, 0, 0)
    original_bytes = header+segment+section+b'12345678'
    raw.write_bytes(original_bytes)
    result_bytes = bytearray(original_bytes)
    result_bytes[120:136] = b'__LASTDATA_CONST'[:16].ljust(16, b'\0')
    transformed.write_bytes(result_bytes)
    common.macho(raw); common.macho(transformed)
    require('exact full-width16-byte constructor section rename accepted',
            module.verify_constructor_transform(raw, transformed) == ['__mod_init_func'])
    result_bytes[-1] ^= 1; transformed.write_bytes(result_bytes)
    reject('reject any changed payload byte outside constructor segment field',
           lambda: module.verify_constructor_transform(raw, transformed))
    saved_argv = sys.argv
    guard_out = root/'artifacts/avf-guest-link-inputs/unleased-guard-control'
    sys.argv = [str(path), '--main', str(args.main), '--vm008', str(args.vm008),
                '--out', str(guard_out), '--mode', 'execute-tails']
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            try:
                module.main()
            except SystemExit as error:
                require('execution without exact approval/plan rejected before output creation', error.code == 2 and not guard_out.exists())
            else:
                raise AssertionError('Unleased execution was admitted')
    finally:
        sys.argv = saved_argv
    report['outcome'] = 'pass'
except Exception as error:
    report['error'] = repr(error)
finally:
    report['final_process'] = module.proc_status()
    report['raw_ru_maxrss_bytes'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
    (args.out/'evidence.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
raise SystemExit(0 if report['outcome'] == 'pass' else 1)
