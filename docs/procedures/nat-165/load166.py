#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-165/166: per-core busy share from the cpuload lines (bsd/dev/redwood_cpufreq.c load_thread, references/s24-port c8860dec:
"tl: u at US CORE:PCT ..." every cpuload= ms; CORE is (MPIDR >> 8) & 0xff, PCT the share of the interval the core was not idle,
interrupts included), set against MiniIOMobileFramebuffer's steady windows (docs/procedures/nat-159/frames159.py) over the same span.
Kernel timestamps on both; not a profiler.

  python3 -B docs/procedures/nat-165/load166.py KERNEL_TEXT [--json OUT]
"""
import importlib.util
import json
import re
import statistics
import sys
from pathlib import Path

U = re.compile(r'tl: u at (\d+)((?: \d+:\d+)*)')
spec = importlib.util.spec_from_file_location('frames159', Path(__file__).resolve().parent.parent / 'nat-159/frames159.py')
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)


def parse(text):
    return [(int(m.group(1)) / 1e6, {int(a): int(b) for a, b in (x.split(':') for x in m.group(2).split())}) for m in U.finditer(text)]


def analyse(text):
    lines = parse(text)
    summary, steady = F.summarize(text)
    out = dict(load_lines=len(lines), frames=summary)
    if not lines:
        out['verdict'] = 'no-load-lines'
        return out
    cores = sorted({c for _, d in lines for c in d})
    out['cores'] = cores
    out['span_s'] = [round(lines[0][0], 1), round(lines[-1][0], 1)]
    if steady:
        lo = steady[0]['t'] - steady[0]['ms'] / 1000.0
        hi = steady[-1]['t'] + 1
        sel = [d for t, d in lines if lo <= t <= hi]
        out['steady_span_s'] = [round(lo, 1), round(hi, 1)]
        out['steady_samples'] = len(sel)
        out['steady_busy'] = {c: dict(median=statistics.median(d.get(c, 0) for d in sel), min=min(d.get(c, 0) for d in sel),
                                      max=max(d.get(c, 0) for d in sel)) for c in cores} if sel else None
        if sel:
            # the boot CPU (MPIDR Aff1 0) is the one running core (NAT-153/159: cpu 1-9 started but off); a core that never runs
            # accumulates no idle time and would read as busy, so only core 0 is graded
            if 0 in cores:
                m = out['steady_busy'][0]['median']
                out['verdict'] = 'L2-saturated' if m >= 90 else 'L1-busy' if m >= 60 else 'L0-headroom'
            else:
                out['verdict'] = 'no-core-0'
            out['graded_core'] = 0
        else:
            out['verdict'] = 'no-load-lines-in-steady-windows'
    else:
        out['verdict'] = 'no-steady-windows'
    return out


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(json.dumps({k: v for k, v in r.items() if k != 'frames'}))


if __name__ == '__main__':
    main()
