#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-204: does mediaserverd stay up with the donor's media library (NAT-203 image e2m)? Reads the kernel text (nat-097 kl_reader2
output), which carries launchd's own lines about the job and the kernel's user-exception trace (on in e2s/e2m).

Counted:
  - `usertrap: mediaserverd[PID] ...` lines (trap202.analyse), split into NAT-202's site (pc 0 with lr CoreImage 0x194b1458c
    unslid: the portrait-filter prewarm's GL call) and any other site;
  - launchd: `(.../com.apple.mediaserverd [PID]) <Notice>: exited due to SIGSEGV`, the highest `service has crashed N times in a row`,
    `internal event: WILL_SPAWN` (spawns), the pids seen;
  - the library's own lines (`hakios: mediaserverd: ...`, `hakios: +[...]: found ..., expected ...; left alone`), if they reached the
    kernel text.

Verdicts (registered in docs/procedures/nat-203/README.md before NAT-204), first match:
  M-none   no mediaserverd line at all                                   -> inconclusive (the job did not run, or the lines were lost)
  M-same   a mediaserverd trap at NAT-202's site                         (the library did not take effect)
  M-other  a mediaserverd trap elsewhere, or an exit due to a signal     (a new fault: see the sites)
  M-fixed  mediaserverd lines, no trap and no exit due to a signal

  python3 -B docs/procedures/nat-203/media204.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'nat-201'))
import trap202  # noqa: E402

NAT202_LR = 0x194b1458c                       # lr less the shared cache slide, with pc 0 (the slide differs per boot)
RE_JOB = re.compile(r'com\.apple\.mediaserverd(?: \[(\d+)\])?\) <\w+>: (.*)')
RE_SIGNAL = re.compile(r'exited due to (SIG\w+)')
RE_CRASHED = re.compile(r'service has crashed (\d+) times in a row')
RE_LIB = re.compile(r'hakios: (?:mediaserverd: )?([^\n]*)')


def analyse(text):
    t = trap202.analyse(text)
    media = [x for x in text.splitlines() if 'mediaserverd' in x]
    pids, signals, crashed, spawns = set(), [], 0, 0
    for line in media:
        m = RE_JOB.search(line)
        if not m:
            continue
        if m[1]:
            pids.add(int(m[1]))
        s = RE_SIGNAL.search(m[2])
        if s:
            signals.append(s[1])
        c = RE_CRASHED.search(m[2])
        if c:
            crashed = max(crashed, int(c[1]))
        if 'internal event: WILL_SPAWN' in m[2]:
            spawns += 1
    lib = [m[1] for x in text.splitlines() if 'hakios:' in x and ('mediaserverd' in x or 'left alone' in x)
           for m in [RE_LIB.search(x)] if m]
    same = 0
    for line in text.splitlines():
        m = trap202.RE_TRAP.search(line)
        if m and m[1] == 'mediaserverd' and int(m[6], 16) == 0 and int(m[7], 16) - int(m[9], 16) == NAT202_LR:
            same += 1
    other = t['mediaserverd_traps'] - same
    if not media:
        verdict = 'M-none'
    elif same:
        verdict = 'M-same'
    elif other or signals:
        verdict = 'M-other'
    else:
        verdict = 'M-fixed'
    return dict(verdict=verdict, mediaserverd_lines=len(media), traps_at_nat202_site=same, traps_elsewhere=other,
                sites=t['mediaserverd_sites'], exits_by_signal=signals, crashed_in_a_row_max=crashed, spawns=spawns,
                pids=sorted(pids), library_lines=lib[:20], traps_by_process=t['traps_by_process'])


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
