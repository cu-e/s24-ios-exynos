#!/usr/bin/env python3
"""Build/sign the probe with installed pinned Android tools. No Gradle, downloads or ADB."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

APP = Path(__file__).resolve().parent
ROOT = APP.parents[1]
NDK = '28.2.13676358'
BUILD_TOOLS = '35.0.0'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run', required=True)
    p.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME', '/home/egor/Android/Sdk')))
    args = p.parse_args()
    if not args.run.replace('-', '').replace('_', '').isalnum() or len(args.run) > 80:
        raise ValueError('Use a unique simple run name')
    out = ROOT / 'artifacts/android-probe' / args.run
    if out.resolve() != out:
        raise ValueError('Run directory cannot use symlinks')
    out.mkdir(parents=True, exist_ok=False)
    sdk = args.sdk.resolve(); tools = sdk / 'build-tools' / BUILD_TOOLS
    llvm = sdk / 'ndk' / NDK / 'toolchains/llvm/prebuilt/linux-x86_64/bin'
    jar = sdk / 'platforms/android-35/android.jar'
    inputs = [APP/'build.py', APP/'AndroidManifest.xml', *sorted((APP/'java').rglob('*.java')), *[APP/'native'/n for n in ['probe.cpp','probe.h','jni.cpp']]]
    source_files = {str(f.relative_to(APP)): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(inputs)}
    source_hash = hashlib.sha256(''.join(name + ':' + digest + '\n' for name,digest in source_files.items()).encode()).hexdigest()
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='inconclusive', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), source_commit=commit, source_sha256=source_hash, source_files=source_files, installed=False, commands=[], toolchain={'ndk': NDK, 'build_tools': BUILD_TOOLS, 'platform': 'android-35'})
    def run(argv):
        x = subprocess.run([str(a) for a in argv], cwd=out, capture_output=True, text=True, timeout=120)
        report['commands'].append(dict(argv=[str(a) for a in argv], exit_code=x.returncode, stdout=x.stdout, stderr=x.stderr))
        if x.returncode: raise RuntimeError(x.stderr[-4000:])
        return x.stdout
    try:
        for f in [tools / 'aapt2', tools / 'd8', tools / 'zipalign', tools / 'apksigner', llvm / 'aarch64-linux-android29-clang++', jar]:
            if not f.is_file(): raise RuntimeError('Missing pinned prerequisite: ' + str(f))
        (out / 'classes').mkdir(); (out / 'dex').mkdir()
        generated = out / 'generated/dev/egor/s24probe/BuildInfo.java'; generated.parent.mkdir(parents=True)
        generated.write_text('package dev.egor.s24probe; final class BuildInfo { static final String COMMIT="' + commit + '"; static final String SOURCE_SHA256="' + source_hash + '"; }\n')
        report['toolchain']['javac'] = run(['javac', '-version']).strip()
        if not report['toolchain']['javac'].startswith('javac 25.0.1'):
            raise RuntimeError('This build is pinned to javac 25.0.1; update lock deliberately for another JDK')
        run(['javac', '--release', '8', '-classpath', jar, '-d', out / 'classes', *sorted((APP / 'java').rglob('*.java')), generated])
        run([tools / 'd8', '--lib', jar, '--min-api', '29', '--output', out / 'dex', *sorted((out / 'classes').rglob('*.class'))])
        run([tools / 'aapt2', 'link', '-o', out / 'unsigned.apk', '--manifest', APP / 'AndroidManifest.xml', '-I', jar])
        for abi, compiler in [('arm64-v8a', 'aarch64-linux-android29-clang++'), ('x86_64', 'x86_64-linux-android29-clang++')]:
            lib = out / 'lib' / abi / 'libs24probe.so'; lib.parent.mkdir(parents=True)
            run([llvm / compiler, '-std=c++17', '-O2', '-fPIC', '-shared', '-static-libstdc++', '-Wall', '-Wextra', '-Wno-missing-field-initializers', '-Wl,-z,max-page-size=16384', APP / 'native/probe.cpp', APP / 'native/jni.cpp', '-lvulkan', '-o', lib])
        with zipfile.ZipFile(out / 'unsigned.apk', 'a', compression=zipfile.ZIP_STORED) as apk:
            for f in [out / 'dex/classes.dex', *sorted((out / 'lib').rglob('*.so'))]:
                apk.write(f, 'classes.dex' if f.suffix == '.dex' else str(f.relative_to(out)))
        run([tools / 'zipalign', '-P', '16', '-f', '4', out / 'unsigned.apk', out / 'aligned.apk'])
        key = out / 'development.jks'
        run(['keytool', '-genkeypair', '-keystore', key, '-storepass', 'android', '-keypass', 'android', '-alias', 'development', '-dname', 'CN=S24 Research Development', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '365'])
        key.chmod(0o600)
        apk = out / 's24-vulkan-probe.apk'
        run([tools / 'apksigner', 'sign', '--ks', key, '--ks-key-alias', 'development', '--ks-pass', 'pass:android', '--key-pass', 'pass:android', '--out', apk, out / 'aligned.apk'])
        run([tools / 'apksigner', 'verify', '--verbose', apk])
        report['apk'] = dict(path=str(apk.relative_to(ROOT)), size=apk.stat().st_size, sha256=hashlib.sha256(apk.read_bytes()).hexdigest())
        report.update(outcome='pass', summary='ARM64/x86_64 APK compiled, aligned and development-signed; not installed')
    except Exception as error:
        report.update(outcome='fail', error=str(error))
    (out / 'build-report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ['outcome', 'apk', 'error'] if k in report}, indent=2))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    try: sys.exit(main())
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr); sys.exit(2)
