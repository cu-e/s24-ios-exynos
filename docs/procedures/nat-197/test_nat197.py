#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-197 host tests: the start.o patch is NAT-195's with one reset_vector instruction replaced by a same-size branch to an
out-of-line block; that block's system-register writes are the boot loader's from_el2 sequence instruction for instruction (only
the scratch registers and the label differ); the linked kernel has scV's segments and symbols, the branch at reset_vector+4 and the
block's way back to reset_vector+8; the analyser's verdicts on real logs (NAT-153, NAT-196) and on synthetic lines; the session
derivation is current."""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / 'artifacts/xnu-macho-tools/macho-session4/prefix/bin'
OD = Path.home() / 'Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-objdump'
LOADER = ROOT / 'artifacts/nat-020/build-003/source/shim/e1s-xnu/start.S'


def unstripped(kdir):
    return next((ROOT / kdir).glob('link*/kernel/kernel.unstripped'))


def plus(path):
    return [l[1:] for l in Path(path).read_text().splitlines() if l.startswith('+') and not l.startswith('+++')]


def code(line):
    c = re.split(r'//|/\*', line)[0].strip()
    return re.sub(r'\s+', ' ', c)


def loader_from_el2():
    """The loader's from_el2 instructions up to and including eret, the loader_main marker (mov x20, #4) left out."""
    lines = LOADER.read_text().splitlines()
    i = lines.index('from_el2:') + 1
    out = []
    for l in lines[i:]:
        c = code(l)
        if not c:
            continue
        if c != 'mov x20, #4':
            out.append(c)
        if c == 'eret':
            return out
    raise AssertionError('no eret')


def drop_block():
    lines = (HERE / 'start.patch').read_text().splitlines()
    i = lines.index('+Lnat197_drop:') + 1
    out = []
    for l in lines[i:]:
        c = code(l[1:])
        if c:
            out.append(c)
        if c == 'eret':
            return out
    raise AssertionError('no eret')


class Patch(unittest.TestCase):
    def test_nat195_plus_the_drop(self):
        a, b = plus(ROOT / 'docs/procedures/nat-195/start.patch'), plus(HERE / 'start.patch')
        removed = [code(l) for l in (Counter(a) - Counter(b)).elements() if code(l)]
        # the NAT-195 probe #define keeps its code and gets a reworded comment; the only instruction gone from its place is
        # reset_vector's mrs x12 (moved into the block)
        self.assertEqual(sorted(removed), ['#define NAT195_EL2_PROBE 1', 'mrs x12, SCTLR_EL1'])
        self.assertIn('#define NAT195_EL2_PROBE 1', [code(l) for l in b])
        self.assertFalse([l for l in (HERE / 'start.patch').read_text().splitlines() if l.startswith('-') and not l.startswith('---')])
        added = [code(l) for l in (Counter(b) - Counter(a)).elements()]
        added = [c for c in added if c and not c.startswith(('*', '#'))]
        self.assertIn('b Lnat197_drop', added)
        self.assertIn('mrs x12, SCTLR_EL1', added)      # moved, not dropped
        self.assertEqual(sum(c.startswith('msr') for c in added), 6)
        self.assertEqual(added.count('eret'), 1)
        self.assertNotIn('smc #0', added)
        self.assertFalse([c for c in added if c.startswith(('str', 'stp', 'hvc'))])

    def test_block_is_the_loader_sequence(self):
        ld = loader_from_el2()
        ours = drop_block()
        self.assertEqual(ours[:2], ['cmp x11, #0x8', 'b.ne Lnat197_el1'])
        norm = [re.sub(r'\bx1\b', 'x9', re.sub(r'\bx2\b', 'x10', c)).replace('el1_entry', 'Lnat197_el1') for c in ld]
        self.assertEqual([c.lower() for c in ours[2:]], [c.lower() for c in norm])
        writes = [c.split()[1].rstrip(',').upper() for c in ours if c.startswith('msr')]
        self.assertEqual(writes, ['HCR_EL2', 'CNTHCTL_EL2', 'ICC_SRE_EL2', 'CPTR_EL2', 'ELR_EL2', 'SPSR_EL2'])

    def test_probe_fallback_kept(self):
        s = (HERE / 'start.patch').read_text()
        self.assertIn('#define NAT195_EL2_PROBE 1', s)
        self.assertIn('Lnat195_park:', s)


