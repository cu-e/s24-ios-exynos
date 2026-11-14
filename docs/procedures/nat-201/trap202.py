#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-202: where does mediaserverd fault? Reads a kernel text dump (nat-097 kl_reader2 output) of the e2s image (NAT-201: e2r with
boot-arg systrace=1, which prints osfmk/arm64/user_exception_trace.c's lines before each user exception is delivered).

Lines used (user_exception_trace.c):
  usertrap: NAME[PID] exception E code 0xC0 0xC1: pc 0xP lr 0xL sp 0xS, shared cache slide 0xD
  usertrap:   xN -> "text"
  usertrap:   called from 0xA

Verdicts (registered in docs/procedures/nat-201/README.md before NAT-202), first match:
  T-none    no `usertrap:` line at all                    -> inconclusive (the trace did not run, or its lines were lost)
  T-other   usertrap lines, none of mediaserverd's        (mediaserverd did not fault through an exception in this run)
  T-media   at least one mediaserverd usertrap line       (its exception, codes, pc/lr, register texts and frames; distinct sites)

With --table (the host's nat-189 dsc-table.pickle) pc, lr and frames are unslid with the trap's own slide and looked up in the shared
cache; an address the cache does not hold is reported with its 16 KiB page offset (the main image slides by whole pages).

  python3 -B docs/procedures/nat-201/trap202.py KERNEL_TEXT [--json OUT] [--table PICKLE]
"""
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RE_TRAP = re.compile(r'usertrap: (\S+)\[(-?\d+)\] exception (\d+) code (0x[0-9a-f]+) (0x[0-9a-f]+): pc (0x[0-9a-f]+) lr (0x[0-9a-f]+) '
                     r'sp (0x[0-9a-f]+), shared cache slide (0x[0-9a-f]+)')
RE_TEXT = re.compile(r'usertrap:   x(\d+) -> "(.*)"')
RE_FRAME = re.compile(r'usertrap:   called from (0x[0-9a-f]+)')
RE_TIME = re.compile(r'^\[\s*(\d+\.\d+)\]')
EXC = {1: 'EXC_BAD_ACCESS', 2: 'EXC_BAD_INSTRUCTION', 3: 'EXC_ARITHMETIC', 6: 'EXC_BREAKPOINT'}


def analyse(text):
    traps = []
    for line in text.splitlines():
        m = RE_TRAP.search(line)
        if m:
            t = RE_TIME.search(line)
            traps.append(dict(name=m[1], pid=int(m[2]), exception=int(m[3]), exception_name=EXC.get(int(m[3]), '?'),
                              code=[m[4], m[5]], pc=m[6], lr=m[7], sp=m[8], slide=m[9], time=float(t[1]) if t else None,
                              texts={}, frames=[]))
            continue
        if not traps:
            continue
        m = RE_TEXT.search(line)
        if m:
            traps[-1]['texts']['x' + m[1]] = m[2]
            continue
        m = RE_FRAME.search(line)
        if m:
            traps[-1]['frames'].append(m[1])
    by = collections.Counter(t['name'] for t in traps)
    media = [t for t in traps if t['name'] == 'mediaserverd']
    # a site is the pc and lr less the shared cache slide (one per boot, the same in every process), so respawns group together; an
    # address in the main image keeps its 16 KiB page offset, as the slide is page-aligned
    sites = collections.Counter((t['exception_name'], t['code'][0], '0x%x' % (int(t['pc'], 16) - int(t['slide'], 16)),
                                 '0x%x' % (int(t['lr'], 16) - int(t['slide'], 16))) for t in media)
    if not traps:
        verdict = 'T-none'
    elif not media:
        verdict = 'T-other'
    else:
        verdict = 'T-media'
    return dict(verdict=verdict, traps_by_process=dict(by), mediaserverd_traps=len(media),
                mediaserverd_sites=[dict(exception=k[0], code0=k[1], pc_unslid=k[2], lr_unslid=k[3], count=v) for k, v in sites.most_common()],
                first_mediaserverd=media[:3], other_first=[t for t in traps if t['name'] != 'mediaserverd'][:10])


def lookup(addrs, table):
    # NAT-202 fix (after the run, symbolisation only): an address below the slide (pc 0, a call through NULL) is not looked up
    bad = {a for a in addrs if a.startswith('0x-') or int(a, 16) < 0x100000000}
    good = [a for a in addrs if a not in bad]
    res = {a: '%s not a shared cache address' % a for a in bad}
    if not good:
        return {a: res[a] for a in addrs}
    addrs_in = addrs
    addrs = good
    out = subprocess.run([sys.executable, '-B', str(HERE.parent / 'nat-189/dscsym.py'), '--table', table, 'lookup', *addrs],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    for a, l in zip(addrs, out):
        res[a] = l if ' None None' not in l else '%s not in the shared cache (page offset 0x%x)' % (a, int(a, 16) & 0x3fff)
    return {a: res[a] for a in addrs_in}


def symbolise(r, table):
    for t in r['first_mediaserverd'] + r['other_first']:
        slide = int(t['slide'], 16)
        addrs = [('0x%x' % (int(a, 16) - slide)) if int(a, 16) >= slide else ('0x-%x' % (slide - int(a, 16)) if int(a, 16) else '0x0')
                 for a in [t['pc'], t['lr'], *t['frames']]]
        t['symbols'] = list(lookup(addrs, table).values())
    for s in r['mediaserverd_sites']:
        sym = lookup([s['pc_unslid'], s['lr_unslid']], table)
        s['pc_symbol'], s['lr_symbol'] = sym[s['pc_unslid']], sym[s['lr_unslid']]


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
