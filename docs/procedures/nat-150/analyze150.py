#!/usr/bin/env python3
"""NAT-150 analyser (rule fixed before the run): every analyze146 verdict, with the SMP rule corrected, plus the early marks that the
NAT-150 kernel prints for each core that has not joined.

    analyze150.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON --out OUT_JSON

The NAT-146 rule counted `cpu_start() cpu: N` lines as started cores. The boot processor prints that line for every core it asks the
firmware for, so it says nothing about the core itself (NAT-149: 10 such lines, 1 core running). Here:
  joined     the cores asked for (cpu_start lines, the boot processor excluded) that have no failure line
  running    the last GenericARMPE count (unchanged), the ground truth of the scheduler
  smp verdict (first match):
    C2-all-ten   running 10, banner 10, no failure line
    C1-some      running more than 1
    C0-one       otherwise
early marks (psci_smp.c NAT-150): `psci: cpu N early marks: last L mpidr M 1:a,b ... 6:a,b affinity_info S`. L is 0x5EC00000 | the
last stage the core wrote (PSCI_SMP_EARLY_MARK in start.s), or 0 if it wrote none:
  E0-no-entry          no mark: the core never ran the first instruction block of LowResetVectorBase (or its store never reached
                       memory)
  E1-entry             at the entry, but neither found its cpu data nor gave up looking (a fault or a hang in the lookup)
  E2-cpu-data-found    cpu data and a valid reset handler found; not at start_cpu's end
  E3-no-cpu-data       no cpu data for its MPIDR, or no valid handler; it spins in the reset vector (a = MPIDR & 0xffff or the
                       handler, b = the end of the entries)
  E4-start-cpu         start_cpu done (stacks), not yet before the MMU switch
  E5-before-mmu        just before the MMU is switched on, not after it
  E6-mmu-on            MMU on (V=P); it did not reach arm_init_cpu()
affinity_info is PSCI AFFINITY_INFO for the core after the wait: 0 on, 1 off, 2 on pending, negative an error.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat150_analyze146', HERE.parent / 'nat-145/analyze146.py')
A146 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A146)

MAGIC = 0x5EC00000
RE_MARK = re.compile(r'psci: cpu (\d+) early marks: last (0x[0-9a-f]+) mpidr (0x[0-9a-f]+) '
                     + ' '.join(r'%d:(0x[0-9a-f]+),(0x[0-9a-f]+)' % s for s in range(1, 7)) + r' affinity_info (-?\d+)')
STAGE_NAMES = {0: 'E0-no-entry', 1: 'E1-entry', 2: 'E2-cpu-data-found', 3: 'E3-no-cpu-data', 4: 'E4-start-cpu', 5: 'E5-before-mmu',
               6: 'E6-mmu-on'}
AFFINITY = {0: 'on', 1: 'off', 2: 'on pending'}


def marks(text):
    out = {}
    for m in RE_MARK.finditer(text):
        g = m.groups()
        last = int(g[1], 16)
        stage = last & 0xffff if (last & ~0xffff) == MAGIC and (last & 0xffff) in STAGE_NAMES else (0 if last == 0 else None)
        vals = [int(x, 16) for x in g[3:15]]
        aff = int(g[15])
        out[int(g[0])] = dict(last=g[1], stage=stage, where=STAGE_NAMES.get(stage, 'unreadable'), mpidr=g[2],
                              stages={s: [hex(vals[2 * s - 2]), hex(vals[2 * s - 1])] for s in range(1, 7)
                                      if vals[2 * s - 2] or vals[2 * s - 1]},
                              affinity_info=aff, affinity=AFFINITY.get(aff, 'error' if aff < 0 else '?'))
    return out


def classify(text, pixels):
    out = A146.classify(text, pixels)
    c = out['cpus']
    boot = 0
    asked = [n for n in c['started'] if n != boot]
    failed = {f['cpu'] for f in c['failed']}
    c['asked'] = asked
    c['joined'] = [n for n in asked if n not in failed]
    c['not_joined'] = sorted(failed)
    out['smp_rule146'] = out['smp']
    running = c['running']
    out['smp'] = ('C2-all-ten' if running == 10 and c['ncpu'] == 10 and not failed else
                  'C1-some' if running is not None and running > 1 else 'C0-one')
    mk = marks(text)
    out['early_marks'] = mk
    where = {}
    for n, m in sorted(mk.items()):
        where.setdefault(m['where'], []).append(n)
    out['early_where'] = where
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kernel-text', required=True, type=Path)
    ap.add_argument('--pixels', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    r = classify(a.kernel_text.read_text(errors='replace'), json.loads(a.pixels.read_text()))
    a.out.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('window', 'display', 'start', 'events', 'reader', 'ui', 'physical_input', 'smp', 'smp_rule146',
                                         'fps_best_window', 'fps_median_interval_ms', 'fps_steady_windows', 'early_where')}))
    print(json.dumps(r['cpus']))


if __name__ == '__main__':
    main()
