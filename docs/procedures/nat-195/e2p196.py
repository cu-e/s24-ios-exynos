#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-196: the EL2 state the firmware leaves on a PSCI-started core. Reads a kernel text dump (nat-097 kl_reader2 output) for
`psci: cpu N early marks:` lines of the e2p image (NAT-195): the probe stores HCR_EL2/SCTLR_EL2 in slot 3, MDCR_EL2/VBAR_EL2 in 4,
CNTHCTL_EL2/CNTVOFF_EL2 in 5, CPTR_EL2/ICC_SRE_EL2 in 6 and sets the stage word to 0x5EC000E2.

Verdicts (registered in docs/procedures/nat-195/README.md before NAT-196):
  E-none     no early-marks line                                   -> inconclusive
  E-noprobe  lines, but no core has stage word 0x5EC000E2           -> the probe did not run (no core at EL2 reached it)
  E-partial  some, not all, started cores have it
  E-ok       every started core has it

  python3 -B docs/procedures/nat-195/e2p196.py KERNEL_TEXT [--json OUT]
"""
import json
import re
import sys

LINE = re.compile(r'psci: cpu (\d+) early marks: last (0x[0-9a-f]+) mpidr (0x[0-9a-f]+) 1:(0x[0-9a-f]+),(0x[0-9a-f]+) '
                  r'2:(0x[0-9a-f]+),(0x[0-9a-f]+) 3:(0x[0-9a-f]+),(0x[0-9a-f]+) 4:(0x[0-9a-f]+),(0x[0-9a-f]+) '
                  r'5:(0x[0-9a-f]+),(0x[0-9a-f]+) 6:(0x[0-9a-f]+),(0x[0-9a-f]+) affinity_info (-?\d+)')
PROBE = 0x5EC000E2


def bits(v, spec):
    return {name: (v >> lo) & ((1 << (hi - lo + 1)) - 1) for name, (hi, lo) in spec.items()}


HCR = dict(VM=(0, 0), FMO=(3, 3), IMO=(4, 4), AMO=(5, 5), TWI=(13, 13), TWE=(14, 14), TSC=(19, 19), TGE=(27, 27), RW=(31, 31),
           E2H=(34, 34), API=(41, 41), APK=(40, 40))
SCTLR2 = dict(M=(0, 0), C=(2, 2), I=(12, 12), EE=(25, 25))
MDCR = dict(HPMN=(4, 0), TPM=(6, 6), TDE=(8, 8), TDA=(9, 9))
CNTHCTL = dict(EL1PCTEN=(0, 0), EL1PCEN=(1, 1))
CPTR = dict(TZ=(8, 8), TFP=(10, 10), TCPAC=(31, 31))
SRE = dict(SRE=(0, 0), DFB=(1, 1), DIB=(2, 2), Enable=(3, 3))


def decode(m):
    v = [int(x, 16) for x in m.groups()[1:16]]
    last, mpidr, el, sctlr1 = v[0], v[1], v[2], v[3]
    core = dict(cpu=int(m[1]), last=hex(last), mpidr=hex(mpidr), entry_el=el >> 2, sctlr_el1_entry=hex(sctlr1),
                affinity_info=int(m[16]), probe=last == PROBE)
    if last == PROBE:
        hcr, sctlr2, mdcr, vbar, cnthctl, cntvoff, cptr, sre = v[6:14]
        core.update(HCR_EL2=hex(hcr), SCTLR_EL2=hex(sctlr2), MDCR_EL2=hex(mdcr), VBAR_EL2=hex(vbar), CNTHCTL_EL2=hex(cnthctl),
                    CNTVOFF_EL2=hex(cntvoff), CPTR_EL2=hex(cptr), ICC_SRE_EL2=hex(sre),
                    fields=dict(HCR_EL2=bits(hcr, HCR), SCTLR_EL2=bits(sctlr2, SCTLR2), MDCR_EL2=bits(mdcr, MDCR),
                                CNTHCTL_EL2=bits(cnthctl, CNTHCTL), CPTR_EL2=bits(cptr, CPTR), ICC_SRE_EL2=bits(sre, SRE)))
        # what the loader's own from_el2 sequence (HCR=RW, CNTHCTL=3, ICC_SRE|=9, CPTR=0, SPSR EL1h) would change
        core['loader_drop_changes'] = sorted(n for n, c in (
            ('HCR_EL2', hcr != 1 << 31), ('CNTHCTL_EL2', cnthctl & 3 != 3), ('ICC_SRE_EL2', sre & 9 != 9), ('CPTR_EL2', cptr != 0)) if c)
        core['not_touched_by_loader_drop'] = dict(CNTVOFF_EL2=hex(cntvoff), MDCR_EL2=hex(mdcr), VBAR_EL2=hex(vbar), SCTLR_EL2=hex(sctlr2))
    return core


def analyse(text):
    cores = [decode(m) for m in LINE.finditer(text)]
    n = sum(c['probe'] for c in cores)
    verdict = 'E-none' if not cores else 'E-noprobe' if n == 0 else 'E-ok' if n == len(cores) else 'E-partial'
    return dict(verdict=verdict, cores_reported=len(cores), cores_probed=n,
                same_state_on_all_probed=len({json.dumps({k: c[k] for k in c if k.endswith('_EL2')}, sort_keys=True)
                                              for c in cores if c['probe']}) == 1 if n else None,
                cores=cores)


def main():
    r = analyse(open(sys.argv[1], encoding='utf-8', errors='replace').read())
    s = json.dumps(r, indent=1)
    if '--json' in sys.argv:
        open(sys.argv[sys.argv.index('--json') + 1], 'w').write(s + '\n')
    print(s)


if __name__ == '__main__':
    main()
