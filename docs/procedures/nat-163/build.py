#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scL: scJ (NAT-158, ran in NAT-159) with boot-arg touch_lat=1 after fb_filter=0. MiniIOMobileFramebuffer then writes a line for
every SwapEnd ("tl: s ID at US") and for every frame put on the panel ("tl: v ID ready US shown US done US"), and redwood_input one
for every touch, into the loader console log (loader_log_line). NAT-161 found the single core half idle on the idle home screen at
~10 frames/s: these lines show whether CoreAnimation hands over frames only every ~100 ms or frames wait in the driver. One
variable against scJ, instrumentation only. Everything else is nat-158/build.py's chain. Host build only.

  python3 -B docs/procedures/nat-163/build.py --out artifacts/nat-163/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scL-md1'
TAG = 'nat_attempt=NAT163-scL'
NEW = ('fb_filter=0', 'touch_lat=1')
SCJ_BUILD = ROOT / 'artifacts/nat-158/build-001'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b158 = _load('nat163_build158', HERE.parent / 'nat-158/build.py')


def expected_cmdline():
    old = json.loads((SCJ_BUILD / 'build.json').read_text())['payload_fixes'][b158.NAME]['cmdline']
    assert old.count(' fb_filter=0 ') == 1 and old.count(b158.TAG) == 1
    return old.replace(' fb_filter=0 ', ' fb_filter=0 touch_lat=1 ').replace(b158.TAG, TAG)


def main():
    assert len(NAME) == len(b158.NAME) and len(TAG) == len(b158.TAG) and b158.NEW == ('fb_filter=0',)
    want = expected_cmdline()
    saved = (b158.NAME, b158.TAG, b158.NEW)
    b158.NAME, b158.TAG, b158.NEW = NAME, TAG, NEW
    args = list(sys.argv)
    try:
        b158.main()
    finally:
        sys.argv = args
        b158.NAME, b158.TAG, b158.NEW = saved
    if '--check-only' in args or '--out' not in args:
        return
    out = Path(args[args.index('--out') + 1])
    path = out / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    if cmd != want:
        raise SystemExit('cmdline is not scJ\'s with touch_lat=1:\n %r\n %r' % (cmd, want))
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    report['nat163_changes'] = dict(cmdline_bytes=len(cmd.encode()), added='touch_lat=1', tag=TAG,
                                    purpose='per-swap and per-frame timing (and touch) lines: what paces the idle home screen at ~10 frames/s')
    report['nat163_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
