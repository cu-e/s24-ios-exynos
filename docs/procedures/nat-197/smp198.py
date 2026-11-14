#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-198: did the PSCI-started cores join XNU after the EL2->EL1 drop (NAT-197, image e21)? Reads a kernel text dump (nat-097
kl_reader2 output).

What the log has:
  running   the last GenericARMPE count `N of M processors are running` (the scheduler's own count)
  failures  `psci: cpu N (MPIDR ..) took an exception on its way in ... ESR .. ELR ..` / `was started 1 seconds ago and has not joined`
  marks     `psci: cpu N early marks: ...` (only for a core that did not join). Stage 1's first value is the entry CurrentEL with, from
            NAT-197 on, the CurrentEL after the drop in bits 11:10: 0x408 = came at EL2, now EL1; 0x8 = still at EL2 (no drop);
            0x404 = came at EL1. Stage word 0x5EC000E2 = NAT-195's fallback probe ran at mark 4: the core was still at EL2 there.
  panic     any `panic(cpu N caller ...)` or `Debugger called` line
  stop      `psci: cpu N did not stop` / `cannot return to the boot loader` (psci_smp.c stop path at the timed return)

Verdicts (registered in docs/procedures/nat-197/README.md before NAT-198), first match:
  S-none      no running count line                                   -> inconclusive (the boot did not get that far, or no log)
  S-panic     a panic line                                            (reported with the cores' state)
  S2-all      running == 10 and no failure line
  S1-some     running > 1
  S0-none     running == 1; per core: where it stopped (E1..E6, E2-probe = still at EL2), its EL after the drop, its fault

  python3 -B docs/procedures/nat-197/smp198.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import sys

MAGIC = 0x5EC00000
PROBE = 0x5EC000E2
RE_RUN = re.compile(r'GenericARMPE: (?:(\d+) of (\d+) processors are running|the slower cores started too: (\d+) processors running)')
RE_REG = re.compile(r'GenericARMCPU: cpu (\d+) \(phys id (0x[0-9a-f]+)\) registered')
RE_FAULT = re.compile(r'psci: cpu (\d+) \(MPIDR (0x[0-9a-f]+)\) took an exception on its way in and has switched itself off: '
                      r'ESR (0x[0-9a-f]+) ELR (0x[0-9a-f]+) FAR (0x[0-9a-f]+) LR (0x[0-9a-f]+) SP (0x[0-9a-f]+) '
                      r'\(ELR and LR as kernel addresses: (0x[0-9a-f]+) (0x[0-9a-f]+)\)')
RE_TIMEOUT = re.compile(r'psci: cpu (\d+) \(MPIDR (0x[0-9a-f]+)\) was started \d+ seconds ago and has not joined: (.*)')
RE_NOSTART = re.compile(r'psci: cpu (\d+) \(MPIDR (0x[0-9a-f]+)\) was not started: (.*)')
RE_MARK = re.compile(r'psci: cpu (\d+) early marks: last (0x[0-9a-f]+) mpidr (0x[0-9a-f]+) '
                     + ' '.join(r'%d:(0x[0-9a-f]+),(0x[0-9a-f]+)' % s for s in range(1, 7)) + r' affinity_info (-?\d+)')
RE_PANIC = re.compile(r'panic\(cpu (\d+) caller (0x[0-9a-f]+)\): (.*)|Debugger called: <(.*)>')
RE_STOP = re.compile(r'psci: cpu (\d+) (ends the system|cannot return to the boot loader|did not stop)')
STAGES = {1: 'E1-entry', 2: 'E2-cpu-data-found', 3: 'E3-no-cpu-data', 4: 'E4-start-cpu', 5: 'E5-before-mmu', 6: 'E6-mmu-on',
          0xE2: 'E2-probe-still-at-EL2'}
EC = {0x00: 'unknown', 0x01: 'WFx', 0x07: 'FP/SIMD access', 0x15: 'SVC', 0x16: 'HVC', 0x17: 'SMC', 0x18: 'MSR/MRS trap',
      0x19: 'SVE', 0x1c: 'PAC fail', 0x20: 'instruction abort (lower EL)', 0x21: 'instruction abort', 0x22: 'PC alignment',
      0x24: 'data abort (lower EL)', 0x25: 'data abort', 0x26: 'SP alignment', 0x2f: 'SError', 0x3c: 'BRK'}


def el_after(stage1_first):
    """(entry EL, EL after the drop or None when the kernel predates NAT-197's bits)."""
    v = int(stage1_first, 16)
    entry = (v >> 2) & 3
    after = (v >> 10) & 3
    return entry, (after if v >> 8 else None)


def analyse(text):
    runs = [(int(a or c), int(b) if b else None) for a, b, c in RE_RUN.findall(text)]
    running = runs[-1][0] if runs else None
    registered = sorted({int(m[0]) for m in RE_REG.findall(text)})
    cores = {}
    for m in RE_FAULT.finditer(text):
        esr = int(m[3], 16)
        cores.setdefault(int(m[1]), {}).update(fault=dict(esr=m[3], ec=hex(esr >> 26), what=EC.get(esr >> 26, '?'), elr_kva=m[8],
                                                         far=m[5], lr_kva=m[9], sp=m[7]))
    for m in RE_TIMEOUT.finditer(text):
        cores.setdefault(int(m[1]), {}).update(timeout=m[3].strip())
    for m in RE_NOSTART.finditer(text):
        cores.setdefault(int(m[1]), {}).update(not_started=m[3].strip())
    for m in RE_MARK.finditer(text):
        g = m.groups()
        last = int(g[1], 16)
        stage = last & 0xffff if (last & ~0xffff) == MAGIC else None
        entry, after = el_after(g[3])
        cores.setdefault(int(g[0]), {}).update(last=g[1], where=STAGES.get(stage, 'E0-no-entry' if last == 0 else 'unreadable'),
                                                entry_el=entry, el_after_drop=after, dropped=(entry == 2 and after == 1),
                                                affinity_info=int(g[15]))
    panics = [dict(cpu=int(m[1]) if m[1] else None, caller=m[2], text=(m[3] or m[4] or '').strip()[:200]) for m in RE_PANIC.finditer(text)]
    stops = [dict(cpu=int(a), what=b) for a, b in RE_STOP.findall(text)]
    failed = sorted(cores)
    if running is None:
        verdict = 'S-none'
    elif panics:
        verdict = 'S-panic'
    elif running == 10 and not failed:
        verdict = 'S2-all'
    elif running > 1:
        verdict = 'S1-some'
    else:
        verdict = 'S0-none'
    where = {}
    for n, c in sorted(cores.items()):
        where.setdefault(c.get('where', 'fault' if 'fault' in c else '?'), []).append(n)
    return dict(verdict=verdict, running=running, running_counts=runs, registered=registered,
                joined=[n for n in registered if n != 0 and n not in cores] if running and running > 1 else [],
                not_joined=failed, where=where, dropped=sorted(n for n, c in cores.items() if c.get('dropped')),
                cores={str(n): c for n, c in sorted(cores.items())}, panics=panics, stop_notes=stops)


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
