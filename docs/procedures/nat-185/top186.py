#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-186: where the only running core's time goes during the synthetic swipes. Reads a kernel text dump (nat-097 kl_reader2 output)
for scV's `e1s-top:` lines (NAT-185 sampler in bsd/e1s_display.o: every 5 s from 200 to 380 s, each process's user+system time
since the last sample, the span, the sum, the kernel's share and cpu0's idle counter). Kernel accounting, not a profiler: a process
that exited inside a span is missing from it, the running thread's current slice may not be folded in yet.

Windows ending in SWIPE_FROM..SWIPE_UNTIL are the swipe phase (the swipe thread runs 215-375 s).

Verdicts (registered in docs/procedures/nat-185/README.md before the run), on the median busy share (sum / span) of the swipe windows:
  U-none  no e1s-top report line                                    -> inconclusive
  U-sat   median >= 0.90: the core is full; rendering is CPU-bound
  U-mid   0.70 <= median < 0.90
  U-free  median < 0.70: the core has time left; frames are paced late, not starved
Also reported: the processes with the largest total over the swipe windows and their shares, the kernel's share, and whether
cpu0's idle counter agrees with span - busy (|idle0 + busy - span| <= 10 % of span in most windows).

  python3 -B docs/procedures/nat-185/top186.py KERNEL_TEXT [--json OUT]
"""
import collections
import json
import re
import statistics
import sys

SPAN = re.compile(r'e1s-top: (\d+) s span (\d+) us busy (\d+) us kernel (\d+) us idle0 (\d+) us procs (\d+) lost (\d+)')
TOP = re.compile(r'e1s-top: (\d+) s top((?: \S+\[-?\d+\] \d+)*)')
ENTRY = re.compile(r'(\S+)\[(-?\d+)\] (\d+)')
SWIPE_FROM, SWIPE_UNTIL = 220, 375


def verdict(median):
    if median is None:
        return 'U-none'
    if median >= 0.90:
        return 'U-sat'
    if median >= 0.70:
        return 'U-mid'
    return 'U-free'


def analyse(text):
    spans = {int(m[1]): dict(span=int(m[2]), busy=int(m[3]), kernel=int(m[4]), idle0=int(m[5]), procs=int(m[6]), lost=int(m[7]))
             for m in SPAN.finditer(text)}
    tops = {int(m[1]): [(n, int(p), int(us)) for n, p, us in ENTRY.findall(m[2])] for m in TOP.finditer(text)}
    if not spans:
        return dict(verdict='U-none', windows=0)
    swipe = sorted(t for t in spans if SWIPE_FROM <= t <= SWIPE_UNTIL and spans[t]['span'] > 0)
    shares = [spans[t]['busy'] / spans[t]['span'] for t in swipe]
    med = statistics.median(shares) if shares else None
    totals = collections.Counter()
    names = {}
    span_sum = sum(spans[t]['span'] for t in swipe)
    for t in swipe:
        for n, p, us in tops.get(t, []):
            totals[p] += us
            names[p] = n
    agree = [abs(spans[t]['idle0'] + spans[t]['busy'] - spans[t]['span']) <= 0.1 * spans[t]['span'] for t in swipe]
    out = dict(verdict=verdict(med), windows=len(spans), swipe_windows=len(swipe),
               busy_share_median=round(med, 3) if med is not None else None,
               busy_share_min=round(min(shares), 3) if shares else None, busy_share_max=round(max(shares), 3) if shares else None,
               kernel_share_median=round(statistics.median(spans[t]['kernel'] / spans[t]['span'] for t in swipe), 3) if swipe else None,
               idle0_share_median=round(statistics.median(spans[t]['idle0'] / spans[t]['span'] for t in swipe), 3) if swipe else None,
               idle_counter_agrees=(sum(agree) > len(agree) / 2) if agree else None,
               lost_max=max(s['lost'] for s in spans.values()),
               top_over_swipes=[dict(name=names[p], pid=p, us=us, share=round(us / span_sum, 3) if span_sum else None)
                                for p, us in totals.most_common(10)],
               per_window=[dict(t=t, share=round(spans[t]['busy'] / spans[t]['span'], 3), top=tops.get(t, [])[:3]) for t in swipe])
    return out


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
