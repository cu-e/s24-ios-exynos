#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-161: per-process CPU time between the first two `ps` snapshots in a kernel text dump (the userland heartbeat prints them),
timed by the launchd log lines just before each snapshot, plus the framebuffer driver's time over the same span from frames159.
Kernel/userland counts, not a profiler: ps TIME includes each process's kernel time; the driver's presenter is a kernel thread.

ERRATUM (2026-11-14, after NAT-164): the snapshot times are NOT reliable. The console part of the dump has no kernel timestamps; the
launchd line before a snapshot can be far older than it, and the heartbeat's own `ps` takes 4-27 s to run on the phone
("SWEET hb: n=N ps pid=P status=0 ms=M"), so per-process TIME is sampled somewhere inside that window. busy_share is therefore
reported only when every ps in the pair ran in under 1 s; otherwise it is null with the reason. The per-process deltas stay as
relative indications only.

  python3 -B docs/procedures/nat-161/cpu161.py KERNEL_TEXT [--json OUT]
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

HEAD = 'PID TTY           TIME CMD'
spec = importlib.util.spec_from_file_location('frames159', Path(__file__).resolve().parent.parent / 'nat-159/frames159.py')
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)


def snapshots(lines):
    out = []
    for i, l in enumerate(lines):
        if l.strip() != HEAD:
            continue
        procs = {}
        for x in lines[i + 1:i + 120]:
            m = re.match(r'\s*(\d+) \?\?\s+(\d+):(\d+\.\d+) (.*)', x)
            if not m:
                break
            procs['%s %s' % (m.group(1), m.group(4).strip()[:60])] = int(m.group(2)) * 60 + float(m.group(3))
        t = None
        for x in reversed(lines[:i]):
            m = re.search(r'1970-01-01 (\d\d):(\d\d):(\d\d\.\d+)', x)
            if m:
                t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
                break
        out.append(dict(t=t, procs=procs))
    return out


def analyse(text):
    lines = text.splitlines()
    s = snapshots(lines)
    if len(s) < 2 or s[0]['t'] is None or s[1]['t'] is None:
        return dict(snapshots=len(s), verdict='no-span')
    a, b = s[0], s[1]
    ps_ms = [int(m.group(1)) for m in re.finditer(r'SWEET hb: n=\d+ ps pid=\d+ status=\d+ ms=(\d+)', text)]
    span = b['t'] - a['t']
    delta = sorted(((round(v - a['procs'].get(k, 0.0), 2), k) for k, v in b['procs'].items()), reverse=True)
    procs = sum(d for d, _ in delta)
    wins, _, _ = F.parse(text)
    # driver time inside the span: windows ending inside it, weighted by the part of each 5 s window in the span
    drv = 0.0
    for w in wins:
        lo, hi = w['t'] - w['ms'] / 1000.0, w['t']
        part = max(0.0, min(hi, b['t']) - max(lo, a['t'])) / (w['ms'] / 1000.0) if w['ms'] else 0
        drv += part * w['frames'] * w['driver_us'] / 1e6
    return dict(snapshots=len(s), span_s=round(span, 2), from_s=round(a['t'], 2), to_s=round(b['t'], 2),
                processes_cpu_s=round(procs, 2), driver_cpu_s=round(drv, 2),
                ps_run_ms=ps_ms[:2],
                busy_share=round((procs + drv) / span, 3) if ps_ms[:2] and max(ps_ms[:2]) < 1000 else None,
                busy_share_unreliable_reason=None if ps_ms[:2] and max(ps_ms[:2]) < 1000 else
                'snapshot times unknown to within the ps run time (%s ms) and the launchd-line offset' % ps_ms[:2],
                raw_share_not_a_measurement=round((procs + drv) / span, 3), top=[dict(cpu_s=d, proc=k) for d, k in delta[:8]],
                note='single running core; time-stamp bases (launchd wall clock vs kernel seconds) assumed equal: both start near boot')


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(json.dumps(r, indent=1) + '\n')
    print(json.dumps(r))


if __name__ == '__main__':
    main()