class Kernel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a, cls.b = unstripped('artifacts/nat-185/kernel-001'), unstripped('artifacts/nat-197/kernel-001')

    def test_layout_equals_scv(self):
        seg = lambda k: [l for l in subprocess.run([str(TOOLS / 'aarch64-apple-darwin-size'), '-m', str(k)], capture_output=True, text=True,
                                                   check=True).stdout.splitlines() if l.startswith('Segment')]
        self.assertEqual(seg(self.a), seg(self.b))
        nm = lambda k: subprocess.run([str(TOOLS / 'aarch64-apple-darwin-nm'), '-n', str(k)], capture_output=True, text=True, check=True).stdout
        self.assertEqual(nm(self.a), nm(self.b))
        r = json.loads((ROOT / 'artifacts/nat-197/kernel-001/rebuild.json').read_text())
        self.assertEqual(r['undefined_symbols'], 0)

    def dis(self, k, lo, hi):
        out = subprocess.run([str(OD), '-d', '--no-show-raw-insn', '--start-address=%#x' % lo, '--stop-address=%#x' % hi, str(k)],
                             capture_output=True, text=True, check=True).stdout
        rows = []
        for l in out.splitlines():
            m = re.match(r'^\s*(fff[0-9a-f]+):\s+(\S+)\s*(.*)$', l)
            if m:
                rows.append((int(m[1], 16), m[2], m[3].split(';')[0].strip()))
        return rows

    def test_branch_out_and_back(self):
        rv = 0xfffffff00743b400                         # _reset_vector (nm equals scV's)
        head = self.dis(self.b, rv, rv + 12)
        self.assertEqual([r[1] for r in head], ['mrs', 'b', 'msr'])
        block = int(head[1][2].split()[0], 16)
        self.assertTrue(0xfffffff00743b570 < block < 0xfffffff00743c000)   # same page as the reset vector, after __start
        rows = self.dis(self.b, block, block + 0x50)
        mn = [r[1] for r in rows]
        self.assertEqual(mn[:2], ['cmp', 'b.ne'])
        end = mn.index('eret')
        self.assertEqual([r[2].split(',')[0] for r in rows[:end] if r[1] == 'msr'],
                         ['HCR_EL2', 'CNTHCTL_EL2', 'ICC_SRE_EL2', 'CPTR_EL2', 'ELR_EL2', 'SPSR_EL2'])
        el1 = int(rows[1][2].split()[0], 16)
        self.assertEqual(el1, rows[end + 1][0])          # b.ne and the eret target are the same EL1 landing
        adr = [r for r in rows if r[1] == 'adr'][0]
        self.assertEqual(int(adr[2].split(',')[1].split()[0], 16), el1)
        self.assertEqual([r[1] for r in rows[end + 1:end + 5]], ['mrs', 'orr', 'mrs', 'b'])
        self.assertEqual(int(rows[end + 4][2].split()[0], 16), rv + 8)

    def test_scv_reset_vector_otherwise_same(self):
        rv = 0xfffffff00743b400
        a = self.dis(self.a, rv + 8, 0xfffffff00743b570)
        b = self.dis(self.b, rv + 8, 0xfffffff00743b570)
        self.assertEqual(a, b)


class Analyser(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('smp198', HERE / 'smp198.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_real_logs(self):
        r = self.m.analyse((ROOT / 'artifacts/nat-196/analysis/kernel-text.txt').read_text(errors='replace'))
        self.assertEqual((r['verdict'], r['running']), ('S0-none', 1))
        self.assertEqual(r['where'], {'E2-probe-still-at-EL2': list(range(1, 10))})
        self.assertEqual(r['dropped'], [])
        r = self.m.analyse((ROOT / 'artifacts/nat-153/analysis/kernel-text.txt').read_text(errors='replace'))
        self.assertEqual(r['verdict'], 'S0-none')
        self.assertEqual(set(r['where']), {'E6-mmu-on'})

    def test_synthetic(self):
        reg = ''.join('GenericARMCPU: cpu %d (phys id 0x%x00) registered\n' % (n, n) for n in range(10))
        self.assertEqual(self.m.analyse(reg)['verdict'], 'S-none')
        ok = reg + 'GenericARMPE: 10 of 10 processors are running\n'
        r = self.m.analyse(ok)
        self.assertEqual((r['verdict'], r['joined']), ('S2-all', list(range(1, 10))))
        mark = ('psci: cpu 4 (MPIDR 0x400) was started 1 seconds ago and has not joined: no sign of it since the firmware took the request\n'
                'psci: cpu 4 early marks: last 0x5ec00006 mpidr 0x81000400 1:0x408,0x30d5099a 2:0x1,0x2 3:0x0,0x0 4:0x1,0x2 '
                '5:0x1,0x2 6:0x1,0x2 affinity_info 0\n')
        r = self.m.analyse(reg + mark + 'GenericARMPE: 9 of 10 processors are running\n')
        self.assertEqual(r['verdict'], 'S1-some')
        self.assertEqual(r['dropped'], [4])
        self.assertEqual(r['cores']['4']['where'], 'E6-mmu-on')
        self.assertNotIn(4, r['joined'])
        fault = ('psci: cpu 2 (MPIDR 0x81000200) took an exception on its way in and has switched itself off: ESR 0x96000045 ELR 0x1 '
                 'FAR 0x2 LR 0x3 SP 0x4 (ELR and LR as kernel addresses: 0xfffffff007000001 0xfffffff007000003)\n')
        r = self.m.analyse(reg + fault + 'GenericARMPE: 1 of 10 processors are running\n')
        self.assertEqual(r['verdict'], 'S0-none')
        self.assertEqual(r['cores']['2']['fault']['what'], 'data abort')
        r = self.m.analyse(ok + 'panic(cpu 3 caller 0xfffffff007123456): x\n')
        self.assertEqual(r['verdict'], 'S-panic')
        self.assertEqual(self.m.el_after('0x8'), (2, None))
        self.assertEqual(self.m.el_after('0x404'), (1, 1))


class Session(unittest.TestCase):
    def test_derivation(self):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'derive198.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((ROOT / 'artifacts/nat-197/package-001/package.json').read_text())['images']['loader-diag-xnu-e21-md1']
        s = (HERE / 'session_nat198.py').read_text()
        self.assertIn(p['recovery_sha256'], s)
        self.assertIn(p['payload_sha256'], s)
        img = ROOT / 'artifacts/nat-197/package-001/loader-diag-xnu-e21-md1/recovery.img'
        self.assertEqual(hashlib.sha256(img.read_bytes()).hexdigest(), p['recovery_sha256'])
        b = json.loads((ROOT / 'artifacts/nat-197/build-001/build.json').read_text())
        self.assertEqual(b['nat152_changes']['loader_sites_check'], dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(b['nat197_changes']['start_patch'], 'docs/procedures/nat-197/start.patch')


if __name__ == '__main__':
    unittest.main(verbosity=2)
