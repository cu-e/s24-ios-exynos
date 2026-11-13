#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""sc9: sc8 build plumbing, NAT-125 touch guard, PMIC init explicitly disabled.

No new power writes or native actions in this host build.
"""
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-sc9-md1'
TAG = 'nat_attempt=NAT126-sc9'
spec = importlib.util.spec_from_file_location('nat126_build123', HERE.parent / 'nat-123/build.py')
b123 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b123)


def main():
    saved = b123.NAME, b123.TAG, b123.KERNEL_DIR, b123.TOKENS
    b123.NAME, b123.TAG = NAME, TAG
    b123.KERNEL_DIR = ROOT / 'artifacts/nat-125/kernel-001'
    b123.TOKENS = ('e1s_wdt_pet=1', 'e1s_decon_hw=1', 'e1spmic=0')
    # The older wrapper's post-build check forbids disabled PMIC. Execute its
    # unchanged NAT-119 machinery directly with our own explicit final check.
    b119 = b123.b119
    old = (b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS, b119.KERNEL_DIR,
           b119.KERNEL_PATCH, b119.b117.append_new)
    b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS = NAME, TAG, b123.TOKENS
    b119.KERNEL_DIR, b119.KERNEL_PATCH = b123.KERNEL_DIR, b123.KERNEL_PATCH
    b119.b117.append_new = b123.append_new
    args = list(sys.argv)
    try:
        rec = json.loads((b123.KERNEL_DIR / 'rebuild.json').read_text())
        for entry in rec['extra_objects']:
            if b119.sha((ROOT / entry['patch']).read_bytes()) != entry['patch_sha256']:
                raise SystemExit('rebuild patch drift: ' + entry['patch'])
        b119.main()
    finally:
        sys.argv = args
        (b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS, b119.KERNEL_DIR,
         b119.KERNEL_PATCH, b119.b117.append_new) = old
        b123.NAME, b123.TAG, b123.KERNEL_DIR, b123.TOKENS = saved
    if '--check-only' in args:
        return
    out = b119.b113.argv_value(args, '--out')
    if out is None:
        return
    path = Path(out) / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    assert cmd.split().count('e1spmic=0') == 1
    assert not any(t in cmd.split() for t in ('e1spmic=2', 'e1spmic=3', 'e1stouch=0'))
    report['nat126_changes'] = dict(kernel=rec['no_storage_sha256'], pmic_mode=0,
                                    touch_guard='NAT-125', cmdline_bytes=len(cmd.encode()),
                                    purpose='Restore userland progress without any ACPM probe/PMIC access')
    report['nat126_sources'] = {'build.py': b119.sha((HERE / 'build.py').read_bytes())}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
