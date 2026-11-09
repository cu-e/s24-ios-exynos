#!/usr/bin/env python3
"""Run the VM-050 KVM API helper on the owner's S24 from RAM only, through su.

Authorized by the owner on 2026-11-10 for opening /dev/kvm and querying the API
version, with no VM created and no disk write. The helper lives in a tmpfs
directory that is removed afterwards. The device serial is not recorded.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
RAM = '/dev/s24-vm050'
HELPER = f'{RAM}/kvm_api'


def adb(*argv, stdin=None, timeout=40):
    done = subprocess.run(['adb', *argv], input=stdin, capture_output=True, timeout=timeout)
    return done.returncode, done.stdout.decode(errors='replace').strip(), done.stderr.decode(errors='replace').strip()


def su(command, stdin=None, timeout=40):
    return adb('exec-in' if stdin is not None else 'shell', f"su -c '{command}'", stdin=stdin, timeout=timeout)


def uptime():
    code, out, _ = adb('shell', 'cat /proc/uptime')
    if code:
        raise RuntimeError('Plain adb uptime failed')
    return float(out.split()[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--helper', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    rows = [l.split() for l in subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=20, check=True).stdout.splitlines()[1:] if l.strip()]
    if len(rows) != 1 or rows[0][1] != 'device':
        raise SystemExit('Need exactly one authorized device')
    out = MAIN/'artifacts/vm-050'/args.run
    out.mkdir(parents=True, exist_ok=False)
    binary = args.helper.read_bytes()
    local = hashlib.sha256(binary).hexdigest()
    report = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), su_used=True, vm_created=False, ioctls=['KVM_GET_API_VERSION'],
                  helper_sha256=local, ram_directory=RAM, steps={}, outcome='inconclusive')
    before = uptime()
    code, text, err = su(f'mkdir -m 700 {RAM}')
    report['steps']['mkdir'] = dict(exit_code=code, stderr=err[:200])
    created = code == 0
    try:
        if not created:
            raise RuntimeError('Could not create the RAM directory; su may be denied or the directory exists')
        code, text, err = su(f'cat > {HELPER}.in', stdin=binary)
        report['steps']['deliver'] = dict(exit_code=code, stderr=err[:200])
        if code:
            raise RuntimeError('Helper delivery failed')
        # Execute a copy: the delivering writer can still hold the first file open (ETXTBSY).
        code, text, err = su(f'cp {HELPER}.in {HELPER} && rm {HELPER}.in && chmod 700 {HELPER} && sha256sum {HELPER}')
        remote = text.split()[0] if text else ''
        report['steps']['hash'] = dict(exit_code=code, matches=remote == local)
        if code or remote != local:
            raise RuntimeError('Helper hash mismatch on device')
        code, text, err = su(f'timeout 10 {HELPER}')
        report['steps']['probe'] = dict(exit_code=code, stdout=text[:300], stderr=err[:200])
        report['result'] = json.loads(text)
        report['outcome'] = 'pass' if code == 0 and report['result'].get('api_version') is not None else 'fail'
    except Exception as error:
        report['outcome'] = 'fail'
        report['error'] = repr(error)
    finally:
        if created:
            code, text, err = su(f'rm -rf {RAM}; test -e {RAM}; echo $?')
            report['steps']['cleanup'] = dict(exit_code=code, absent=text.strip().endswith('1'))
            if not report['steps']['cleanup']['absent']:
                report['outcome'] = 'fail'
    after = uptime()
    report['uptime_seconds'] = dict(before=before, after=after, no_reboot=after > before)
    if not report['uptime_seconds']['no_reboot']:
        report['outcome'] = 'fail'
    path = out/'report.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    print(path.read_text())
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
