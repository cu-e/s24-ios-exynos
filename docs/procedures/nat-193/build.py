#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scZ: scV (NAT-185, ran in NAT-186 and NAT-188) with boot-arg fbscale=2 in the place of touch_lat=1. MiniIOMobileFramebuffer then
reports 750x1624 (375x812 points at two pixels a point) and sets /chosen display-scale and /product artwork-scale-factor to 2, so
backboardd composes 2.25 times fewer pixels in software (NAT-192: its time is per-pixel resampling, masks and blending). The driver
still writes all 1080x2340 panel pixels from its NAT-183 run table (750 -> 1080 is an upscale). Same kernel
(artifacts/nat-185/kernel-001) and md0 root as scV; only the command line differs.

Why the swap: the 255-byte line convention of the chain (nat-158/165 asserts) has no room for one more token; touch_lat=1 only adds the
per-swap `tl:` lines, which bbd188 (NAT-194's verdict) does not read. Host build only.

  python3 -B docs/procedures/nat-193/build.py --out artifacts/nat-193/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scZ-md1'
TAG = 'nat_attempt=NAT193-scZ'
OLD_TOKEN, NEW_TOKEN = 'touch_lat=1', 'fbscale=2'
SCV_BUILD = ROOT / 'artifacts/nat-185/build-001'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b185 = _load('nat193_build185', HERE.parent / 'nat-185/build.py')
b174 = b185.b183.b176.b174
b165 = b174.b165


def expected_cmdline():
    old = json.loads((SCV_BUILD / 'build.json').read_text())['payload_fixes'][b185.NAME]['cmdline']
    assert old.count(' %s ' % OLD_TOKEN) == 1 and old.count(b185.TAG) == 1 and NEW_TOKEN.split('=')[0] not in old
    return old.replace(' %s ' % OLD_TOKEN, ' %s ' % NEW_TOKEN).replace(b185.TAG, TAG)


def main():
    assert len(NAME) == len(b185.NAME) and len(TAG) == len(b185.TAG)
    assert b174.NEW == ('fb_filter=0', OLD_TOKEN), b174.NEW
    want = expected_cmdline()
    real165 = b165.main

    def main165():
        # nat-174's main has just installed its expected line (cpuload=1000 -> touch_lat=1); scZ expects fbscale=2 there instead
        e = b165.expected_cmdline

        def expected():
            c = e()
            assert c.count(' %s ' % OLD_TOKEN) == 1
            return c.replace(' %s ' % OLD_TOKEN, ' %s ' % NEW_TOKEN)
        b165.expected_cmdline = expected
        try:
            real165()
        finally:
            b165.expected_cmdline = e

    saved = (b185.NAME, b185.TAG, b174.NEW, b165.main)
    b185.NAME, b185.TAG, b174.NEW, b165.main = NAME, TAG, ('fb_filter=0', NEW_TOKEN), main165
    args = list(sys.argv)
    try:
        b185.main()
    finally:
        sys.argv = args
        b185.NAME, b185.TAG, b174.NEW, b165.main = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    if cmd != want:
        raise SystemExit('cmdline is not scV\'s with fbscale=2 in place of touch_lat=1:\n %r\n %r' % (cmd, want))
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    scv = json.loads((SCV_BUILD / 'build.json').read_text())
    assert report['nat185_changes']['kernel'] == scv['nat185_changes']['kernel'], 'kernel differs from scV'
    report['nat165_changes']['added'] = '%s (NAT-193: in place of cpuload=1000 and of NAT-174\'s %s)' % (NEW_TOKEN, OLD_TOKEN)
    report['nat174_changes']['cmdline_token'] = '%s in place of cpuload=1000 (NAT-193; touch_lat=1 is not set)' % NEW_TOKEN
    report['nat174_changes']['note'] = 'NAT-193 build: the swipe thread is kept; touch_lat=1 is replaced by fbscale=2'
    report['nat185_changes']['note'] = 'NAT-193 build: tag and one token replaced (see nat193_changes); kernel unchanged'
    report['nat193_changes'] = dict(cmdline_bytes=len(cmd.encode()), replaced=OLD_TOKEN, by=NEW_TOKEN, tag=TAG,
                                    kernel=report['nat185_changes']['kernel'],
                                    purpose='2x UI scale under the synthetic swipes: 2.25x fewer pixels for backboardd, against NAT-186')
    report['nat193_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py',)}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
