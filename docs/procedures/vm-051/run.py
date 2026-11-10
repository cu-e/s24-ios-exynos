#!/usr/bin/env python3
"""Run the VM-051 minimal KVM guest helper on the owner's S24 from RAM only, through su.

Authorized by decision 0002 (2026-11-10), which allows bounded KVM experiments
including a test VM. The helper creates one VM with one vCPU and 2 MiB of RAM,
runs a few guest instructions to PSCI SYSTEM_OFF and exits; an in-process alarm and
an outer timeout bound it. Nothing is written to disk; the tmpfs directory is
removed afterwards. The device serial is not recorded.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
RAM = '/dev/s24-vm051'
HELPER = f'{RAM}/kvm_guest'
CPUS = (0, 4, 9)


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
    out = MAIN/'artifacts/vm-051'/args.run
    out.mkdir(parents=True, exist_ok=False)
    binary = args.helper.read_bytes()
    local = hashlib.sha256(binary).hexdigest()
    report = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), su_used=True, vm_created=True, cpus=list(CPUS),
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
        # adb exec-in can return before the device-side writer finishes, so wait for the full file.
        for _ in range(20):
            code, text, err = su(f'sha256sum {HELPER}.in')
            if code == 0 and text.split()[:1] == [local]:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('Delivered helper never reached the expected hash')
        # Execute a copy: the delivering writer can still hold the first file open (ETXTBSY).
        code, text, err = su(f'cp {HELPER}.in {HELPER} && rm {HELPER}.in && chmod 700 {HELPER} && sha256sum {HELPER}')
        remote = text.split()[0] if text else ''
        report['steps']['hash'] = dict(exit_code=code, matches=remote == local)
        if code or remote != local:
            raise RuntimeError('Helper hash mismatch on device')
        report['results'] = {}
        for cpu in CPUS:
            code, text, err = su(f'timeout 15 {HELPER} {cpu}', timeout=40)
            report['steps'][f'guest-cpu{cpu}'] = dict(exit_code=code, stdout=text[:4000], stderr=err[:200])
            try:
                report['results'][str(cpu)] = json.loads(text)
            except ValueError:
                report['results'][str(cpu)] = None
            if code:
                break
        good = [r for r in report['results'].values() if r and r.get('ok') and r.get('console') == 'Hi']
        report['outcome'] = 'pass' if len(good) == len(CPUS) else 'fail'
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
