#!/usr/bin/env python3
"""Run owned host transport tests and compile-only ARM objects, no radio/SDK."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--cc', default='cc')
    p.add_argument('--host-clang', type=Path, default=Path('/home/egor/.local/bin/clang'))
    p.add_argument('--clang', type=Path, default=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'))
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT / 'artifacts/bluetooth-transport' / args.run
    if out.resolve() != out:
        raise ValueError('Run path must not use symlinks')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  commands=[], sha256={}, device_io=False, native_driver_built=False,
                  aarch64_executed=False, apple_sdk_used=False)
    try:
        snapshot = out / 'source'; snapshot.mkdir()
        for name in ('transport.h', 'transport.c', 'fixture.c', 'layout.cpp', 'profile.json', 'check.py'):
            source = SOURCE / name
            shutil.copyfile(source, snapshot / name)
            report['sha256'][str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()

        def run(argv, env=None):
            argv = [str(a) for a in argv]
            try:
                r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=45, env=env)
            except subprocess.TimeoutExpired as error:
                report['commands'].append(dict(argv=argv, exit_code=None, timeout=True))
                raise RuntimeError('Process deadline exceeded') from error
            report['commands'].append(dict(argv=argv, exit_code=r.returncode, stdout=r.stdout, stderr=r.stderr))
            if r.returncode:
                raise RuntimeError(r.stderr or r.stdout)
            return r.stdout

        flags = ['-Wall', '-Wextra', '-Werror', '-Wpedantic']
        for compiler in (args.cc, args.host_clang, args.clang): run([compiler, '--version'])
        run([args.cc, '-std=c11', *flags, '-c', snapshot / 'transport.c', '-o', out / 'host-core.o'])
        run([args.cc, '-std=c++17', *flags, '-c', snapshot / 'layout.cpp', '-o', out / 'host-layout.o'])
        run([args.host_clang, '-std=c11', *flags, '-O1', '-g', '-fno-omit-frame-pointer', '-fsanitize=address,undefined',
             snapshot / 'transport.c', snapshot / 'fixture.c', '-o', out / 'fixture'])
        env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
        result = json.loads(run([out / 'fixture'], env=env))
        if result.get('outcome') != 'pass' or result.get('mutation_control_attempts') != 20000 or result.get('device_io') is not False:
            raise ValueError('Fixture result mismatch')
        report['result'] = result
        report['object_headers'] = {}
        for target, label in [('aarch64-none-elf', 'aarch64-elf'), ('arm64-apple-ios16.5', 'arm64-ios-macho')]:
            for name, standard in [('transport.c', '-std=c11'), ('layout.cpp', '-std=c++17')]:
                obj = out / (label + '-' + name + '.o')
                run([args.clang, '--target=' + target, '-ffreestanding', standard, *flags, '-c', snapshot / name, '-o', obj])
                detail = run([args.clang.parent / 'llvm-readobj', '--file-headers', obj])
                expected = 'elf64-littleaarch64' if label == 'aarch64-elf' else 'Mach-O arm64'
                if expected not in detail: raise ValueError('Unexpected object format')
                report['object_headers'][obj.name] = detail
        for product in out.iterdir():
            if product.is_file(): report['sha256'][str(product.relative_to(ROOT))] = hashlib.sha256(product.read_bytes()).hexdigest()
        report.update(outcome='pass', summary='Owned H4/initialization-command model passes sanitizer mutation/control fixtures and four ARM object checks; no UART, firmware or daemon execution')
    except Exception as error:
        report.update(outcome='fail', error=str(error))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('outcome', 'summary', 'error', 'result')}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
