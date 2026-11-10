#!/usr/bin/env python3
"""Host test and APK build of the s24vmm viewer. No Gradle, downloads, ADB or phone access.

1. Cross-implementation protocol test: test/wire.c (the VMM's own scfb.c encoder and decoder, under
   ASan+UBSan) writes S24F frames that test/ProtocolTest.java decodes on the host JVM with the app's
   Protocol class; Java writes S24T touches that the C decoder reads back.
2. Builds the APK twice from clean directories and requires byte-identical unsigned aligned APKs,
   then signs one with a per-run development key (the signature is not reproducible by design).
Writes artifacts/<task>/<run>/viewer/build-report.json under the main checkout.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import zipfile

APP = Path(__file__).resolve().parent
VMM = APP.parent/'vmm'
ROOT = Path('/home/egor/dev/pet/s24-ios-exynos')
BUILD_TOOLS = '35.0.0'
PLATFORM = 'android-35'
CLANG = '/home/egor/.local/bin/clang'
JAVAC = 'javac 25.0.1'
ZIP_TIME = (1981, 1, 1, 1, 1, 2)
EXPECTED_TOUCHES = [dict(rc=0, slot=0, tracking_id=0, x=10, y=20), dict(rc=0, slot=9, tracking_id=65535, x=1124, y=2435),
                    dict(rc=0, slot=0, tracking_id=-1, x=0, y=0), dict(rc=-1, slot=10, tracking_id=1, x=2, y=3)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--task', default='vm-053')
    parser.add_argument('--sdk', type=Path, default=Path(os.environ.get('ANDROID_HOME', '/home/egor/Android/Sdk')))
    args = parser.parse_args()
    for value in (args.run, args.task):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value):
            raise ValueError('Invalid run or task name')
    out = ROOT/'artifacts'/args.task/args.run/'viewer'
    out.mkdir(parents=True, exist_ok=False)
    sdk = args.sdk.resolve()
    tools, jar = sdk/'build-tools'/BUILD_TOOLS, sdk/'platforms'/PLATFORM/'android.jar'
    java_sources = sorted((APP/'java').rglob('*.java'))
    inputs = [APP/'build.py', APP/'AndroidManifest.xml', *java_sources, APP/'test/wire.c', APP/'test/ProtocolTest.java', VMM/'scfb.c', VMM/'scfb.h']
    report = dict(schema_version=1, kind='host-test', origin='local-host', outcome='fail', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=APP, text=True).strip(),
                  dirty=bool(subprocess.check_output(['git', 'status', '--porcelain', '--', str(APP), str(VMM)], cwd=APP, text=True).strip()),
                  sources={str(f.relative_to(APP.parent)): sha(f) for f in inputs}, installed=False, device_io=False, commands=[],
                  toolchain=dict(build_tools=BUILD_TOOLS, platform=PLATFORM, clang=CLANG))

    def run(argv, cwd=out, timeout=180):
        argv = [str(a) for a in argv]
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        report['commands'].append(dict(argv=argv, exit_code=done.returncode, stdout=done.stdout[-3000:], stderr=done.stderr[-3000:]))
        if done.returncode:
            raise RuntimeError(f'{Path(argv[0]).name} exited {done.returncode}: {done.stderr[-800:]}')
        return done.stdout

    try:
        for f in [tools/'aapt2', tools/'d8', tools/'zipalign', tools/'apksigner', jar, Path(CLANG)]:
            if not f.is_file():
                raise RuntimeError(f'Missing pinned prerequisite: {f}')
        report['toolchain']['javac'] = run(['javac', '-version']).strip()
        if report['toolchain']['javac'] != JAVAC:
            raise RuntimeError(f'Pinned to {JAVAC}')

        # 1. protocol test across the C and Java implementations
        host = out/'host-test'
        (host/'classes').mkdir(parents=True)
        run([CLANG, '-std=c11', '-Wall', '-Wextra', '-Werror', '-Wpedantic', '-g', '-O1', '-fsanitize=address,undefined', '-fno-sanitize-recover=all',
             '-I', VMM, APP/'test/wire.c', VMM/'scfb.c', '-o', host/'wire'])
        run([host/'wire', 'frames', host/'frames.bin'])
        run(['javac', '--release', '8', '-Xlint:all,-options', '-Werror', '-d', host/'classes', APP/'java/dev/egor/s24vmmviewer/Protocol.java', APP/'test/ProtocolTest.java'])
        report['java_test'] = json.loads(run(['java', '-cp', host/'classes', 'ProtocolTest', host/'frames.bin', host/'touches.bin']))
        decoded = [json.loads(line) for line in run([host/'wire', 'touches', host/'touches.bin']).splitlines()]
        report['c_decoded_touches'] = decoded
        protocol_ok = (report['java_test']['failures'] == 0 and report['java_test']['checks'] > 0 and decoded == EXPECTED_TOUCHES)

        # 2. two clean builds
        builds = []
        for name in ('build-1', 'build-2'):
            b = out/name
            (b/'classes').mkdir(parents=True)
            (b/'dex').mkdir()
            run(['javac', '--release', '8', '-Xlint:all,-options', '-Werror', '-classpath', jar, '-d', b/'classes', *java_sources])
            run([tools/'d8', '--release', '--lib', jar, '--min-api', '29', '--output', b/'dex', *sorted((b/'classes').rglob('*.class'))])
            run([tools/'aapt2', 'link', '-o', b/'unsigned.apk', '--manifest', APP/'AndroidManifest.xml', '-I', jar])
            with zipfile.ZipFile(b/'unsigned.apk', 'a') as apk:
                entry = zipfile.ZipInfo('classes.dex', date_time=ZIP_TIME)
                entry.compress_type = zipfile.ZIP_DEFLATED
                apk.writestr(entry, (b/'dex/classes.dex').read_bytes())
            run([tools/'zipalign', '-f', '4', b/'unsigned.apk', b/'aligned.apk'])
            run([tools/'zipalign', '-c', '4', b/'aligned.apk'])
            builds.append(dict(dex_sha256=sha(b/'dex/classes.dex'), aligned_sha256=sha(b/'aligned.apk'), aligned_size=(b/'aligned.apk').stat().st_size))
        report['builds'] = builds
        reproducible = builds[0] == builds[1]

        key = out/'development.jks'
        run(['keytool', '-genkeypair', '-keystore', key, '-storepass', 'android', '-keypass', 'android', '-alias', 'development',
             '-dname', 'CN=S24 Research Development', '-keyalg', 'RSA', '-keysize', '2048', '-validity', '365'])
        key.chmod(0o600)
        apk = out/'s24vmm-viewer.apk'
        run([tools/'apksigner', 'sign', '--ks', key, '--ks-key-alias', 'development', '--ks-pass', 'pass:android', '--key-pass', 'pass:android',
             '--out', apk, out/'build-1/aligned.apk'])
        verify = run([tools/'apksigner', 'verify', '--verbose', apk])
        badging = run([tools/'aapt2', 'dump', 'badging', apk])
        report['apk'] = dict(path=str(apk.relative_to(ROOT)), size=apk.stat().st_size, sha256=sha(apk),
                             unsigned_aligned_sha256=builds[0]['aligned_sha256'], verified='Verifies' in verify,
                             package=re.search(r"package: name='([^']+)'", badging).group(1),
                             permissions=sorted(re.findall(r"uses-permission: name='([^']+)'", badging)))
        report['checks'] = dict(protocol=protocol_ok, reproducible=reproducible, signed=report['apk']['verified'],
                                only_internet_permission=report['apk']['permissions'] == ['android.permission.INTERNET'])
        report['outcome'] = 'pass' if all(report['checks'].values()) else 'fail'
    except Exception as error:  # keep what happened
        report['error'] = f'{type(error).__name__}: {error}'
    (out/'build-report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report.get(k) for k in ('outcome', 'checks', 'java_test', 'builds', 'apk', 'error')}, indent=1))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    sys.exit(main())
