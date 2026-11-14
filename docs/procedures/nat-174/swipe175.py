#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-175: frame capacity during the synthetic home-screen swipes of scR (NAT-174 kernel, touch_lat=1). Reads a kernel text dump
(nat-097 kl_reader2 output) and uses NAT-163's tl164 parser for `tl: s` (swap handed over), `tl: v` (frame shown/done) and `tl: p`
(posted touch sample). A swipe is a DOWN (type 1) of finger 9; its window is [DOWN, DOWN + WINDOW_US): the 12 x 16 ms moves, the UP and
the page settle. Swaps inside windows are "swipe" swaps, swaps at least GUARD_US away from any touch sample are "idle".
Kernel counts, not a camera: a swap is a frame userland handed over, "done" is pixels in panel memory, not light from the panel.

Verdicts (registered in docs/procedures/nat-174/README.md before the run):
  S-none   no finger-9 DOWN inside the delivered log tail (thread did not run, or the tail does not reach the swipes) -> inconclusive
  S-same   swipe swap-interval median within 10% of the idle one: no animation proven (gesture ignored?) -> inconclusive
  F60      swipe swap-interval median <= 18 ms
  F30      <= 36 ms
  F-low    slower
Real-finger samples (finger != 9) are counted and reported; they do not change the verdict but mark the run as touched.

  python3 -B docs/procedures/nat-174/swipe175.py KERNEL_TEXT [--json OUT]
"""
import bisect
import importlib.util
import json
import re
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat174_tl164', HERE.parent / 'nat-163/tl164.py')
tl164 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tl164)

FINGER = 9
WINDOW_US = 1000000
GUARD_US = 1000000
MAX_GAP_US = 200000             # gaps longer than this inside a window are pauses, not frame pacing
SWIPE = re.compile(r'e1s-swipe: (start|done)[^\n]*')


def verdict(swipe_med, idle_med, downs):
    if downs == 0 or swipe_med is None:
        return 'S-none'
    if idle_med is not None and abs(swipe_med - idle_med) <= 0.1 * idle_med:
        return 'S-same'
    if swipe_med <= 18.0:
        return 'F60'
    if swipe_med <= 36.0:
        return 'F30'
    return 'F-low'


def analyse(text):
    swaps, frames, touches, _ = tl164.parse(text)
    stamps = [at for _, at in swaps] + [t[4] for t in touches] + [f[1] for f in frames]
    if not stamps:
        return dict(verdict='S-none', swaps=0, downs=0, note='no touch_lat lines')
    cover = (min(stamps), max(stamps))
    downs = sorted(t[4] for t in touches if t[1] == FINGER and t[0] == 1)
    ours = [t for t in touches if t[1] == FINGER]
    real = [t for t in touches if t[1] != FINGER]
    all_t = sorted(t[4] for t in touches)
    sw = sorted(at for _, at in swaps)

    def near_touch(at):
        i = bisect.bisect_left(all_t, at - GUARD_US)
        return i < len(all_t) and all_t[i] <= at + GUARD_US

    per, gaps, first = [], [], []
    for d in downs:
        lo, hi = bisect.bisect_left(sw, d), bisect.bisect_left(sw, d + WINDOW_US)
        w = sw[lo:hi]
        g = [b - a for a, b in zip(w, w[1:]) if b - a < MAX_GAP_US]
        gaps += g
        if w:
            first.append(w[0] - d)
        per.append(dict(down_s=round(d / 1e6, 3), swaps=len(w),
                        fps=round((len(w) - 1) * 1e6 / (w[-1] - w[0]), 2) if len(w) >= 3 else None))
    idle = [at for at in sw if not near_touch(at)]
    idle_gaps = [b - a for a, b in zip(idle, idle[1:]) if b - a < 2000000]
    s_ms = tl164.stats_ms(gaps)
    i_ms = tl164.stats_ms(idle_gaps)
    done_of = {f[0]: f for f in frames}
    def in_window(at):
        i = bisect.bisect_right(downs, at) - 1          # the last DOWN at or before this swap
        return i >= 0 and at < downs[i] + WINDOW_US
    swipe_frames = [done_of[i] for i, at in swaps if i in done_of and in_window(at)]
    fps = [p['fps'] for p in per if p['fps'] is not None]
    r = dict(cover_s=[round(cover[0] / 1e6, 3), round(cover[1] / 1e6, 3)], swaps=len(swaps), frames=len(frames),
             downs=len(downs), finger9_samples=len(ours), real_finger_samples=len(real),
             swipe_swap_interval=s_ms, idle_swap_interval=i_ms,
             swipe_share_60hz=round(sum(1 for g in gaps if g <= 18000) / len(gaps), 3) if gaps else None,
             swipe_fps_median=round(statistics.median(fps), 2) if fps else None, swipe_fps_max=max(fps) if fps else None,
             swaps_per_swipe_median=statistics.median([p['swaps'] for p in per]) if per else None,
             down_to_first_swap=tl164.stats_ms(first),
             swipe_copy=tl164.stats_ms([f[3] - f[2] for f in swipe_frames]),
             swipe_beat_wait=tl164.stats_ms([f[2] - f[1] for f in swipe_frames]),
             thread_lines=[m.group(0)[:160] for m in SWIPE.finditer(text)][:4], per_swipe=per)
    r['verdict'] = verdict(s_ms['median'] if s_ms else None, i_ms['median'] if i_ms else None, len(downs))
    return r


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(json.dumps({k: r[k] for k in r if k != 'per_swipe'}))


if __name__ == '__main__':
    main()
