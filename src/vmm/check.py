#!/usr/bin/env python3
"""Host checks for s24vmm: machine/FDT/device tests and virtio/SCFB tests under ASan+UBSan, the
SCFB seqlock test under TSan, and a warning-free static NDK build. No phone access.
Writes artifacts/<task>/<run>/check.json (task defaults to vm-053)."""
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
FILES = ['fdt.h', 'fdt.c', 'machine.h', 'machine.c', 'virtio.h', 'virtio.c', 'scfb.h', 'scfb.c', 's24vmm.c', 'test_vmm.c', 'test_io.c',
         'check.py', 'avfboot/identity.h']


def run(argv, report, timeout=120):
    done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    report['commands'].append(dict(argv=argv, exit_code=done.returncode, stdout=done.stdout[-2000:], stderr=done.stderr[-2000:]))
    if done.returncode:
        raise RuntimeError(f'{argv[0]} exited {done.returncode}: {done.stderr[-500:]}')
    return done.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--task', default='vm-053')
    args = parser.parse_args()
    for value in (args.run, args.task):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
            raise ValueError('Invalid run or task name')
    out = ROOT/'artifacts'/args.task/args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='fail', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip(), commands=[],
                  sha256={name: hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in FILES}, device_io=False)
    try:
        src = [str(SOURCE/f) for f in ['fdt.c', 'machine.c', 'scfb.c', 'test_vmm.c']]
        run([CLANG, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-g', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
             *src, '-o', str(out/'test_vmm')], report)
        report['tests'] = json.loads(run([str(out/'test_vmm')], report))
        io_src = [str(SOURCE/f) for f in ['virtio.c', 'scfb.c', 'test_io.c']]
        run([CLANG, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-g', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
             *io_src, '-o', str(out/'test_io')], report)
        report['io_tests'] = [json.loads(line) for line in run([str(out/'test_io')], report).splitlines() if line.startswith('{')]
        run([CLANG, '-std=c11', '-Wall', '-Wextra', '-Werror', '-g', '-O1', '-fsanitize=thread', *io_src, '-o', str(out/'test_io_tsan')], report)
        tsan = subprocess.run([str(out/'test_io_tsan')], capture_output=True, text=True, timeout=300, env={'TSAN_OPTIONS': 'halt_on_error=1 exitcode=66'})
        report['commands'].append(dict(argv=[str(out/'test_io_tsan')], exit_code=tsan.returncode, stdout=tsan.stdout[-2000:], stderr=tsan.stderr[-2000:]))
        report['tsan'] = dict(exit_code=tsan.returncode, warnings='ThreadSanitizer' in tsan.stderr)
        run([NDK_CC, '-std=gnu11', '-static', '-O2', '-Wall', '-Wextra', '-Werror',
             *[str(SOURCE/f) for f in ['s24vmm.c', 'machine.c', 'fdt.c', 'virtio.c', 'scfb.c']], '-o', str(out/'s24vmm')], report)
        report['sha256']['s24vmm(binary)'] = hashlib.sha256((out/'s24vmm').read_bytes()).hexdigest()
        io_total = report['io_tests'][-1] if report['io_tests'] else {}
        report['outcome'] = 'pass' if (report['tests'].get('failures') == 0 and report['tests'].get('checks', 0) > 0 and
                                       io_total.get('failures') == 0 and io_total.get('checks', 0) > 0 and
                                       report['tsan'] == dict(exit_code=0, warnings=False)) else 'fail'
    except Exception as error:
        report['error'] = repr(error)
    (out/'check.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(outcome=report['outcome'], tests=report.get('tests'), io_tests=report.get('io_tests'), tsan=report.get('tsan'),
                          error=report.get('error'))))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
