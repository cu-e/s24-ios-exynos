#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-181: did run-wise memcpy (NAT-180, scT) shorten the framebuffer driver's time per frame? Reads a kernel text dump (nat-097
kl_reader2 output). The driver time is MiniIOMobileFramebuffer's own "us each in the driver" over the steady 5 s windows (NAT-159's
frames159 rule); the swipe copy and swap intervals are NAT-175's swipe175 on the `tl:` tail. Kernel counts, not a camera.

Verdicts (registered in docs/procedures/nat-180/README.md before the run; NAT-175/177 baseline: driver median 8.91 ms, copy 8.77 ms):
  K-none  no steady statistics window -> inconclusive
  K2      driver median <= 5.0 ms
  K1      driver median < 8.0 ms
  K0      driver median >= 8.0 ms: no proven gain
The swipe verdict (F60/F30/F-low/S-*) is reported beside it; it is not part of K.

  python3 -B docs/procedures/nat-180/fbcopy181.py KERNEL_TEXT [--json OUT]
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = dict(driver_ms_median=8.914, swipe_copy_ms_median=8.77, swipe_swap_interval_ms_median=21.0, source='NAT-177')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


frames159 = _load('nat181_frames159', HERE.parent / 'nat-159/frames159.py')
swipe175 = _load('nat181_swipe175', HERE.parent / 'nat-174/swipe175.py')


def verdict(driver_ms):
    if driver_ms is None:
        return 'K-none'
    if driver_ms <= 5.0:
        return 'K2'
    if driver_ms < 8.0:
        return 'K1'
    return 'K0'


def analyse(text):
    f, _ = frames159.summarize(text)
    s = swipe175.analyse(text)
    d = f.get('driver_ms_median')
    copy = (s.get('swipe_copy') or {}).get('median')
    gap = (s.get('swipe_swap_interval') or {}).get('median')
    return dict(verdict=verdict(d), driver_ms_median=d, driver_ms_min=f.get('driver_ms_min'), driver_ms_max=f.get('driver_ms_max'),
                steady_windows=f.get('steady_windows'), fps_median=f.get('fps_median'),
                swipe_verdict=s.get('verdict'), swipe_copy_ms_median=copy, swipe_swap_interval_ms_median=gap,
                swipe_fps_median=s.get('swipe_fps_median'), swipe_fps_max=s.get('swipe_fps_max'),
                driver_gain_ms=round(BASELINE['driver_ms_median'] - d, 3) if d is not None else None,
                copy_gain_ms=round(BASELINE['swipe_copy_ms_median'] - copy, 3) if copy is not None else None, baseline=BASELINE)


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
