#!/usr/bin/env python3
"""Build the pinned RADV-for-Xclipse Vulkan driver for Android arm64 (GPU-005).

Host build only: no ADB, no install. It reproduces the configure options of the
pinned upstream build.sh, with this project's installed NDK and a project-local
Python venv holding Mesa's generator modules. Meson downloads the three wrap
sources (libdrm, zlib, expat) and checks each against the source_hash in the
pinned wrap file. Every command, exit code, tool version and the output hash
goes to artifacts/gpu-005/<run>/report.json; failures are kept, not masked.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
PIN = 'fe9b8943aaeec11ed9fccbfcc382da07379afbe5'
URL = 'https://github.com/JimVulkan/radv-xclipse'
NDK = '28.2.13676358'
API = 34
# The exact option list of upstream build.sh at PIN.
MESON_OPTIONS = [
    '-Dbuildtype=debugoptimized', '-Db_ndebug=true',
    '-Dplatforms=android', f'-Dplatform-sdk-version={API}', '-Dandroid-stub=true', '-Dandroid-strict=false',
    '-Dandroid-libbacktrace=disabled',
    '-Dvulkan-drivers=amd', '-Dgallium-drivers=', '-Dvulkan-layers=', '-Dtools=',
    '-Dllvm=disabled', '-Dzstd=disabled', '-Dlmsensors=disabled', '-Dperfetto=false',
    '-Dglx=disabled', '-Dgbm=disabled', '-Degl=disabled', '-Dgles1=disabled', '-Dgles2=disabled',
    '-Dallow-fallback-for=libdrm,perfetto', '--force-fallback-for=expat,libdrm,zlib',
    '-Dlibdrm:default_library=static', '-Dexpat:default_library=static', '-Dzlib:default_library=static',
    '-Dc_args=-march=armv8.2-a', '-Dcpp_args=-march=armv8.2-a',
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--source', type=Path, default=ROOT / 'artifacts/gpu-005/radv-xclipse')
    p.add_argument('--venv', type=Path, default=ROOT / 'artifacts/gpu-005/venv')
    p.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME', '/home/egor/Android/Sdk')))
    p.add_argument('--timeout', type=int, default=3600)
    args = p.parse_args()
    if not args.run.replace('-', '').isalnum() or len(args.run) > 80:
        raise SystemExit('Use a unique simple run name')
    out = ROOT / 'artifacts/gpu-005' / args.run
    out.mkdir(parents=True, exist_ok=False)
    build = out / 'build'
    bin_ = args.sdk / 'ndk' / NDK / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='fail', task='GPU-005',
                  recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  project_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  source=dict(url=URL, pin=PIN, path=str(args.source)), ndk=NDK, api=API,
                  meson_options=MESON_OPTIONS, commands=[], tools={})
    env = dict(os.environ, PATH=f"{args.venv / 'bin'}:{os.environ['PATH']}")

    def run(argv, cwd, timeout=600, keep=8000):
        argv = [str(a) for a in argv]
        try:
            x = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
            rc, so, se = x.returncode, x.stdout, x.stderr
        except subprocess.TimeoutExpired as e:
            rc, so, se = 'timeout', str(e.stdout or ''), str(e.stderr or '')
        report['commands'].append(dict(argv=argv, cwd=str(cwd), exit_code=rc, stdout_tail=so[-keep:], stderr_tail=se[-keep:]))
        if rc != 0:
            raise RuntimeError(f'{argv[0]} exited {rc}')
        return so

    try:
        head = run(['git', 'rev-parse', 'HEAD'], args.source).strip()
        if head != PIN:
            raise RuntimeError(f'source HEAD {head} is not the pin {PIN}')
        if run(['git', 'status', '--porcelain', '--untracked-files=no'], args.source).strip():
            raise RuntimeError('source checkout has local changes')
        for name in ['aarch64-linux-android34-clang', 'aarch64-linux-android34-clang++', 'llvm-ar', 'llvm-strip']:
            if not (bin_ / name).exists():
                raise RuntimeError(f'missing NDK tool {bin_ / name}')
        report['tools'] = {
            'meson': run(['meson', '--version'], out).strip(),
            'ninja': run(['ninja', '--version'], out).strip(),
            'glslangValidator': run(['glslangValidator', '--version'], out).splitlines()[0],
            'python_modules': run([args.venv / 'bin/python', '-m', 'pip', 'freeze'], out).split(),
            'clang': run([bin_ / 'aarch64-linux-android34-clang', '--version'], out).splitlines()[0],
        }
        build.mkdir()
        cross = build / 'cross.ini'
        cross.write_text(
            "[binaries]\n"
            f"c = '{bin_}/aarch64-linux-android{API}-clang'\n"
            f"cpp = '{bin_}/aarch64-linux-android{API}-clang++'\n"
            f"ar = '{bin_}/llvm-ar'\n"
            f"strip = '{bin_}/llvm-strip'\n\n"
            "[properties]\ncpp_link_args = ['-static-libstdc++']\n\n"
            "[host_machine]\nsystem = 'android'\ncpu_family = 'aarch64'\ncpu = 'aarch64'\nendian = 'little'\n")
        run(['meson', 'setup', build, '--cross-file', cross, *MESON_OPTIONS], args.source, timeout=900)
        run(['ninja', '-C', build, 'src/amd/vulkan/libvulkan_radeon.so'], args.source, timeout=args.timeout, keep=4000)
        lib = build / 'src/amd/vulkan/libvulkan_radeon.so'
        stripped = out / 'libvulkan_radeon.so'
        run([bin_ / 'llvm-strip', '-o', stripped, lib], out)
        readelf = run([bin_ / 'llvm-readelf', '-h', '-d', '--dyn-syms', stripped], out, keep=0)
        exports = sorted({line.split()[-1] for line in readelf.splitlines()
                          if ' FUNC ' in line and ' GLOBAL ' in line and ' UND ' not in line})
        needed = sorted({line.split('[')[1].rstrip(']') for line in readelf.splitlines() if '(NEEDED)' in line})
        report['product'] = dict(path=str(stripped.relative_to(ROOT)), bytes=stripped.stat().st_size, sha256=sha256(stripped),
                                 unstripped_sha256=sha256(lib), machine=next((l.split(':', 1)[1].strip() for l in readelf.splitlines() if 'Machine:' in l), None),
                                 needed=needed, exported_functions=exports)
        report['outcome'] = 'pass'
    except Exception as e:  # keep the failure in the report
        report['error'] = str(e)
    (out / 'report.json').write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps({k: report.get(k) for k in ('outcome', 'error')} | {'product': report.get('product', {}).get('sha256')}))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
