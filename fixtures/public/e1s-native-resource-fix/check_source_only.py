#!/usr/bin/env python3
"""Source-only STR-039 checks: no compiler, preprocessor, loader or Make runs.

Exercises the real rebind/resource functions against the recorded failed APFS
argv, all 1042 genuine recipes and mutated copies of the qualified headers.
"""
import argparse
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
ACCEPTED = MAIN/'worktrees/str-030-e1s-native-compile-fix2-20261106/fixtures/public/e1s-native-compile/native_compile.py'
ACCEPTED_SHA = '2676a8edb31b0136aa7195d37523549d9c77edee7ac140a7f476ebf5064b178f'
FAILED_ROW = MAIN/'worktrees/str-024-e1s-native-objects-bsd-a-20261106/docs/procedures/e1s-native-objects/bsd-a/build-005/failed-row-context.json'
PROOF = MAIN/'docs/procedures/avf-resource-namespace/guard-session3/qualification/canonical-resource-proof.json'
PROOF_SHA = '25024c71b9a18dfb7b615760e4c61d1bd3daf277d56acc0d7f6bb8f3d8fa243e'
INTERFACE = MAIN/'worktrees/str-016-e1s-development-body-graph-20261106/fixtures/public/e1s-development-body-graph/qualified-graph.json'
COMPILER_SHA = '7972eb2820ae25b5bedff1ea954cef9e9a0e4a15c7a8e440628e8b6540fafc82'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def load_caller():
    spec = importlib.util.spec_from_file_location('resource_caller', HERE/'native_compile.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Checks:
    def __init__(self):
        self.rows = []

    def expect(self, name, condition, detail=None):
        self.rows.append(dict(name=name, outcome='pass' if condition else 'fail', detail=detail))
        if not condition:
            raise SystemExit(f'FAILED {name}: {detail}')

    def rejects(self, name, needle, function, *args, **kwargs):
        try:
            function(*args, **kwargs)
        except ValueError as error:
            self.expect(name, needle in str(error), str(error))
            return
        self.expect(name, False, 'accepted invalid input')


def check_delta(checks):
    checks.expect('accepted-caller-sha', sha(ACCEPTED) == ACCEPTED_SHA)
    old = ACCEPTED.read_text().splitlines()
    new = (HERE/'native_compile.py').read_text().splitlines()
    changes = [op for op in difflib.SequenceMatcher(a=old, b=new, autojunk=False).get_opcodes() if op[0] != 'equal']
    summary = [dict(tag=t, old=old[a:b], new_lines=d-c) for t, a, b, c, d in changes]
    patch = ''.join(difflib.unified_diff([l+'\n' for l in old], [l+'\n' for l in new], 'accepted/native_compile.py', 'str-039/native_compile.py', n=1))
    checks.expect('delta-equals-committed-patch', patch == (HERE/'source-delta.patch').read_text(), len(patch))
    replaced = [old[a:b] for t, a, b, _, _ in changes if t == 'replace']
    checks.expect('delta-replaces-only-docstring-and-runtime-pin',
                  [len(r) for r in replaced] == [1, 1] and replaced[0][0].startswith('"""Derive') and replaced[1][0].startswith('RUNTIME_SHA = ')
                  and all(t in ['replace', 'insert'] for t, *_ in changes), summary)
    checks.expect('same-byte:source-metadata.json', sha(HERE/'source-metadata.json') == sha(ACCEPTED.parent/'source-metadata.json'))
    accepted_runtime = json.loads((ACCEPTED.parent/'runtime.json').read_text())
    current_runtime = json.loads((HERE/'runtime.json').read_text())
    drift = {k: (accepted_runtime['files'][k], current_runtime['files'][k]) for k in accepted_runtime['files'] if accepted_runtime['files'][k] != current_runtime['files'][k]}
    checks.expect('runtime-only-ld-so-cache-repinned', list(drift) == ['/etc/ld.so.cache'] and set(current_runtime['files']) == set(accepted_runtime['files'])
                  and {k: v for k, v in accepted_runtime.items() if k != 'files'} == {k: v for k, v in current_runtime.items() if k != 'files'}
                  and current_runtime['files']['/etc/ld.so.cache'] == sha('/etc/ld.so.cache'), drift)
    return summary


def check_rebind(checks, caller):
    row = json.loads(FAILED_ROW.read_text())
    argv = row['actual_argv']
    checks.expect('failed-row-is-apfs', row['id'] == caller.RESOURCE_OBJECT and row['missing_header'] == 'arm_neon.h')
    checks.expect('failed-operand-is-absent-root', argv[216] == '-idirafter' and argv[217] == caller.RESOURCE_ABSENT)
    result = caller.rebind_resource(caller.RESOURCE_OBJECT, argv)
    changed = [n for n, (a, b) in enumerate(zip(argv, result)) if a != b]
    checks.expect('only-resource-operand-changes', len(result) == len(argv) and changed == [217] and result[217] == str(caller.RESOURCE_ROOT), changed)
    plain = [a for a in argv if a != '-idirafter' and a != caller.RESOURCE_ABSENT]
    checks.expect('non-selected-row-unchanged', caller.rebind_resource('bsd/other.o', plain) == plain)
    checks.rejects('reject-wrong-id-with-operand', 'outside selected', caller.rebind_resource, 'bsd/other.o', argv)
    wrong = list(argv); wrong[217] = str(caller.RESOURCE_ROOT)
    checks.rejects('reject-wrong-operand', 'exact genuine', caller.rebind_resource, caller.RESOURCE_OBJECT, wrong)
    twice = list(argv)+['-idirafter', caller.RESOURCE_ABSENT]
    checks.rejects('reject-duplicate-operand', 'exact genuine', caller.rebind_resource, caller.RESOURCE_OBJECT, twice)
    extra = list(argv)+['-I'+caller.RESOURCE_ABSENT]
    checks.rejects('reject-extra-mention', 'exact genuine', caller.rebind_resource, caller.RESOURCE_OBJECT, extra)
    checks.rejects('reject-missing-operand', 'exact genuine', caller.rebind_resource, caller.RESOURCE_OBJECT, plain)
    with tempfile.TemporaryDirectory(dir=str(MAIN/'artifacts')) as scratch:
        present = str(Path(scratch).resolve())
        materialized = [present if a == caller.RESOURCE_ABSENT else a for a in argv]
        checks.rejects('reject-materialized-absent-root', 'unexpectedly exists', caller.rebind_resource, caller.RESOURCE_OBJECT, materialized, absent=present)


def check_resources(checks, caller):
    real = caller.resource_inputs()
    checks.expect('real-resource-root-qualifies', sorted(Path(p).name for p in real) == ['arm_acle.h', 'arm_bf16.h', 'arm_neon.h'], real)
    with tempfile.TemporaryDirectory(dir=str(MAIN/'artifacts')) as scratch:
        base = Path(scratch).resolve()
        def fresh(name):
            root = base/name
            root.mkdir()
            for header in caller.RESOURCE_HEADERS:
                shutil.copyfile(caller.RESOURCE_ROOT/header, root/header)
            return root
        checks.expect('copy-qualifies', len(caller.resource_inputs(fresh('good'))) == 3)
        root = fresh('hash')
        with (root/'arm_neon.h').open('ab') as stream:
            stream.write(b'\n')
        checks.rejects('reject-changed-header', 'Changed resource header', caller.resource_inputs, root)
        root = fresh('missing'); (root/'arm_bf16.h').unlink()
        checks.rejects('reject-missing-header', 'missing or shadowing', caller.resource_inputs, root)
        root = fresh('shadow'); (root/'stdint.h').write_text('/* shadow */\n')
        checks.rejects('reject-shadow-header', 'missing or shadowing', caller.resource_inputs, root)
        root = fresh('symlink'); (root/'arm_acle.h').unlink(); (root/'arm_acle.h').symlink_to(caller.RESOURCE_ROOT/'arm_acle.h')
        checks.rejects('reject-symlink-header', 'Changed resource header', caller.resource_inputs, root)
        alias = base/'alias'; alias.symlink_to(fresh('target'))
        checks.rejects('reject-symlink-root', 'canonical directory', caller.resource_inputs, alias)
        checks.rejects('reject-file-root', 'canonical directory', caller.resource_inputs, base/'absent')


def check_authority(checks, caller):
    checks.expect('proof-sha', sha(PROOF) == PROOF_SHA)
    proof = json.loads(PROOF.read_text())
    checks.expect('proof-compiler-lineage', proof['final_compiler']['sha256'] == COMPILER_SHA and proof['source_revision'] == 'fa9443738c1a18accef4244732ec6d6ee97a8133')
    checks.expect('proof-header-hashes', {k: v['sha256'] for k, v in proof['generated_headers'].items()} == caller.RESOURCE_HEADERS)
    checks.expect('recorded-generation-report-exists', sha(proof['generation_report']['path']) == proof['generation_report']['sha256'])


def check_graph(checks, caller):
    interface = json.loads(INTERFACE.read_text())
    graph = json.loads(Path(interface['graph']['path']).read_text())
    selected = []
    for row in graph['objects']:
        recipe = json.loads(Path(row['recipe']['path']).read_text())
        argv = shlex.split(recipe['expanded_steps_by_query_BOUND_CHECKS']['0']['1'])
        result = caller.rebind_resource(row['id'], argv)
        if result != argv:
            selected.append(row['id'])
    checks.expect('all-1042-recipes-pass-through', len(graph['objects']) == 1042 and selected == [caller.RESOURCE_OBJECT], selected)


def check_plan(checks, plan_path, caller):
    plan = json.loads(Path(plan_path).read_text())
    row = plan['commands'][0]
    failed = json.loads(FAILED_ROW.read_text())
    checks.expect('plan-single-apfs-row', [c['id'] for c in plan['commands']] == [caller.RESOURCE_OBJECT])
    checks.expect('plan-original-argv-preserved', row['original_argv'] == failed['original_argv'])
    actual = list(failed['actual_argv'])
    planned = list(row['argv'])
    differ = [n for n, (a, b) in enumerate(zip(actual, planned)) if a != b]
    allowed = {n for n, a in enumerate(actual) if 'artifacts/e1s-native-compile/bsd-a-build-005/' in a}
    checks.expect('plan-argv-differs-only-in-outputs-and-resource', len(actual) == len(planned) and set(differ)-allowed == {217}, differ)
    checks.expect('plan-resource-operand', planned[217] == str(caller.RESOURCE_ROOT))
    checks.expect('plan-source-and-recipe', row['source'] == failed['source'] and row['recipe'] == failed['recipe'])
    for header, digest in caller.RESOURCE_HEADERS.items():
        path = str(caller.RESOURCE_ROOT/header)
        checks.expect('plan-input:'+header, plan['inputs'].get(path) == digest)
    roots = plan['namespace']['roots']; files = plan['namespace']['files']
    checks.expect('namespace-has-resource-root', str(caller.RESOURCE_ROOT) in roots)
    for header in caller.RESOURCE_HEADERS:
        matches = [p for p in files if Path(p).name == header]
        checks.expect('single-namespace-match:'+header, matches == [str(caller.RESOURCE_ROOT/header)], matches)
    checks.expect('old-root-not-input-but-kept-absent', not any(caller.RESOURCE_ABSENT in p for p in plan['inputs']) and caller.RESOURCE_ABSENT in plan['absent_inputs'])
    stdint = [p for p in files if p.endswith('/stdint.h')]
    checks.expect('resource-root-has-no-stdint', not any(p.startswith(str(caller.RESOURCE_ROOT)) for p in stdint) and any(p.endswith('EXTERNAL_HEADERS/stdint.h') for p in stdint), stdint)


def check_execution_guards(checks, plan_path, caller):
    """Drive the real verify/namespace path that runs before and after every compile."""
    common = caller.module(*caller.PINS[0], 'resource_check_common')
    plan = json.loads(Path(plan_path).read_text())
    caller.verify(common, plan)
    checks.expect('verify-accepts-real-plan', True)
    headers = {str(caller.RESOURCE_ROOT/name): digest for name, digest in caller.RESOURCE_HEADERS.items()}
    changed = json.loads(json.dumps(plan)); changed['inputs'][str(caller.RESOURCE_ROOT/'arm_neon.h')] = '0'*64
    checks.rejects('verify-rejects-changed-header-pin', 'namespace', caller.verify, common, changed)
    missing = json.loads(json.dumps(plan)); del missing['inputs'][str(caller.RESOURCE_ROOT/'arm_bf16.h')]
    checks.rejects('verify-rejects-unindexed-header', 'namespace', caller.verify, common, missing)
    with tempfile.TemporaryDirectory(dir=str(MAIN/'artifacts')) as scratch:
        base = Path(scratch).resolve()
        appeared = json.loads(json.dumps(plan)); appeared['absent_inputs'] = [str(base)]
        checks.rejects('verify-rejects-materialized-absent-root', 'Unqualified input appeared', caller.verify, common, appeared)
        root = base/'resource'; root.mkdir()
        for header in caller.RESOURCE_HEADERS:
            shutil.copyfile(caller.RESOURCE_ROOT/header, root/header)
        index = {str(root/name): digest for name, digest in caller.RESOURCE_HEADERS.items()}
        cwd = base/'cwd'; cwd.mkdir(); source = base/'source'; source.mkdir(); (source/'a.c').write_text('')
        index[str(source/'a.c')] = sha(source/'a.c')
        rows = [dict(cwd=str(cwd), bound_source=str(source/'a.c'), next_owned_compile_argv_template=['clang', '-idirafter', str(root)])]
        checks.expect('namespace-accepts-exact-root', sorted(common.namespace(rows, index, common.Digests())['files']) == sorted(index))
        (root/'stdint.h').write_text('/* shadow */\n')
        checks.rejects('namespace-rejects-shadow-header', 'newly shadowing', common.namespace, rows, index, common.Digests())
        (root/'stdint.h').unlink(); (root/'arm_acle.h').unlink()
        checks.rejects('namespace-rejects-missing-header', 'Missing qualified', common.namespace, rows, index, common.Digests())
    checks.expect('resource-headers-in-admitted-plan', all(plan['inputs'].get(p) == d for p, d in headers.items()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, help='source-only plan JSON produced by native_compile.py plan')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    caller = load_caller()
    checks = Checks()
    delta = check_delta(checks)
    check_rebind(checks, caller)
    check_resources(checks, caller)
    check_authority(checks, caller)
    check_graph(checks, caller)
    if args.plan:
        check_plan(checks, args.plan, caller)
        check_execution_guards(checks, args.plan, caller)
    report = dict(kind='source-review', origin='local-host', outcome='pass', target_tools_executed=False,
                  caller_sha256=sha(HERE/'native_compile.py'), accepted_caller_sha256=ACCEPTED_SHA,
                  delta=delta, checks=checks.rows, check_count=len(checks.rows))
    args.out.write_text(json.dumps(report, indent=2)+'\n')
    print(f'pass {len(checks.rows)} checks')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
