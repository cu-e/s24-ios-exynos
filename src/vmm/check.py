#!/usr/bin/env python3
"""Host checks for s24vmm: machine/FDT/device tests under ASan+UBSan and a warning-free static NDK build.
No phone access. Writes artifacts/vm-052/<run>/check.json."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

SOURCE = Path(__file__).resolve().parent
ROOT = Path('/home/egor/dev/pet/s24-ios-exynos')
CLANG = '/home/egor/.local/bin/clang'
NDK_CC = '/home/egor/Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/aarch64-linux-android35-clang'
FILES = ['fdt.h', 'fdt.c', 'machine.h', 'machine.c', 's24vmm.c', 'test_vmm.c', 'check.py', 'avfboot/identity.h']


def run(argv, report, timeout=120):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    report['commands'].append(dict(argv=argv, exit_code=done.returncode, stdout=done.stdout[-2000:], stderr=done.stderr[-2000:]))
    if done.returncode:
        raise RuntimeError(f'{argv[0]} exited {done.returncode}: {done.stderr[-500:]}')
    return done.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT/'artifacts/vm-052'/args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='fail', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(), commands=[],
                  sha256={name: hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in FILES}, device_io=False)
    try:
        src = [str(SOURCE/f) for f in ['fdt.c', 'machine.c', 'test_vmm.c']]
        run([CLANG, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-g', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
             *src, '-o', str(out/'test_vmm')], report)
        report['tests'] = json.loads(run([str(out/'test_vmm')], report))
        run([NDK_CC, '-std=gnu11', '-static', '-O2', '-Wall', '-Wextra', '-Werror', *[str(SOURCE/f) for f in ['s24vmm.c', 'machine.c', 'fdt.c']],
             '-o', str(out/'s24vmm')], report)
        report['sha256']['s24vmm(binary)'] = hashlib.sha256((out/'s24vmm').read_bytes()).hexdigest()
        report['outcome'] = 'pass' if report['tests'].get('failures') == 0 and report['tests'].get('checks', 0) > 0 else 'fail'
    except Exception as error:
        report['error'] = repr(error)
    (out/'check.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'], tests=report.get('tests'), error=report.get('error'))))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
