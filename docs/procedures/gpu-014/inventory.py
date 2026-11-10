#!/usr/bin/env python3
"""Read-only Vulkan driver inventory for the connected S24 (GPU-014).

Runs a fixed list of plain ADB shell commands. No su, install, settings change,
rendering, pairing or reboot. `cmd gpu vkjson` asks Android's own gpu service to
enumerate the driver. The device serial is held in memory only to scrub output.
Raw output stays in a Git-ignored artifact directory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

MAIN = Path('/home/egor/dev/pet/s24-ios-exynos')
PROPS = ['ro.hardware.vulkan', 'ro.hardware.egl', 'ro.opengles.version', 'ro.board.platform', 'ro.soc.manufacturer', 'ro.soc.model',
         'ro.product.device', 'ro.build.version.incremental', 'ro.build.version.sdk']
CHECKS = [('features', "pm list features | grep -iE 'vulkan|opengl'"),
          ('surfaceflinger-gles', "dumpsys SurfaceFlinger | grep -E '^GLES:|EGL (implementation|version)'")]
IMEI = re.compile(r'\b\d{15}\b')
MAC = re.compile(r'\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b')


def scrub(text, serial):
    return MAC.sub('<mac>', IMEI.sub('<digits15>', text.replace(serial, '<serial>')))


def shell(command, serial, timeout=45):
    done = subprocess.run(['adb', 'shell', command], capture_output=True, text=True, timeout=timeout)
    return dict(command=command, exit_code=done.returncode, stdout=scrub(done.stdout, serial), stderr=scrub(done.stderr, serial)[:500])


def version(value):
    value = int(value)  # vkjson prints large integers in floating-point form
    return f'{value >> 22 & 0x7f}.{value >> 12 & 0x3ff}.{value & 0xfff}'


def extension_names(items):
    return sorted(item.get('extensionName', '') for item in items)


def summarize(data):
    devices = []
    for device in data.get('devices', []):
        props = device.get('properties', {})
        limits = props.get('limits', {})
        devices.append(dict(
            name=props.get('deviceName'), api_version=version(props.get('apiVersion', 0)), driver_version_raw=props.get('driverVersion'),
            vendor_id=hex(int(props.get('vendorID', 0))), device_id=hex(int(props.get('deviceID', 0))), device_type=props.get('deviceType'),
            limits={k: limits.get(k) for k in ['maxImageDimension2D', 'maxPushConstantsSize', 'maxBoundDescriptorSets', 'maxComputeSharedMemorySize', 'maxMemoryAllocationCount', 'timestampPeriod'] if k in limits},
            queues=device.get('queues'), memory_heaps=device.get('memory', {}).get('memoryHeaps'), memory_types=len(device.get('memory', {}).get('memoryTypes', [])),
            device_extensions=extension_names(device.get('extensions', [])), device_layers=len(device.get('layers', []))))
    return dict(instance_extensions=extension_names(data.get('extensions', [])), instance_layers=len(data.get('layers', [])), device_count=len(devices), devices=devices)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', args.run):
        raise ValueError('Invalid run name')
    rows = [l.split() for l in subprocess.run(['adb', 'devices'], capture_output=True, text=True, timeout=20, check=True).stdout.splitlines()[1:] if l.strip()]
    if len(rows) != 1 or rows[0][1] != 'device':
        raise SystemExit('Need exactly one authorized device')
    serial = rows[0][0]
    out = MAIN/'artifacts/gpu-014'/args.run
    out.mkdir(parents=True, exist_ok=False)
    raw = shell('cmd gpu vkjson', serial, timeout=60)
    (out/'vkjson.raw.json').write_text(raw['stdout'])
    text = raw['stdout']
    start = text.find('{')
    data = json.loads(text[start:])
    report = dict(schema_version=1, kind='android-userland', origin='adb-shell', recorded_at=datetime.now(timezone.utc).isoformat(timespec='seconds'), su_used=False, installed=False, rendered=False, device_state_changed=False,
                  vkjson_exit_code=raw['exit_code'], vkjson_sha256=hashlib.sha256(text.encode()).hexdigest(), props={}, checks={}, summary=summarize(data))
    for name in PROPS:
        report['props'][name] = shell(f'getprop {name}', serial)['stdout'].strip()
    for name, command in CHECKS:
        report['checks'][name] = shell(command, serial)
    path = out/'report.json'
    path.write_text(json.dumps(report, indent=2)+'\n')
    if serial in path.read_text() or serial in (out/'vkjson.raw.json').read_text():
        path.unlink()
        (out/'vkjson.raw.json').unlink()
        raise SystemExit('Serial leaked into saved output; deleted it')
    print(json.dumps(dict(report=str(path.relative_to(MAIN)), sha256=hashlib.sha256(path.read_bytes()).hexdigest())))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
