#!/usr/bin/env python3
"""NAT-142 analyser (rule fixed by NAT-141 before the run): every NAT-140 verdict (nat-139/analyze140.py), plus the STM start
sequence and the polled events.

    analyze142.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON --out OUT_JSON

start (first match):
  S0-no-thread       no `e1s-touch: event thread started` line
  S1-not-ready       thread started, `start: sense on (ready no, ...)`
  S2-no-scan-echo    ready yes, scan echo no
  S3-sense-on        ready yes, scan echo yes
events:
  E0-no-coordinates  no `e1s-touch: coord N:` line and every summary says coord 0
  E1-coordinates     at least one coordinate event from the controller (count, presses, releases, first/last x,y reported)
reader: R1-open when `redwood-touch: opened by pid N` is in the text (iOS opened /dev/hakios-touch), else R0.
physical_input: `controller-events` when E1 (a finger produced coordinate events in the XNU kernel and they were posted to the
node); whether iOS acted on them needs a UI change, which this analyser does not claim.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat141_analyze140', HERE.parent / 'nat-139/analyze140.py')
A140 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A140)

RE_SENSE = re.compile(r'e1s-touch: start: sense on \(ready (yes|no), scan echo (yes|no)\)')
RE_COORD = re.compile(r'e1s-touch: coord (\d+): finger (\d+) action (\d) x (\d+) y (\d+)')
RE_SUM = re.compile(r'e1s-touch: events after (\d+) polls: coord (\d+) \(press (\d+) release (\d+)\) other (\d+); irq line low in (\d+) polls')
RE_OPEN = re.compile(r'redwood-touch: opened by pid (\d+)')


def classify(text, pixels):
    out = A140.classify(text, pixels)
    m = RE_SENSE.search(text)
    if 'e1s-touch: event thread started' not in text:
        out['start'] = 'S0-no-thread'
    elif not m:
        out['start'] = 'S0-no-thread'
        out['reasons'].append('thread started but no sense-on line')
    elif m[1] == 'no':
        out['start'] = 'S1-not-ready'
    elif m[2] == 'no':
        out['start'] = 'S2-no-scan-echo'
    else:
        out['start'] = 'S3-sense-on'
    coords = [dict(n=int(c[0]), finger=int(c[1]), action=int(c[2]), x=int(c[3]), y=int(c[4])) for c in RE_COORD.findall(text)]
    sums = [dict(polls=int(s[0]), coord=int(s[1]), press=int(s[2]), release=int(s[3]), other=int(s[4]), irq_low=int(s[5]))
            for s in RE_SUM.findall(text)]
    out['coord_lines'] = coords
    out['summaries'] = sums
    total = max([s['coord'] for s in sums] + [c['n'] for c in coords] + [0])
    out['coord_total'] = total
    out['events'] = 'E1-coordinates' if total > 0 else 'E0-no-coordinates'
    o = RE_OPEN.search(text)
    out['reader'] = 'R1-open pid %s' % o[1] if o else 'R0-not-open'
    out['physical_input'] = 'controller-events' if total > 0 else 'not-established'
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kernel-text', required=True, type=Path)
    ap.add_argument('--pixels', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    r = classify(a.kernel_text.read_text(errors='replace'), json.loads(a.pixels.read_text()))
    a.out.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('window', 'display', 'power', 'touch', 'start', 'events', 'coord_total', 'reader',
                                         'log', 'physical_input')}))


if __name__ == '__main__':
    main()
