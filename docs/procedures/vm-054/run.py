#!/usr/bin/env python3
"""VM-054: run s24vmm on the owner's S24 from RAM only, through su (decision 0002: bounded KVM test VMs).

Delivers the VMM and its inputs into a tmpfs directory, checks every hash on the device, runs the
VMM under its own --timeout plus an outer `timeout`, then removes the directory and confirms it is
gone and that the phone did not reboot. Nothing is written to persistent storage. The device
serial is not recorded.

  run.py --run NAME --vmm PATH --file image=PATH [--file initrd=PATH] --timeout 30 -- [vmm args]

VMM arguments may refer to delivered files as {image}, {initrd}, ...
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
RAM = '/dev/s24-vm054'
NAME = re.compile(r'[a-z][a-z0-9_]{0,15}')


def adb(*argv, stdin=None, timeout=60):
    done = subprocess.run(['adb', *argv], input=stdin, capture_output=True, timeout=timeout)
    return done.returncode, done.stdout.decode(errors='replace'), done.stderr.decode(errors='replace')


def su(command, stdin=None, timeout=60):
    return adb('exec-in' if stdin is not None else 'shell', f"su -c '{command}'", stdin=stdin, timeout=timeout)


def uptime():
    code, out, _ = adb('shell', 'cat /proc/uptime')
    if code:
        raise RuntimeError('Plain adb uptime failed')
    return float(out.split()[0])


def deliver(name, data, report):
    digest = hashlib.sha256(data).hexdigest()
    target = f'{RAM}/{name}'
    code, _, err = su(f'cat > {target}.in', stdin=data, timeout=300)
    if code:
        raise RuntimeError(f'Delivery of {name} failed: {err[:200]}')
    # adb exec-in can return before the device-side writer finishes, so wait for the full file.
    for _ in range(60):
        code, out, _ = su(f'sha256sum {target}.in')
        if code == 0 and out.split()[:1] == [digest]:
            break
        time.sleep(0.5)
    else:
        raise RuntimeError(f'{name} never reached the expected hash')
    # Use a copy: the delivering writer can still hold the first file open (ETXTBSY).
    code, out, _ = su(f'cp {target}.in {target} && rm {target}.in && chmod 700 {target} && sha256sum {target}')
    if code or out.split()[:1] != [digest]:
        raise RuntimeError(f'{name} hash mismatch on device')
    report['delivered'][name] = dict(bytes=len(data), sha256=digest)
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--run', required=True)
    parser.add_argument('--vmm', type=Path, required=True)
    parser.add_argument('--file', action='append', default=[], help='name=path, delivered next to the VMM')
    parser.add_argument('--timeout', type=int, required=True, help='seconds passed to the VMM; the outer bound adds 15')
    parser.add_argument('vmm_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run) or not 1 <= args.timeout <= 1800:
        raise ValueError('Invalid run name or timeout')
    files = {}
    for item in args.file:
        name, _, path = item.partition('=')
        if not NAME.fullmatch(name) or name == 'vmm' or not path:
            raise ValueError(f'Invalid --file {item}')
        files[name] = Path(path)
    vmm_args = [a for a in args.vmm_args if a != '--']
    if any("'" in a for a in vmm_args):
        raise ValueError('Single quotes are not allowed in VMM arguments')
    rows = [l.split() for l in subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=20, check=True).stdout.splitlines()[1:] if l.strip()]
    if len(rows) != 1 or rows[0][1] != 'device':
        raise SystemExit('Need exactly one authorized device')
    out = MAIN/'artifacts/vm-054'/args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), su_used=True, vm_created=True,
                  ram_directory=RAM, timeout_seconds=args.timeout, delivered={}, steps={}, outcome='inconclusive')
    before = uptime()
    code, _, err = su(f'mkdir -m 700 {RAM}')
    report['steps']['mkdir'] = dict(exit_code=code, stderr=err[:200])
    created = code == 0
    try:
        if not created:
            raise RuntimeError('Could not create the RAM directory; su may be denied or the directory exists')
        vmm = deliver('vmm', args.vmm.read_bytes(), report)
        paths = {name: deliver(name, path.read_bytes(), report) for name, path in files.items()}
        argv = ' '.join(f'"{a.format(**paths)}"' for a in vmm_args)
        command = f'cd {RAM} && timeout {args.timeout + 15} {vmm} --timeout {args.timeout} {argv} > {RAM}/stdout 2> {RAM}/stderr; echo $?'
        report['steps']['command'] = command
        started = time.monotonic()
        code, text, err = su(command, timeout=args.timeout + 60)
        report['steps']['vmm'] = dict(adb_exit=code, vmm_exit=text.strip()[-8:], wall_seconds=round(time.monotonic() - started, 3), stderr=err[:300])
        for stream in ['stdout', 'stderr']:
            code, text, _ = su(f'cat {RAM}/{stream}', timeout=60)
            (out/f'{stream}.txt').write_text(text)
            report[f'{stream}_bytes'] = len(text)
        events = [json.loads(line) for line in (out/'stderr.txt').read_text().splitlines() if line.startswith('{"s24vmm"')]
        report['vmm_events'] = events
        end = next((e for e in events if e.get('s24vmm') == 'end'), None)
        code, text, _ = su('pidof s24vmm vmm; echo done')
        report['steps']['vmm_gone'] = text.strip() == 'done'
        report['end_cause'] = end.get('cause') if end else None
        report['outcome'] = 'pass' if end and report['steps']['vmm_gone'] else 'fail'
    except Exception as error:
        report['outcome'] = 'fail'
        report['error'] = repr(error)
    finally:
        if created:
            code, text, _ = su(f'rm -rf {RAM}; test -e {RAM}; echo $?')
            report['steps']['cleanup'] = dict(exit_code=code, absent=text.strip().endswith('1'))
            if not report['steps']['cleanup']['absent']:
                report['outcome'] = 'fail'
    after = uptime()
    report['uptime_seconds'] = dict(before=before, after=after, no_reboot=after > before)
    if not report['uptime_seconds']['no_reboot']:
        report['outcome'] = 'fail'
    path = out/'report.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: report.get(k) for k in ['outcome', 'end_cause', 'error', 'uptime_seconds']}))
    return 0 if report['outcome'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
