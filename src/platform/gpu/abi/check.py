#!/usr/bin/env python3
"""Build transport checks on the host and compile-only AArch64 objects. No SDK/device."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[4]
SOURCE = Path(__file__).resolve().parent
DEFAULT_CLANG = Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--clang', type=Path, default=DEFAULT_CLANG)
    p.add_argument('--host-clang', type=Path, default=Path('/home/egor/.local/bin/clang'))
    p.add_argument('--cc', default='cc')
    args = p.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT / 'artifacts/gpu-abi' / args.run
    if out.resolve() != out:
        raise ValueError('Run path must not use symlinks')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  commands=[], device_io=False, native_driver_built=False, apple_sdk_used=False,
                  aarch64_executed=False, sha256={})
    flags = ['-Wall', '-Wextra', '-Werror', '-Wpedantic']
    sources = [SOURCE / n for n in ('sgpu_abi.h', 'sgpu_abi.c', 'sgpu_fake.h', 'sgpu_fake.c', 'layout.c', 'sanity.c', 'check.py')]
    try:
        # Build from a dated isolated copy; never modify reviewed upstream or phone.
        snapshot = out / 'source'
        snapshot.mkdir()
        for source in sources:
            shutil.copyfile(source, snapshot / source.name)
            report['sha256'][str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()

        def run(argv, timeout=45, env=None):
            argv = [str(a) for a in argv]
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=timeout, env=env)
            report['commands'].append(dict(argv=argv, exit_code=result.returncode, stdout=result.stdout, stderr=result.stderr))
            if result.returncode:
                raise RuntimeError(result.stderr or result.stdout or 'Command failed')
            return result.stdout

        run([args.cc, '--version'])
        run([args.clang, '--version'])
        run([args.host_clang, '--version'])
        run([args.cc, '-std=c11', *flags, '-fPIC', '-shared', snapshot / 'sgpu_abi.c', snapshot / 'sgpu_fake.c', '-o', out / 'sgpu-fake.so'])
        run([args.cc, '-std=c++17', '-x', 'c++', *flags, '-c', snapshot / 'layout.c', '-o', out / 'layout-host-cxx.o'])
        run([args.host_clang, '-std=c11', *flags, '-O1', '-g', '-fno-omit-frame-pointer', '-fsanitize=address,undefined',
             snapshot / 'sgpu_abi.c', snapshot / 'sgpu_fake.c', snapshot / 'sanity.c', '-o', out / 'sanity'])
        env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
        result = json.loads(run([out / 'sanity'], timeout=30, env=env))
        if result.get('outcome') != 'pass' or result.get('mutation_attempts') != 50000 or result.get('device_io') is not False:
            raise ValueError('Sanitizer harness result mismatch')
        report['result'] = result
        formats = {}
        report['object_formats'] = formats
        for target, label in [('aarch64-none-elf', 'aarch64-elf'), ('arm64-apple-ios16.5', 'arm64-ios-macho')]:
            for name in ('sgpu_abi.c', 'sgpu_fake.c', 'layout.c'):
                obj = out / (label + '-' + name + '.o')
                run([args.clang, '--target=' + target, '-ffreestanding', '-std=c11', *flags, '-c', snapshot / name, '-o', obj])
                formats[obj.name] = run([args.clang.parent / 'llvm-readobj', '--file-headers', obj])
            cpp_obj = out / (label + '-layout-cxx.o')
            run([args.clang, '--target=' + target, '-ffreestanding', '-std=c++17', '-x', 'c++', *flags,
                 '-c', snapshot / 'layout.c', '-o', cpp_obj])
            formats[cpp_obj.name] = run([args.clang.parent / 'llvm-readobj', '--file-headers', cpp_obj])
        for name, detail in formats.items():
            expected = 'elf64-littleaarch64' if name.startswith('aarch64-elf') else 'Mach-O arm64'
            if expected not in detail:
                raise ValueError('Unexpected object format: ' + name)
        report.update(outcome='pass', summary='Host transport validation/sanitizers pass; wire layouts and C core compile for AArch64 ELF and iOS16.5 arm64 Mach-O without SDK', result=result, object_formats=formats)
        for product in out.iterdir():
            if product.is_file():
                report['sha256'][str(product.relative_to(ROOT))] = hashlib.sha256(product.read_bytes()).hexdigest()
    except Exception as error:
        report.update(outcome='fail', error=str(error))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('outcome', 'summary', 'error', 'result')}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
