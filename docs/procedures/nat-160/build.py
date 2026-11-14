#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scK: scJ (NAT-158, ran in NAT-159) with boot-arg fbscale=2 after fb_filter=0. MiniIOMobileFramebuffer then reports 750x1624
(375x812 points at two pixels a point) and sets /chosen display-scale and /product artwork-scale-factor to 2, so iOS renders 2.25
times fewer pixels; the driver still writes all 1080x2340 panel pixels (nearest-neighbour, enlarging). NAT-156 lever 4. One variable
against scJ. Everything else is nat-158/build.py's chain (scH's kernel, NAT-157 loader fix, both gates). Host build only.

  python3 -B docs/procedures/nat-160/build.py --out artifacts/nat-160/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scK-md1'
TAG = 'nat_attempt=NAT160-scK'
NEW = ('fb_filter=0', 'fbscale=2')
SCJ_BUILD = ROOT / 'artifacts/nat-158/build-001'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b158 = _load('nat160_build158', HERE.parent / 'nat-158/build.py')


def expected_cmdline():
    old = json.loads((SCJ_BUILD / 'build.json').read_text())['payload_fixes'][b158.NAME]['cmdline']
    assert old.count(' fb_filter=0 ') == 1 and old.count(b158.TAG) == 1
    return old.replace(' fb_filter=0 ', ' fb_filter=0 fbscale=2 ').replace(b158.TAG, TAG)


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
        raise SystemExit('cmdline is not scJ\'s with fbscale=2:\n %r\n %r' % (cmd, want))
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    report['nat160_changes'] = dict(cmdline_bytes=len(cmd.encode()), added='fbscale=2', tag=TAG,
                                    purpose='2x UI scale: 2.25x fewer pixels rendered on the single-core software path, against NAT-159')
    report['nat160_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
