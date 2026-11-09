#!/usr/bin/env python3
"""Copy six boot-chain partitions from the owner's S24 to the host, read-only.

Authorized by the owner on 2026-11-10 for exactly this list. Uses su only to read
block devices. Never reads userdata or efs and never writes to the device. The
device serial is not recorded. A copy is not a tested restore.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

PARTITIONS = ['boot', 'init_boot', 'vendor_boot', 'dtbo', 'vbmeta', 'recovery']
MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')


def single_device():
    rows = [l.split() for l in subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=20, check=True).stdout.splitlines()[1:] if l.strip()]
    if len(rows) != 1 or rows[0][1] != 'device':
        raise SystemExit('Need exactly one authorized device')


def su(command, timeout=300):
    done = subprocess.run(['adb', 'exec-out', f"su -c '{command}'"], capture_output=True, timeout=timeout)
    if done.returncode:
        raise RuntimeError(f'{command}: exit {done.returncode}')
    return done.stdout.decode().strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    single_device()
    out = MAIN/'artifacts/device-backup'/args.run
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    report = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), su_used=True, device_written=False,
                  build=su('getprop ro.build.version.incremental'), partitions={})
    for name in PARTITIONS:
        node = f'/dev/block/by-name/{name}'
        size = int(su(f'blockdev --getsize64 {node}'))
        device_sha = su(f'sha256sum {node}').split()[0]
        path = out/f'{name}.img'
        digest = hashlib.sha256()
        count = 0
        with path.open('xb') as stream:
            proc = subprocess.Popen(['adb', 'exec-out', f"su -c 'cat {node}'"], stdout=subprocess.PIPE)
            for chunk in iter(lambda: proc.stdout.read(1 << 20), b''):
                stream.write(chunk); digest.update(chunk); count += len(chunk)
            code = proc.wait(timeout=60)
        path.chmod(0o600)
        match = code == 0 and count == size and digest.hexdigest() == device_sha
        report['partitions'][name] = dict(bytes=count, expected_bytes=size, device_sha256=device_sha, host_sha256=digest.hexdigest(), verified=match, file=str(path.relative_to(MAIN)))
        print(name, count, 'verified' if match else 'MISMATCH', flush=True)
    report['outcome'] = 'pass' if all(p['verified'] for p in report['partitions'].values()) else 'fail'
    (out/'manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(report['outcome'])
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
