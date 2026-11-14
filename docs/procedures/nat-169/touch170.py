#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-170: the touch driver's health, poll cost, IRQ gate and GPIO access cost from a kernel text dump (nat-097 kl_reader2 output).

Uses docs/procedures/nat-168/touch168.py for the ID reads, the event thread and the 1000-poll slope, and adds:
  - the gate counters of NAT-169's summary line: "...; irq line low in L polls; skipped S, high-line reads H with E events";
  - the device ID read time: the stamp gap from "spi9 map" to "poll 1 device id" (both runs print the same line before it).
Kernel stamps print microseconds without padding, and the fraction can exceed 999999 (122.1002373 follows 122.944911): a stamp is
seconds + fraction / 1e6.

Verdicts (registered in decision 0069 before the run):
  T-fail   no "device id: ok" or no "event thread started"
  G-fail   E > 0: a read on a high line found events, so the gate would miss events (the line is not level-low while pending)
  P1 / P-part / P0   as touch168: slope <= 12.0 / between / >= 17.0 s per 1000 polls
The read/write split of the GPIO access cost is an estimate, assuming 88 bits per device ID read and per bit 4 loads + 3 stores
(NAT-168's driver) against 1 load + 3 stores (NAT-169's): load = (T_168 - T_170) / (3 * 88), store = (T_170 / 88 - load) / 3.

  python3 -B docs/procedures/nat-169/touch170.py KERNEL_TEXT [--json OUT] [--ref-id-ms 5.241]
"""
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('touch168', HERE.parent / 'nat-168/touch168.py')
t168 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t168)

GATE = re.compile(r'events after (\d+) polls: .*; irq line low in (\d+) polls; skipped (\d+), high-line reads (\d+) with (\d+) events')
STAMP = r'\[\s*(\d+)\.(\d+)\]: '
MAP = re.compile(STAMP + r'e1s-touch: spi9 map')
ID1 = re.compile(STAMP + r'e1s-touch: poll 1 device id')
REF_ID_MS = 5.241                     # NAT-168, same line pair


def us(m):
    return int(m.group(1)) * 1000000 + int(m.group(2))


def analyse(text, ref_id_ms=REF_ID_MS):
    out = t168.analyse(text)
    gates = [tuple(int(x) for x in m.groups()) for m in GATE.finditer(text)]
    if gates:
        polls, low, skipped, high, events = gates[-1]
        out.update(gate=dict(polls=polls, irq_low=low, skipped=skipped, high_reads=high, high_events=events))
    a, b = MAP.search(text), ID1.search(text)
    if a and b:
        t = (us(b) - us(a)) / 1000.0
        out['device_id_read_ms'] = round(t, 3)
        load = (ref_id_ms - t) / (3 * 88) * 1000.0
        out['gpio_cost_estimate_us'] = dict(load=round(load, 2), store=round((t * 1000.0 / 88 - load) / 3, 2), ref_id_ms=ref_id_ms)
    if out['verdict'] != 'T-fail' and out.get('gate', {}).get('high_events', 0) > 0:
        out['verdict'] = 'G-fail'
    return out


def main():
    ref = float(sys.argv[sys.argv.index('--ref-id-ms') + 1]) if '--ref-id-ms' in sys.argv else REF_ID_MS
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read(), ref)
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
