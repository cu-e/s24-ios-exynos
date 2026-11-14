#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-195 host tests: the start.o patch is NAT-152's plus only the probe block; the probe writes no system register (no msr) and
stores only into the core's own early-mark slot; the built kernel has scV's segments and external symbols; the probe instructions in
the linked kernel are of the allowed kinds; the analyser's verdicts on NAT-153's real log and on synthetic probe lines; the session
derivation is current."""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / 'artifacts/xnu-macho-tools/macho-session4/prefix/bin'
OD = Path.home() / 'Android/Sdk/ndk/28.2.13676358/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-objdump'


def unstripped(kdir):
    return next((ROOT / kdir).glob('link*/kernel/kernel.unstripped'))


def plus(path):
    return [l[1:] for l in Path(path).read_text().splitlines() if l.startswith('+') and not l.startswith('+++')]


class Patch(unittest.TestCase):
    def test_superset_of_nat152(self):
        a, b = plus(ROOT / 'docs/procedures/nat-152/start.patch'), plus(HERE / 'start.patch')
        self.assertEqual([l for l in a if l not in b], [])
        self.assertFalse([l for l in Path(HERE / 'start.patch').read_text().splitlines() if l.startswith('-') and not l.startswith('---')])
        from collections import Counter
        extra = list((Counter(b) - Counter(a)).elements())
        code = [l.split('//')[0].strip() for l in extra]
        code = [c for c in code if c and not c.startswith(('/*', '*', '#'))]
        ops = {c.split()[0] for c in code if not c.endswith(':')}
        self.assertEqual(ops, {'mrs', 'cmp', 'b.ne', 'PSCI_SMP_EARLY_MARK', 'ubfx', 'adrp', 'add', 'movz', 'movk', 'str', 'dc', 'dsb',
                               'smc', 'wfe', 'b'})
        self.assertNotIn('msr', ops)
        stores = [c for c in code if c.startswith('str')]
        self.assertEqual(stores, ['str\t\tx9, [x10]'])
        # the only secure call is PSCI CPU_OFF 0x84000002
        self.assertIn('movz\tw0, #0x0002', '\n'.join(code))
        self.assertIn('movk\tw0, #0x8400, lsl #16', '\n'.join(code))
        self.assertEqual(sum(c.startswith('smc') for c in code), 1)


class Kernel(unittest.TestCase):
    def test_layout_equals_scv(self):
        a, b = unstripped('artifacts/nat-185/kernel-001'), unstripped('artifacts/nat-195/kernel-001')
        seg = lambda k: [l for l in subprocess.run([str(TOOLS / 'aarch64-apple-darwin-size'), '-m', str(k)], capture_output=True, text=True,
                                                   check=True).stdout.splitlines() if l.startswith('Segment')]
        self.assertEqual(seg(a), seg(b))
        nm = lambda k: subprocess.run([str(TOOLS / 'aarch64-apple-darwin-nm'), '-n', str(k)], capture_output=True, text=True, check=True).stdout
        self.assertEqual(nm(a), nm(b))
        r = json.loads((ROOT / 'artifacts/nat-195/kernel-001/rebuild.json').read_text())
        self.assertEqual(r['undefined_symbols'], 0)

    def test_probe_instructions(self):
        k = unstripped('artifacts/nat-195/kernel-001')
        out = subprocess.run([str(OD), '-d', '--no-show-raw-insn', '--start-address=0xfffffff00743b570', '--stop-address=0xfffffff00743c000',
                              str(k)], capture_output=True, text=True, check=True).stdout
        lines = [l.strip() for l in out.splitlines() if re.match(r'^\s*fff[0-9a-f]+:', l)]
        mnem = [re.split(r'\s+', l.split(':', 1)[1].strip())[0] for l in lines]
        self.assertNotIn('msr', mnem)
        self.assertEqual(mnem.count('smc'), 1)
        self.assertEqual(mnem.count('wfe'), 1)
        regs = re.findall(r'mrs\s+x\d+, (\w+)', out)
        self.assertTrue({'HCR_EL2', 'SCTLR_EL2', 'MDCR_EL2', 'VBAR_EL2', 'CNTHCTL_EL2', 'CNTVOFF_EL2', 'CPTR_EL2', 'ICC_SRE_EL2'} <= set(regs))


class Analyser(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('e2p196', HERE / 'e2p196.py')
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def test_nat153_is_noprobe(self):
        r = self.m.analyse((ROOT / 'artifacts/nat-153/analysis/kernel-text.txt').read_text(errors='replace'))
        self.assertEqual((r['verdict'], r['cores_reported'], r['cores_probed']), ('E-noprobe', 9, 0))
        self.assertEqual({c['entry_el'] for c in r['cores']}, {2})

    def test_synthetic(self):
        line = ('[ 1.0]: psci: cpu %d early marks: last 0x5ec000e2 mpidr 0x8100%02x00 1:0x8,0x30d8099a 2:0x996dca720,0x90183e00c '
                '3:0x80000002,0x30c50830 4:0x6,0x0 5:0x3,0x0 6:0x0,0x9 affinity_info 1\n')
        r = self.m.analyse(line % (1, 1) + line % (2, 2))
        self.assertEqual(r['verdict'], 'E-ok')
        self.assertTrue(r['same_state_on_all_probed'])
        c = r['cores'][0]
        self.assertEqual(c['fields']['HCR_EL2']['RW'], 1)
        self.assertEqual(c['fields']['HCR_EL2']['VM'], 0)
        self.assertEqual(c['fields']['ICC_SRE_EL2']['Enable'], 1)
        self.assertEqual(c['loader_drop_changes'], ['HCR_EL2'])
        mixed = line % (1, 1) + line.replace('0x5ec000e2', '0x5ec00006') % (2, 2)
        self.assertEqual(self.m.analyse(mixed)['verdict'], 'E-partial')
        self.assertEqual(self.m.analyse('nothing')['verdict'], 'E-none')


class Session(unittest.TestCase):
    def test_derivation(self):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'derive196.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((ROOT / 'artifacts/nat-195/package-001/package.json').read_text())['images']['loader-diag-xnu-e2p-md1']
        s = (HERE / 'session_nat196.py').read_text()
        self.assertIn(p['recovery_sha256'], s)
        self.assertIn(p['payload_sha256'], s)
        img = ROOT / 'artifacts/nat-195/package-001/loader-diag-xnu-e2p-md1/recovery.img'
        self.assertEqual(hashlib.sha256(img.read_bytes()).hexdigest(), p['recovery_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
