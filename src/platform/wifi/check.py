#!/usr/bin/env python3
"""Compile owned Wi-Fi boundary against pinned external ABI; never starts a radio."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools'))
import sources


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--host-clang', type=Path, default=Path('/home/egor/.local/bin/clang'))
    parser.add_argument('--clang', type=Path, default=Path('/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/clang'))
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT / 'artifacts/wifi-platform' / args.run
    if out.resolve() != out:
        raise ValueError('Run path cannot use symlinks')
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  commands=[], sha256={}, device_io=False, donor_runtime_linked=False,
                  native_backend_built=False, aarch64_executed=False, apple_sdk_used=False)
    try:
        registry = json.loads((ROOT / 'research/sources.json').read_text())['sources']
        profile = json.loads((SOURCE / 'profile.json').read_text())
        verified = []
        for key in ('donor', 'stale_catalog_donor'):
            selected = profile[key]
            entry = next(s for s in registry if s['id'] == selected['id'])
            if entry['revision'] != selected['revision']:
                raise ValueError('Registry/profile revision mismatch')
            checked = sources.verify(ROOT, entry)
            if checked['review_file_sha256'].get('include/nw_abi.h') != selected['header_sha256']:
                raise ValueError('Donor ABI digest mismatch')
            verified.append(checked)
        report['verified_sources'] = verified
        current = ROOT / 'references' / profile['donor']['id'] / 'include'
        old = ROOT / 'references' / profile['stale_catalog_donor']['id'] / 'include'
        snapshot = out / 'source'
        snapshot.mkdir()
        for name in ('e1s_wifi.h', 'e1s_wifi.c', 'fixture.c', 'layout.cpp', 'profile.json', 'check.py'):
            original = SOURCE / name
            shutil.copyfile(original, snapshot / name)
            report['sha256'][str(original.relative_to(ROOT))] = hashlib.sha256(original.read_bytes()).hexdigest()

        def run(argv, expected_failure=False, env=None):
            argv = [str(a) for a in argv]
            try:
                r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=45, env=env)
            except subprocess.TimeoutExpired as error:
                report['commands'].append(dict(argv=argv, exit_code=None, timeout=True))
                raise RuntimeError('Process deadline exceeded') from error
            report['commands'].append(dict(argv=argv, exit_code=r.returncode, expected_failure=expected_failure, stdout=r.stdout, stderr=r.stderr))
            if expected_failure:
                if r.returncode == 0 or not ('static assertion' in r.stderr or 'preempt_enable' in r.stderr):
                    raise RuntimeError('Stale ABI was not rejected for the expected incompatibility')
            elif r.returncode:
                raise RuntimeError(r.stderr or r.stdout)
            return r.stdout

        flags = ['-Wall', '-Wextra', '-Werror', '-Wpedantic']
        run([args.cc, '--version']); run([args.host_clang, '--version']); run([args.clang, '--version'])
        run([args.cc, '-std=c11', *flags, '-I', current, '-c', snapshot / 'e1s_wifi.c', '-o', out / 'boundary-host.o'])
        run([args.cc, '-std=c++17', *flags, '-I', current, '-c', snapshot / 'layout.cpp', '-o', out / 'layout-host.o'])
        run([args.cc, '-std=c11', *flags, '-I', old, '-c', snapshot / 'e1s_wifi.c', '-o', out / 'stale-abi.o'], expected_failure=True)
        run([args.host_clang, '-std=c11', *flags, '-O1', '-g', '-fno-omit-frame-pointer', '-fsanitize=address,undefined', '-I', current,
             snapshot / 'e1s_wifi.c', snapshot / 'fixture.c', '-o', out / 'fixture'])
        env = {**os.environ, 'ASAN_OPTIONS': 'detect_leaks=1:halt_on_error=1', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1'}
        result = json.loads(run([out / 'fixture'], env=env))
        if result != {'outcome': 'pass', 'environment': 'synthetic-wifi-binding', 'range_pairs': 16384, 'callback_calls': 0, 'device_io': False}:
            raise ValueError('Fixture result mismatch')
        report['result'] = result
        report['object_headers'] = {}
        for target, label in [('aarch64-none-elf', 'aarch64-elf'), ('arm64-apple-ios16.5', 'arm64-ios-macho')]:
            for name, standard in [('e1s_wifi.c', '-std=c11'), ('layout.cpp', '-std=c++17')]:
                obj = out / (label + '-' + name + '.o')
                run([args.clang, '--target=' + target, '-ffreestanding', standard, *flags, '-I', current, '-c', snapshot / name, '-o', obj])
                detail = run([args.clang.parent / 'llvm-readobj', '--file-headers', obj])
                expected = 'elf64-littleaarch64' if label == 'aarch64-elf' else 'Mach-O arm64'
                if expected not in detail:
                    raise ValueError('Wrong cross-compiled object format')
                report['object_headers'][obj.name] = detail
        # Reverify no external reviewed header changed while building.
        for checked in verified:
            entry = next(s for s in registry if s['id'] == checked['id'])
            if sources.verify(ROOT, entry) != checked:
                raise ValueError('External source changed during build')
        for product in out.iterdir():
            if product.is_file():
                report['sha256'][str(product.relative_to(ROOT))] = hashlib.sha256(product.read_bytes()).hexdigest()
        report.update(outcome='pass', summary='Owned Wi-Fi admission/DMA boundary passes host sanitizers and four AArch64 C/C++ object checks; stale catalog ABI rejected; no callback or radio execution')
    except Exception as error:
        report.update(outcome='fail', error=str(error))
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report.get(k) for k in ('outcome', 'summary', 'error', 'result')}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
