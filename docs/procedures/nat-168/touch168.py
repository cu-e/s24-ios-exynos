#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-168: touch driver health and poll cost from a kernel text dump (nat-097 kl_reader2 output).

Lines used (e1s_touch, NAT-143 patch):
  e1s-touch: poll K device id: ok (...)            the chip answered the ID read over bit-banged SPI
  e1s-touch: event thread started (...)            the poll thread runs
  e1s-touch: events after N polls: ...             every 1000 polls

The stamp fraction is not zero padded (frames159.stamp), so only the seconds part is used; the period per 1000 polls is the
least-squares slope over all marks (error well under 0.1 s for 10+ marks), plus the per-interval seconds differences.

Verdicts (registered in decision 0068 before the run):
  T-fail   no "device id: ok" or no "event thread started": the chip does not work at this half-bit
  P1       slope <= 12.0 s per 1000 polls (sleep 10 s + < 2 ms per poll)
  P-part   12.0 < slope < 17.0
  P0       slope >= 17.0 (no gain vs NAT-166's 19.3)

  python3 -B docs/procedures/nat-168/touch168.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import sys

ID_OK = re.compile(r'e1s-touch: poll (\d+) device id: ok')
ID_ANY = re.compile(r'e1s-touch: poll (\d+) device id: (.*)')
STARTED = re.compile(r'e1s-touch: event thread started')
MARK = re.compile(r'\[\s*(\d+)\.\d*\]: e1s-touch: events after (\d+) polls: coord (\d+)')


def slope(pts):
    n = len(pts)
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    sxx = sum((x - mx) ** 2 for x, _ in pts)
    return sum((x - mx) * (y - my) for x, y in pts) / sxx


def analyse(text):
    ids = [m.group(2).strip() for m in ID_ANY.finditer(text)]
    ok = len(ID_OK.findall(text))
    marks = [(int(m.group(2)), int(m.group(1)), int(m.group(3))) for m in MARK.finditer(text)]
    out = dict(id_reads=len(ids), id_ok=ok, id_lines=ids[:6], event_thread_started=bool(STARTED.search(text)), marks=len(marks))
    if ok == 0 or not out['event_thread_started']:
        out['verdict'] = 'T-fail'
        return out
    if len(marks) < 3:
        out['verdict'] = 'inconclusive'
        return out
    s = slope([(n / 1000.0, t) for n, t, _ in marks])
    out.update(seconds_per_1000=round(s, 2), first_mark_s=marks[0][1], last_mark_s=marks[-1][1],
               intervals_s=[b[1] - a[1] for a, b in zip(marks, marks[1:])], coord_events=marks[-1][2],
               busy_ms_per_poll_est=round(s - 10.0, 2))
    out['verdict'] = 'P1' if s <= 12.0 else ('P0' if s >= 17.0 else 'P-part')
    return out


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
