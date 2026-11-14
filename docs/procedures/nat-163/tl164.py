#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-163/164: decode the `touch_lat=1` timing lines of a kernel text dump (nat-097 kl_reader2 output). Formats, references/s24-port
c8860dec:
  tl: s ID at US                              MiniIOMobileFramebuffer.cpp:873   a swap handed over (SwapEnd)
  tl: v ID ready US shown US done US          MiniIOMobileFramebuffer.cpp:1051  a frame: GPU done / its beat came / pixels in the panel
  tl: p TYPE FINGER X Y at US                 bsd/dev/redwood_input.c:124       a touch sample posted to userland
  tl: u at US CPU:NN ...                      bsd/dev/redwood_cpufreq.c:272     each core's busy share (if that driver runs)
US are microseconds of mach_absolute_time. Kernel counts, not a camera: "done" is when the pixels are in the panel's memory, not
when the panel shows them.

  python3 -B docs/procedures/nat-163/tl164.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import statistics
import sys

S = re.compile(r'tl: s (\d+) at (\d+)')
V = re.compile(r'tl: v (\d+) ready (\d+) shown (\d+) done (\d+)')
P = re.compile(r'tl: p (\d+) (\d+) (\d+) (\d+) at (\d+)')
U = re.compile(r'tl: u at (\d+)((?: \d+:\d+)+)')
TOUCH_GAP_US = 1000000      # a swap within 1 s of a touch sample counts as "under touch"


def q(xs, f):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(f * len(xs)))] if xs else None


def stats_ms(xs):
    if not xs:
        return None
    return dict(n=len(xs), median=round(statistics.median(xs) / 1000.0, 2), p10=round(q(xs, 0.1) / 1000.0, 2),
                p90=round(q(xs, 0.9) / 1000.0, 2), min=round(min(xs) / 1000.0, 2), max=round(max(xs) / 1000.0, 2))


def parse(text):
    swaps = [(int(m.group(1)), int(m.group(2))) for m in S.finditer(text)]
    frames = [tuple(int(m.group(i)) for i in range(1, 5)) for m in V.finditer(text)]
    touches = [tuple(int(m.group(i)) for i in range(1, 6)) for m in P.finditer(text)]
    load = [(int(m.group(1)), {int(a): int(b) for a, b in (x.split(':') for x in m.group(2).split())}) for m in U.finditer(text)]
    return swaps, frames, touches, load


def analyse(text):
    swaps, frames, touches, load = parse(text)
    tt = sorted(t[4] for t in touches)

    def touched(at):
        import bisect
        i = bisect.bisect_left(tt, at - TOUCH_GAP_US)
        return i < len(tt) and tt[i] <= at + TOUCH_GAP_US

    swap_at = dict(swaps)
    out = dict(swaps=len(swaps), frames=len(frames), touch_samples=len(touches), load_lines=len(load))
    for name, keep in (('idle', lambda at: not touched(at)), ('touch', touched)):
        sw = [at for _, at in swaps if keep(at)]
        gaps = [b - a for a, b in zip(sw, sw[1:]) if b - a < 2000000]          # a pause of 2 s or more is not pacing
        fr = [f for f in frames if keep(f[1])]
        seg = dict(swaps=len(sw), swap_interval=stats_ms(gaps),
                   beat_wait=stats_ms([f[2] - f[1] for f in fr]),             # ready -> shown (waiting for the driver's beat)
                   copy=stats_ms([f[3] - f[2] for f in fr]),                  # shown -> done (the CPU copy to the panel)
                   swap_to_done=stats_ms([f[3] - swap_at[f[0]] for f in fr if f[0] in swap_at]),
                   share_60hz=round(sum(1 for g in gaps if g <= 18000) / len(gaps), 3) if gaps else None)
        out[name] = seg
    # a touch sample -> the first frame handed over after it -> its pixels in panel memory (an upper bound on the kernel's part)
    lat = []
    done_of = {f[0]: f[3] for f in frames}
    sw_sorted = sorted(swaps, key=lambda s: s[1])
    import bisect
    keys = [s[1] for s in sw_sorted]
    for t in tt:
        i = bisect.bisect_right(keys, t)
        if i < len(sw_sorted) and sw_sorted[i][0] in done_of and sw_sorted[i][1] - t < 500000:
            lat.append(done_of[sw_sorted[i][0]] - t)
    out['touch_to_panel'] = stats_ms(lat)
    if load:
        cores = sorted({c for _, d in load for c in d})
        out['core_busy_median'] = {c: statistics.median(d.get(c, 0) for _, d in load) for c in cores}
    return out


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
