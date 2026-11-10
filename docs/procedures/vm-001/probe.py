#!/usr/bin/env python3
"""Read-only virtualization availability probe for the connected S24 (VM-001).

Runs a fixed list of commands through already-authorized ADB as the shell user.
No su, adb root, pairing, install, settings change, reboot or partition access.
It never opens /dev/kvm and never starts a virtual machine. `vm info` only asks
the Android virtualization service what the device reports.

The device serial is held in memory to scrub output and is never written.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
PROPS = [
    'ro.product.device', 'ro.product.model', 'ro.build.version.incremental',
    'ro.build.version.release', 'ro.build.version.sdk',
    'ro.boot.hypervisor.vm.supported', 'ro.boot.hypervisor.protected_vm.supported',
    'ro.boot.hypervisor.version',
]
CHECKS = [
    ('identity', 'id'),
    ('kernel-version', 'uname -r'),
    ('kvm-node', 'ls -lZ /dev/kvm'),
    ('kvm-shell-readable', 'test -r /dev/kvm; echo $?'),
    ('kvm-shell-writable', 'test -w /dev/kvm; echo $?'),
    ('avf-feature', 'pm has-feature android.software.virtualization_framework'),
    ('avf-service', 'service check android.system.virtualizationservice'),
    ('avf-service-list', "service list | grep -i -E 'virtuali[sz]ation|microdroid'"),
    ('avf-apex', 'ls -ld /apex/com.android.virt'),
    ('avf-apex-bin', 'ls /apex/com.android.virt/bin'),
    ('avf-packages', 'pm list packages --user 0 virtualization'),
    ('avf-vm-info', '/apex/com.android.virt/bin/vm info'),
]
IMEI = re.compile(r'\b\d{15}\b')
MAC = re.compile(r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b')


def connected_serial():
    done = subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=20, check=True)
    rows = [line.split() for line in done.stdout.splitlines()[1:] if line.strip()]
    ready = [row[0] for row in rows if len(row) == 2 and row[1] == 'device']
    if len(rows) != 1 or len(ready) != 1:
        raise SystemExit('Need exactly one authorized device; refusing to guess')
    return ready[0]


def scrub(text, serial):
    return MAC.sub('<mac>', IMEI.sub('<digits15>', text.replace(serial, '<serial>')))


def shell(command, serial):
    try:
        done = subprocess.run(['adb', 'shell', command], capture_output=True, text=True, timeout=30)
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as error:
        code, out, err = 'timeout', error.stdout or '', error.stderr or ''
        out = out.decode(errors='replace') if isinstance(out, bytes) else out
        err = err.decode(errors='replace') if isinstance(err, bytes) else err
    return dict(command=command, exit_code=code, stdout=scrub(out, serial)[:4000], stderr=scrub(err, serial)[:1000])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    out = ROOT/'artifacts/vm-001'/args.run
    out.mkdir(parents=True, exist_ok=False)
    serial = connected_serial()
    report = dict(schema_version=1, kind='android-userland', origin='adb-shell', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),
                  probe_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), su_used=False, device_state_changed=False,
                  kvm_opened=False, vm_started=False, props={}, checks={})
    for name in PROPS:
        report['props'][name] = shell(f'getprop {name}', serial)['stdout'].strip()
    for name, command in CHECKS:
        report['checks'][name] = shell(command, serial)
    path = out/'report.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    if serial in path.read_text():
        path.unlink()
        raise SystemExit('Serial leaked into the report; deleted it')
    print(json.dumps(dict(report=str(path.relative_to(ROOT)), sha256=hashlib.sha256(path.read_bytes()).hexdigest()), indent=1))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
