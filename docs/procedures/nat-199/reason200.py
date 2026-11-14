#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-200: why does SpringBoard abort under SMP? Reads a kernel text dump (nat-097 kl_reader2 output) of the e2r image (NAT-199).

Lines used:
  userabort: NAME[PID] aborts, shared cache slide 0xS; called from: ...   (existing hook)
  userabort: reason: Terminating app due to uncaught exception 'N', reason: '...'   (NAT-199)
  userabort: throw stack: (0x... 0x...)                                     (NAT-199)
  userabort: reason scan: K line(s) in B bytes of the loader log, D distinct said

Verdicts (registered in docs/procedures/nat-199/README.md before NAT-200), first match:
  R-no-abort       no `userabort:` abort line                          (nothing to explain in this run)
  R-none           abort lines but no `reason scan` line               -> inconclusive (the scan did not run or its line was lost)
  R-reason         at least one `userabort: reason:` line              (the text, its exception name, and the throw stack)
  R-abort-no-text  scan lines, no reason line                          (the abort is not an uncaught exception's, or its text
                                                                        never reached the console)

With --table (the host's nat-189 dsc-table.pickle) the throw-stack addresses are unslid with the SpringBoard slide and looked up.

  python3 -B docs/procedures/nat-199/reason200.py KERNEL_TEXT [--json OUT] [--table PICKLE]
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RE_ABORT = re.compile(r'userabort: (\S+)\[(\d+)\] aborts, shared cache slide (0x[0-9a-f]+); called from:([0-9a-fx ]*)')
RE_REASON = re.compile(r'userabort: reason: (.*)')
RE_STACK = re.compile(r'userabort: throw stack: \(([0-9a-fx ]*)\)?')
RE_SCAN = re.compile(r'userabort: reason scan: (\d+) line\(s\) in (\d+) bytes of the loader log, (\d+) distinct said')
RE_NAME = re.compile(r"uncaught exception '([^']*)', reason: '(.*)'?")


def analyse(text):
    aborts = [dict(name=m[1], pid=int(m[2]), slide=m[3], frames=m[4].split()) for m in RE_ABORT.finditer(text)]
    reasons = []
    lines = text.splitlines()
    for i, l in enumerate(lines):
        m = RE_REASON.search(l)
        if not m:
            continue
        r = dict(text=m[1])
        n = RE_NAME.search(m[1])
        if n:
            r.update(exception=n[1], reason=n[2].rstrip("'"))
        for nxt in lines[i + 1:i + 3]:
            s = RE_STACK.search(nxt)
            if s:
                r['throw_stack'] = s[1].split()
                break
        reasons.append(r)
    scans = [dict(lines=int(m[1]), bytes=int(m[2]), distinct=int(m[3])) for m in RE_SCAN.finditer(text)]
    if not aborts:
        verdict = 'R-no-abort'
    elif not scans:
        verdict = 'R-none'
    elif reasons:
        verdict = 'R-reason'
    else:
        verdict = 'R-abort-no-text'
    return dict(verdict=verdict, aborts=aborts, reasons=reasons, scans=scans)


def symbolise(r, table):
    slides = {a['slide'] for a in r['aborts'] if a['name'] == 'SpringBoard'}
    if len(slides) != 1:
        return
    slide = int(slides.pop(), 16)
    for x in r['reasons']:
        addrs = ['0x%x' % (int(a, 16) - slide) for a in x.get('throw_stack', []) if a.startswith('0x')]
        if not addrs:
            continue
        out = subprocess.run([sys.executable, '-B', str(HERE.parent / 'nat-189/dscsym.py'), '--table', table, 'lookup', *addrs],
                             capture_output=True, text=True)
        x['throw_stack_symbols'] = out.stdout.splitlines()


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    if '--table' in sys.argv:
        symbolise(r, sys.argv[sys.argv.index('--table') + 1])
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
