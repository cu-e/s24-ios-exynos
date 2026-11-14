#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-188: the render server's CPU per frame. Reads a kernel text dump (nat-097 kl_reader2 output): scV/scW's `e1s-top:` spans
(NAT-185: backboardd's user+system time per 5 s) and MiniIOMobileFramebuffer's 5 s frame counts. For each e1s-top span ending in
the swipe phase (220-375 s), backboardd's time is divided by the frames the driver counted in windows stamped inside that span.
Also: the share of 60-Hz intervals in the driver's histograms over 218-378 s. Kernel counts, not a camera or a profiler.

Verdicts (registered in docs/procedures/nat-187/README.md before NAT-188), on the median backboardd ms per frame against NAT-186's
same figure (BASELINE_MS = 67.95 ms, this script on NAT-186's log):
  B-none  no span with frames  -> inconclusive
  B2      median <= 0.5 x baseline
  B1      median <= 0.8 x baseline
  B0      otherwise: no clear gain

  python3 -B docs/procedures/nat-187/bbd188.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import statistics
import sys

SPAN = re.compile(r'e1s-top: (\d+) s span (\d+) us busy (\d+) us kernel (\d+) us')
TOP = re.compile(r'e1s-top: (\d+) s top(.*)')
BBD = re.compile(r'backboardd\[\d+\] (\d+)')
FR = re.compile(r'\[\s*([0-9.]+)\]: MiniIOMobileFramebuffer: (\d+) frames in (\d+) ms')
HIST = re.compile(r'\[\s*([0-9.]+)\]: MiniIOMobileFramebuffer: from one frame to the next: (\d+) times under 10 ms, (\d+) under 18, '
                  r'(\d+) under 26, (\d+) under 35, (\d+) longer')
FROM, UNTIL = 220, 375
BASELINE_MS = 67.95     # this script on NAT-186's kernel text (artifacts/nat-186/analysis/kernel-text.txt), registered before NAT-188


def stamp(s):
    return float(s.split('.')[0])


def verdict(med, base):
    if med is None:
        return 'B-none'
    if base and med <= 0.5 * base:
        return 'B2'
    if base and med <= 0.8 * base:
        return 'B1'
    return 'B0'


def analyse(text, base=None):
    spans = {int(m[1]): int(m[2]) for m in SPAN.finditer(text)}
    bbd = {}
    for m in TOP.finditer(text):
        b = BBD.search(m[2])
        bbd[int(m[1])] = int(b[1]) if b else 0
    frames = [(stamp(m[1]), int(m[2])) for m in FR.finditer(text)]
    rows = []
    for t in sorted(spans):
        if not FROM <= t <= UNTIL or t not in bbd:
            continue
        n = sum(f for s, f in frames if t - spans[t] / 1e6 < s <= t)
        if n:
            rows.append(dict(t=t, backboardd_ms=round(bbd[t] / 1000, 1), frames=n, ms_per_frame=round(bbd[t] / 1000 / n, 2),
                             share=round(bbd[t] / spans[t], 3)))
    h = [0] * 5
    for m in HIST.finditer(text):
        if 218 <= stamp(m[1]) <= 378:
            for i in range(5):
                h[i] += int(m[i + 2])
    med = statistics.median(r['ms_per_frame'] for r in rows) if rows else None
    return dict(verdict=verdict(med, base), baseline_ms_per_frame=base, ms_per_frame_median=med,
                ms_per_frame_p25=round(statistics.quantiles([r['ms_per_frame'] for r in rows], n=4)[0], 2) if len(rows) >= 4 else None,
                backboardd_share_median=round(statistics.median(r['share'] for r in rows), 3) if rows else None,
                spans_with_frames=len(rows), intervals=sum(h), share_60hz=round((h[0] + h[1]) / sum(h), 3) if sum(h) else None,
                rows=rows)


def main():
    base = BASELINE_MS
    if '--baseline' in sys.argv:
        base = float(sys.argv[sys.argv.index('--baseline') + 1])
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read(), base)
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
