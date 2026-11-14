#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-173: decode the e1s-cpuclk lines of a kernel text dump (nat-097 kl_reader2 output; NAT-172 e1s_acpm.patch):
  e1s-cpuclk: before: pll con3 0xV = K kHz; R adds/us; mbox INTMR1 0xM
  e1s-cpuclk: FREQ_REQ cluster 0 T kHz on channel 0: error E, reply W0 W1 W2 W3
  e1s-cpuclk: after: pll con3 0xV = K kHz; R adds/us
  e1s-cpuclk: <reason>; no request     (or "off", "cannot map", "not a stock cluster-0 level")
R is dependent 64-bit adds per microsecond (best of three runs of 8 Mi), about MHz on an in-order core (inference: 1-cycle add).

Verdicts (registered in decision 0070 before the run):
  inconclusive  no "e1s-cpuclk: before" line
  C-skip        no request was sent (the logged reason is reported)
  C-err         the request returned a non-zero error
  C-same        sent with error 0, but the after-PLL equals the before-PLL (the firmware did not move the clock)
  C2            after-PLL within 1% of the target and the add rate at least 1.5x the before rate
  C1            any other change (PLL moved but not to the target, or the rate disagrees with the PLL)

  python3 -B docs/procedures/nat-172/cpuclk173.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import sys

BEFORE = re.compile(r'e1s-cpuclk: before: pll con3 (0x[0-9a-f]+) = (\d+) kHz; (\d+) adds/us; mbox INTMR1 (0x[0-9a-f]+)')
REQ = re.compile(r'e1s-cpuclk: FREQ_REQ cluster 0 (\d+) kHz on channel 0: error (-?\d+), reply ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+) ([0-9a-f]+)')
AFTER = re.compile(r'e1s-cpuclk: after: pll con3 (0x[0-9a-f]+) = (\d+) kHz; (\d+) adds/us')
NOREQ = re.compile(r'e1s-cpuclk: (.*?)(?:; no request| \(e1scpuclk=0\))')


def decode(con3):
    v = int(con3, 16)
    return dict(enable=bool(v >> 31), m=(v >> 16) & 0x3ff, p=(v >> 8) & 0x3f, s=v & 7)


def analyse(text):
    b, q, a, n = BEFORE.search(text), REQ.search(text), AFTER.search(text), NOREQ.search(text)
    out = {}
    if not b:
        out['verdict'] = 'inconclusive'
        return out
    out['before'] = dict(con3=b.group(1), fields=decode(b.group(1)), khz=int(b.group(2)), adds_per_us=int(b.group(3)), intmr1=b.group(4))
    if not q:
        out['verdict'] = 'C-skip'
        out['reason'] = n.group(1) if n else None
        return out
    target, err = int(q.group(1)), int(q.group(2))
    out['request'] = dict(target_khz=target, error=err, reply=[q.group(i) for i in range(3, 7)])
    if a:
        out['after'] = dict(con3=a.group(1), fields=decode(a.group(1)), khz=int(a.group(2)), adds_per_us=int(a.group(3)))
    if err != 0:
        out['verdict'] = 'C-err'
    elif not a or a.group(1) == b.group(1):
        out['verdict'] = 'C-same'
    elif out['after']['khz'] >= target - target // 100 and out['after']['adds_per_us'] * 2 >= out['before']['adds_per_us'] * 3:
        out['verdict'] = 'C2'
    else:
        out['verdict'] = 'C1'
    if a and out['before']['adds_per_us']:
        out['rate_ratio'] = round(out['after']['adds_per_us'] / out['before']['adds_per_us'], 3)
    return out


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
