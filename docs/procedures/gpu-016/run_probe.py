#!/usr/bin/env python3
"""Bounded stock-Vulkan run of the TST-002-qualified probe APK on the S24 (GPU-016, child of GPU-003).

Fixed sequence over already-authorized ADB as the shell user: verify the exact qualified APK bytes,
install it for user 0 only, run a few single clear/readback tests through the app's own UI, exercise
the in-app Stop and process force-stop paths, then uninstall and verify absence and uptime. No su, no
settings change, no reboot, no stress loop. Every ADB call has a timeout. The device serial is held in
memory only to scrub output. Raw output stays in the Git-ignored artifacts/gpu-016/<run>/ directory.
Only UI nodes of the probe package are kept; the rest of the window hierarchy is discarded unsaved.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
PKG = 'dev.egor.s24probe'
ACTIVITY = PKG + '/.MainActivity'
QUALIFIED_SHA256 = '1187f632f1b1bd20d4e8ce0c29d21959b4f51760de3e17e55064fe2d8f23afd6'
DEVICE_UI = '/data/local/tmp/gpu016-ui.xml'
SEQUENTIAL_RUNS = 5
IMEI = re.compile(r'\b\d{15}\b')
MAC = re.compile(r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


class Session:
    def __init__(self, serial):
        self.serial = serial
        self.log = []

    def scrub(self, text):
        return MAC.sub('<mac>', IMEI.sub('<digits15>', text.replace(self.serial, '<serial>')))

    def adb(self, argv, timeout=30, keep=4000, label=None):
        started = time.monotonic()
        try:
            done = subprocess.run(['adb', *argv], capture_output=True, text=True, timeout=timeout)
            code, out, err = done.returncode, done.stdout, done.stderr
        except subprocess.TimeoutExpired as exc:
            code, out, err = 'timeout', (exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout, bytes) else (exc.stdout or ''), f'host timeout after {timeout}s'
        entry = dict(at=now(), label=label, argv=['adb', *argv], exit_code=code, seconds=round(time.monotonic() - started, 3),
                     stdout=self.scrub(out)[:keep], stderr=self.scrub(err)[:1000])
        self.log.append(entry)
        return code, self.scrub(out), self.scrub(err)

    def shell(self, command, timeout=30, keep=4000, label=None):
        return self.adb(['shell', command], timeout=timeout, keep=keep, label=label)


def thermal(s, label):
    code, out, _ = s.shell('dumpsys thermalservice', timeout=20, keep=0, label='thermal-' + label)
    status = re.search(r'^Thermal Status: (\d+)', out, re.M)
    section = out.split('Current temperatures from HAL:', 1)[1] if 'Current temperatures from HAL:' in out else ''
    section = section.split('Current cooling devices', 1)[0]
    temps = {m.group(2): float(m.group(1)) for m in re.finditer(r'mValue=([-0-9.]+), mType=\d+, mName=([A-Z0-9_]+)', section)}
    return dict(label=label, at=now(), exit_code=code, thermal_status=int(status.group(1)) if status else None, hal_celsius=temps)


def uptime(s, label):
    code, out, _ = s.shell('cat /proc/uptime', timeout=15, label='uptime-' + label)
    return float(out.split()[0]) if code == 0 and out.strip() else None


def installed(s, label):
    code, out, _ = s.shell(f'pm list packages --user 0 {PKG}', timeout=20, label='pm-list-' + label)
    return code, any(line.strip() == 'package:' + PKG for line in out.splitlines())


def package_record(s, label):
    code, out, _ = s.shell(f'dumpsys package {PKG} | grep -c "Package \\[{PKG}\\]"', timeout=30, label='pm-record-' + label)
    return int(out.strip() or 0) if out.strip().isdigit() else None


def pid(s, label):
    code, out, _ = s.shell(f'pidof {PKG}', timeout=15, label='pidof-' + label)
    return out.strip() or None


def screen(s, label):
    _, power, _ = s.shell('dumpsys power | grep -E "mWakefulness="', timeout=20, label='power-' + label)
    _, window, _ = s.shell('dumpsys window | grep -E "isKeyguardShowing|mCurrentFocus="', timeout=20, label='window-' + label)
    focus = [line.strip() for line in window.splitlines() if 'mCurrentFocus=' in line]
    probe_focused = any(PKG in line for line in focus)
    # Never retain the name of another foreground app.
    s.log[-1]['stdout'] = '\n'.join(line if (PKG in line or 'isKeyguardShowing' in line) else '<non-probe window line>' for line in window.splitlines())
    return dict(label=label, awake='mWakefulness=Awake' in power, keyguard_showing='isKeyguardShowing=true' in window, probe_focused=probe_focused)


def ui(s, label):
    """Dump the hierarchy, keep only probe-package nodes, delete the device copy."""
    for attempt in range(3):
        code, out, _ = s.shell(f'uiautomator dump {DEVICE_UI} >/dev/null 2>&1 && cat {DEVICE_UI}; rm -f {DEVICE_UI}', timeout=30, keep=0, label=f'ui-{label}-{attempt}')
        start = out.find('<?xml')
        if start >= 0:
            try:
                root = ET.fromstring(out[start:].strip())
                break
            except ET.ParseError:
                pass
        time.sleep(0.5)
    else:
        return dict(label=label, ok=False, nodes=[])
    nodes = []
    for node in root.iter('node'):
        if node.get('package') != PKG:
            continue
        b = [int(v) for v in re.findall(r'\d+', node.get('bounds', ''))]
        nodes.append(dict(text=node.get('text', ''), cls=node.get('class', '').rsplit('.', 1)[-1], enabled=node.get('enabled') == 'true', bounds=b))
    return dict(label=label, ok=True, at=now(), nodes=nodes)


def find(view, text):
    for node in view['nodes']:
        if node['text'] == text and len(node['bounds']) == 4:
            x0, y0, x1, y1 = node['bounds']
            return dict(x=(x0 + x1) // 2, y=(y0 + y1) // 2, enabled=node['enabled'])
    return None


def status_text(view):
    for node in view['nodes']:
        t = node['text']
        if t.startswith(('Ready to test', 'Result:', 'Previous result:', 'Testing image', 'Stopping', 'This test session', 'Test exceeded', 'A previous test', 'Previous test ended', 'Saved report could not')):
            return t
    return None


def read_report(s, label):
    code, out, _ = s.shell(f'run-as {PKG} cat files/last-report.json', timeout=15, label='report-' + label)
    if code != 0:
        return None
    try:
        return json.loads(out)
    except ValueError:
        return None


def wait_report(s, previous_stamp, label, limit=10.0):
    deadline = time.monotonic() + limit
    while time.monotonic() < deadline:
        report = read_report(s, label)
        if report and report.get('recorded_at') != previous_stamp:
            return report
        time.sleep(0.3)
    return None


def launch(s, label):
    s.shell(f'am start -W -n {ACTIVITY}', timeout=30, label='launch-' + label)
    for _ in range(20):
        state = screen(s, label)
        if state['probe_focused']:
            return state
        time.sleep(0.5)
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    parser.add_argument('--apk', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    apk_bytes = args.apk.read_bytes()
    apk_sha = hashlib.sha256(apk_bytes).hexdigest()
    if apk_sha != QUALIFIED_SHA256:
        raise SystemExit(f'APK {apk_sha} is not the TST-002-qualified digest; refusing to install')
    rows = [l.split() for l in subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=20, check=True).stdout.splitlines()[1:] if l.strip()]
    if len(rows) != 1 or rows[0][1] != 'device':
        raise SystemExit('Need exactly one authorized device')
    s = Session(rows[0][0])
    out = MAIN / 'artifacts/gpu-016' / args.run
    out.mkdir(parents=True, exist_ok=False)
    report = dict(schema_version=1, kind='android-userland', origin='local-device', task='GPU-016', parent_task='GPU-003', started_at=now(),
                  apk=dict(path=str(args.apk.resolve().relative_to(MAIN)) if args.apk.resolve().is_relative_to(MAIN) else args.apk.name, sha256=apk_sha, size=len(apk_bytes)),
                  su_used=False, settings_changed=False, reboot_requested=False, thermal=[], ui=[], runs=[], stop_tests=[], notes=[])
    t_start = time.monotonic()
    install_done = False
    try:
        _, model, _ = s.shell('getprop ro.product.model', label='model')
        _, incremental, _ = s.shell('getprop ro.build.version.incremental', label='incremental')
        report['device'] = dict(model=model.strip(), incremental=incremental.strip())
        report['uptime_before_s'] = uptime(s, 'before')
        report['thermal'].append(thermal(s, 'before-install'))
        code, present = installed(s, 'before')
        report['preinstalled'] = present
        if code != 0 or present:
            raise RuntimeError('Probe package query failed or package already present; refusing to touch it')
        state = screen(s, 'before')
        report['screen_before'] = state
        if not state['awake'] or state['keyguard_showing']:
            raise RuntimeError('Screen is not awake/unlocked; this script does not wake or unlock the phone')
        code, outp, errp = s.adb(['install', '--user', '0', str(args.apk)], timeout=180, label='install')
        install_done = True  # Attempted; cleanup must verify absence either way.
        code2, present = installed(s, 'after-install')
        report['install'] = dict(exit_code=code, stdout=outp.strip()[-300:], stderr=errp.strip()[-300:], present=present)
        if code != 0 or not present:
            raise RuntimeError('Install failed')
        s.shell(f'dumpsys package {PKG} | grep -E "versionName|primaryCpuAbi|pkgFlags|installed=" | head -8', timeout=30, label='package-facts')

        report['launch_cold'] = launch(s, 'cold')
        if not report['launch_cold']['probe_focused']:
            raise RuntimeError('Probe window did not take focus; no taps issued')
        view = ui(s, 'initial'); report['ui'].append(view)
        previous = (read_report(s, 'initial') or {}).get('recorded_at')
        report['initial_report_present'] = previous is not None

        # Sequential single-image runs in one process (first is the cold driver load).
        for index in range(1, SEQUENTIAL_RUNS + 1):
            view = ui(s, f'before-run{index}')
            start = find(view, 'Start test')
            if not start or not start['enabled'] or not screen(s, f'run{index}')['probe_focused']:
                report['notes'].append(f'run{index}: Start missing/disabled or probe not focused; sequence stopped')
                break
            tapped = time.monotonic()
            s.shell(f'input tap {start["x"]} {start["y"]}', timeout=15, label=f'tap-start-run{index}')
            result = wait_report(s, previous, f'run{index}')
            after = ui(s, f'after-run{index}'); report['ui'].append(after)
            report['runs'].append(dict(run=index, host_seconds_to_report=round(time.monotonic() - tapped, 3), report=result,
                                       status_after=status_text(after), stop_enabled_after=(find(after, 'Stop') or {}).get('enabled'),
                                       start_enabled_after=(find(after, 'Start test') or {}).get('enabled')))
            if not result:
                report['notes'].append(f'run{index}: no new report within 10 s; sequence stopped')
                break
            previous = result['recorded_at']
            if result.get('outcome') != 'pass' or result.get('requires_process_restart'):
                report['notes'].append(f'run{index}: outcome {result.get("outcome")}; sequence stopped')
                break
            time.sleep(1.0)
        report['thermal'].append(thermal(s, 'after-sequential-runs'))

        # Stop test A: cooperative in-app Stop raced against a cold-process run. The stagger between
        # the Start and Stop taps is derived from the measured cold run so Stop lands inside its window.
        cold_ms = float(((report['runs'] or [{}])[0].get('report') or {}).get('elapsed_ms') or 100.0)
        staggers = [f'{min(max(cold_ms / 2000, 0.01), 0.1):.3f}', f'{min(max(cold_ms / 4000, 0.005), 0.05):.3f}']
        for attempt, stagger in enumerate(staggers, start=1):
            test = dict(name=f'in-app-stop-attempt{attempt}', stagger_s=float(stagger))
            s.shell(f'am force-stop {PKG}', timeout=20, label=f'force-stop-idle-a{attempt}')
            test['pid_after_idle_force_stop'] = pid(s, f'idle-a{attempt}')
            test['relaunch'] = launch(s, f'stop-a{attempt}')
            time.sleep(1.0)
            view = ui(s, f'relaunch-a{attempt}'); report['ui'].append(view)
            test['status_on_relaunch'] = status_text(view)
            test['report_unchanged_on_relaunch'] = (read_report(s, f'relaunch-a{attempt}') or {}).get('recorded_at') == previous
            start, stop = find(view, 'Start test'), find(view, 'Stop')
            if not (start and stop and start['enabled'] and test['relaunch']['probe_focused']):
                test['result'] = 'not attempted: Start/Stop not found, Start disabled or probe not focused'
                report['stop_tests'].append(test); break
            tapped = time.monotonic()
            s.shell(f'input tap {start["x"]} {start["y"]} & sleep {stagger}; input tap {stop["x"]} {stop["y"]}; wait', timeout=20, label=f'race-start-stop-a{attempt}')
            result = wait_report(s, previous, f'stop-a{attempt}')
            after = ui(s, f'after-stop-a{attempt}'); report['ui'].append(after)
            test.update(host_seconds_to_report=round(time.monotonic() - tapped, 3), report=result, status_after=status_text(after),
                        start_enabled_after=(find(after, 'Start test') or {}).get('enabled'))
            report['stop_tests'].append(test)
            if result:
                previous = result['recorded_at']
            if not result or result.get('outcome') == 'cancelled' or result.get('requires_process_restart'):
                break
        # Follow-up run proves the app and driver remain usable after the cooperative stop.
        view = ui(s, 'before-post-stop-run')
        start = find(view, 'Start test')
        if start and start['enabled'] and screen(s, 'post-stop')['probe_focused']:
            tapped = time.monotonic()
            s.shell(f'input tap {start["x"]} {start["y"]}', timeout=15, label='tap-start-post-stop')
            result = wait_report(s, previous, 'post-stop')
            report['stop_tests'].append(dict(name='run-after-in-app-stop', host_seconds_to_report=round(time.monotonic() - tapped, 3), report=result))
            if result:
                previous = result['recorded_at']

        # Stop test B: terminate the process while a run is being started.
        test = dict(name='force-stop-during-run', stagger_s=0.05)
        view = ui(s, 'before-kill')
        start = find(view, 'Start test')
        if start and start['enabled'] and screen(s, 'kill')['probe_focused']:
            before_pid = pid(s, 'before-kill')
            s.shell(f'input tap {start["x"]} {start["y"]} & sleep 0.05; am force-stop {PKG}; wait', timeout=20, label='race-start-force-stop')
            time.sleep(0.5)
            test.update(pid_before=bool(before_pid), pid_after=pid(s, 'after-kill'))
            after_kill = read_report(s, 'after-kill')
            test['run_completed_before_kill'] = bool(after_kill and after_kill.get('recorded_at') != previous)
            if test['run_completed_before_kill']:
                test['report'] = after_kill; previous = after_kill['recorded_at']
            test['relaunch'] = launch(s, 'after-kill')
            time.sleep(1.0)
            view = ui(s, 'relaunch-after-kill'); report['ui'].append(view)
            test['status_on_relaunch'] = status_text(view)
            start = find(view, 'Start test')
            if start and start['enabled'] and test['relaunch']['probe_focused']:
                tapped = time.monotonic()
                s.shell(f'input tap {start["x"]} {start["y"]}', timeout=15, label='tap-start-after-kill')
                result = wait_report(s, previous, 'after-kill-run')
                test['run_after_relaunch'] = dict(host_seconds_to_report=round(time.monotonic() - tapped, 3), report=result)
                if result:
                    previous = result['recorded_at']
        else:
            test['result'] = 'not attempted: Start not available or probe not focused'
        report['stop_tests'].append(test)
        current = pid(s, 'before-log')
        if current:
            s.shell(f'logcat -d -t 400 --pid={current.split()[0]}', timeout=30, keep=20000, label='logcat-probe-pid')
        report['thermal'].append(thermal(s, 'after-stop-tests'))
    except Exception as error:  # noqa: BLE001 - every failure still runs cleanup below
        report['error'] = f'{type(error).__name__}: {error}'
    finally:
        s.shell(f'am force-stop {PKG}', timeout=20, label='final-force-stop')
        report['pid_after_final_force_stop'] = pid(s, 'final')
        if install_done:
            s.shell(f'pm uninstall --user 0 {PKG}', timeout=60, label='uninstall-user0')
            if package_record(s, 'after-user0-uninstall'):
                s.shell(f'pm uninstall {PKG}', timeout=60, label='uninstall-all')
        s.shell(f'rm -f {DEVICE_UI}; ls {DEVICE_UI} 2>&1', timeout=15, label='remove-ui-dump')
        code, present = installed(s, 'final')
        report['final'] = dict(pm_list_exit=code, package_present_user0=present, package_records=package_record(s, 'final'),
                               uptime_after_s=uptime(s, 'after'))
        report['final']['no_reboot'] = (report.get('uptime_before_s') is not None and report['final']['uptime_after_s'] is not None
                                        and report['final']['uptime_after_s'] > report['uptime_before_s'])
        report['thermal'].append(thermal(s, 'after-uninstall'))
        report['device_seconds'] = round(time.monotonic() - t_start, 1)
        report['finished_at'] = now()
        report['commands'] = s.log
        path = out / 'report.json'
        text = json.dumps(report, indent=2) + '\n'
        if s.serial in text:
            raise SystemExit('Serial leaked into output; nothing saved')
        path.write_text(text)
        print(json.dumps(dict(report=str(path.relative_to(MAIN)), sha256=hashlib.sha256(text.encode()).hexdigest(),
                              error=report.get('error'), runs=[(r['report'] or {}).get('outcome') for r in report['runs']],
                              final=report['final'])))
    return 0 if 'error' not in report else 1


if __name__ == '__main__':
    raise SystemExit(main())
