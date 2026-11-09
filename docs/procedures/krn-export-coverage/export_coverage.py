#!/usr/bin/env python3
"""Measure export-list coverage of a linked kernel (KRN-040).

Re-implements the membership rule of XNU's SETUP/kextsymboltool.c for the two
passes of the check_all_exports recipe in config/Makefile. This is NOT the genuine
tool and NOT a genuine check_all_exports result: it only reports which names the
export files request that `nm -gj` does not list for this kernel.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
XNU = MAIN/'artifacts/xnu-prepare/e1s-dependency-source-session1/xnu'
NM = MAIN/'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-nm'
KERNEL = MAIN/'worktrees/str-041-e1s-native-link-image-20261110/artifacts/e1s-native-link/link-001/kernel/kernel.unstripped'
KRN026_INPUTS = MAIN/'worktrees/krn-026-20261105/fixtures/public/kernel-export-gaps/inputs.json'
COMPONENTS = ['BSDKernel', 'IOKit', 'Libkern', 'Mach', 'MACFramework', 'Unsupported', 'Private']
PASSES = {'without-private': 'Private', 'without-unsupported': 'Unsupported'}


def symchar(c):
    return ' ' < c <= '~' and c not in ':#'


def parse_line(line):
    """Return (name, indirect) as kextsymboltool would store them, or None for no symbol."""
    if line.startswith('#'):
        return None
    i = 0
    while i < len(line) and not symchar(line[i]):
        i += 1
    if i == len(line) or line[i] == '.':
        return None
    start = i
    while i < len(line) and symchar(line[i]):
        i += 1
    name = line[start:i]
    while i < len(line) and line[i] in ' \t':
        i += 1
    indirect = None
    if i < len(line) and line[i] == ':':
        i += 1
        while i < len(line) and line[i] in ' \t':
            i += 1
        start = i
        while i < len(line) and symchar(line[i]):
            i += 1
        if i > start:
            indirect = line[start:i]
        elif i == len(line):
            raise ValueError(f'Bad symbol line: {line}')
    elif i < len(line) and line[i] != '-':
        raise ValueError(f'Bad symbol line: {line}')
    return name, indirect


def parse(text):
    return [item for item in map(parse_line, text.splitlines()) if item]


def present(entry, imports, sorted_imports):
    target = entry[1] or entry[0]
    if len(target) > 1 and target.endswith('*'):
        prefix = target[:-1]
        low, high = 0, len(sorted_imports)
        while low < high:
            mid = (low + high) // 2
            if sorted_imports[mid] < prefix:
                low = mid + 1
            else:
                high = mid
        return low < len(sorted_imports) and sorted_imports[low].startswith(prefix)
    return target in imports


def self_test():
    assert parse_line('# comment') is None
    assert parse_line('') is None
    assert parse_line('   ') is None
    assert parse_line('.hidden') is None
    assert parse_line('_a') == ('_a', None)
    assert parse_line('  _a') == ('_a', None)
    assert parse_line('_a:_b') == ('_a', '_b')
    assert parse_line('_a : _b') == ('_a', '_b')
    assert parse_line('_a -obsolete') == ('_a', None)
    assert parse_line('_a:_b -obsolete') == ('_a', '_b')
    imports = {'_abc', '_abd', '_x'}
    order = sorted(imports)
    assert present(('_abc', None), imports, order)
    assert not present(('_ab', None), imports, order)
    assert present(('_ab*', None), imports, order)
    assert not present(('_q*', None), imports, order)
    assert present(('_alias', '_x'), imports, order)
    assert not present(('_x', '_absent'), imports, order)
    for bad in ['_a b', '_a:', '_a # note']:
        try:
            parse_line(bad)
        except ValueError:
            continue
        raise AssertionError(bad)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    self_test()
    out = MAIN/'artifacts/krn-export-coverage'/args.run
    out.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(dir=out) as temp:
        done = subprocess.run([str(NM), '-gj', str(KERNEL)], capture_output=True, text=True, timeout=120, cwd=temp)
    if done.returncode:
        raise RuntimeError(done.stderr[-500:])
    imports = {entry[0] for entry in parse('\n'.join(sorted(set(done.stdout.split('\n')))))}
    order = sorted(imports)
    report = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), genuine_check_all_exports=False, kernel_sha256=sha(KERNEL), nm_sha256=sha(NM), imported_symbols=len(imports), passes={})
    union = {}
    for name, excluded in PASSES.items():
        missing, total = {}, 0
        for component in COMPONENTS:
            if component == excluded:
                continue
            for path in [XNU/f'config/{component}.exports', XNU/f'config/{component}.arm64.exports']:
                entries = parse(path.read_text())
                total += len(entries)
                absent = sorted({e[0] for e in entries if not present(e, imports, order)})
                if absent:
                    missing[path.name] = absent
                for symbol in absent:
                    union.setdefault(symbol, set()).add(path.name)
        report['passes'][name] = dict(export_entries=total, missing_names=sum(len(v) for v in missing.values()), missing=missing)
    report['all_missing'] = {k: sorted(v) for k, v in sorted(union.items())}
    report['all_missing_count'] = len(union)
    def strings(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from strings(item)
    known = {n for n in strings(json.loads(KRN026_INPUTS.read_text())) if re.fullmatch(r'_[A-Za-z0-9_]+', n)}
    report['krn026_inputs_sha256'] = sha(KRN026_INPUTS)
    report['krn026_names'] = len(known)
    report['missing_and_in_krn026'] = sorted(set(union) & known)
    report['missing_not_in_krn026'] = sorted(set(union) - known)
    report['krn026_not_missing_here'] = sorted(known - set(union))
    path = out/'report.json'
    path.write_text(json.dumps(report, indent=1)+'\n')
    print(json.dumps({k: report[k] for k in ['imported_symbols', 'all_missing_count', 'krn026_names']} | {'overlap': len(report['missing_and_in_krn026']), 'only_here': len(report['missing_not_in_krn026']), 'only_krn026': len(report['krn026_not_missing_here']), 'passes': {k: (v['export_entries'], v['missing_names']) for k, v in report['passes'].items()}, 'sha': sha(path)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
