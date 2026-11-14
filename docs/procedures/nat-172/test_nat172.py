#!/usr/bin/env python3
"""NAT-172 host checks: the patched e1s_acpm.c (docs/procedures/nat-172/e1s_acpm.patch) with NAT-123's e1s_pmic.patch against
host/fakeapm.c (NAT-123's fake APM plus a channel-0 DVFS "firmware" and a fake CMU_CPUCL0 PLL_CON3). Synthetic, not hardware
evidence. NAT-123's own PMIC cases are re-run here on the new transport (class Nat123Regression).
"""
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DONOR = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd'
PATCHES = tempfile.mkdtemp(prefix='nat172-patches-', dir=os.environ.get('TMPDIR'))
shutil.copy(HERE / 'e1s_acpm.patch', PATCHES)
shutil.copy(ROOT / 'docs/procedures/nat-123/e1s_pmic.patch', PATCHES)

spec = importlib.util.spec_from_file_location('t123', ROOT / 'docs/procedures/nat-123/test_nat123.py')
t123 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t123)
t123.HERE = HERE                        # host/ of NAT-172
t123.PATCH_DIR = Path(PATCHES)


class Nat123Regression(t123.TransportTests):
    pass


del t123.TransportTests                 # run NAT-123's cases only through the subclass above


class Dvfs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = Nat123Regression
        Nat123Regression.setUpClass()

    def run_case(self, case='normal'):
        out = subprocess.run([str(Nat123Regression.exe), '2', case], check=True, text=True, capture_output=True, timeout=20).stdout
        m = re.search(r'DVFS cmds=(\d+) bad=(\d+) con3=(0x[0-9a-f]+|0)', out)
        return out, int(m.group(1)), int(m.group(2)), int(m.group(3), 16)

    def test_one_stock_request_and_both_readbacks(self):
        out, n, bad, con3 = self.run_case()
        self.assertEqual((n, bad), (1, 0))
        self.assertRegex(out, r'dvfs ch0 00[0-9a-f]{2}0002 001de458 00000000 00000000')     # 1959000 kHz, seq in 21:16
        self.assertIn('e1s-cpuclk: before: pll con3 0x80230102 = 672000 kHz', out)
        self.assertIn('FREQ_REQ cluster 0 1959000 kHz on channel 0: error 0', out)
        self.assertIn('e1s-cpuclk: after: pll con3 0x80660102 = 1958400 kHz', out)
        self.assertIn('writes=2 bad=0 ldo9=0xf0 ldo18=0xd8', out)                        # the PMIC path still works
        self.assertLess(out.index('PMIC channel ready'), out.index('e1s-cpuclk: before'))

    def test_no_request_cases(self):
        for case, text in (('at-max', 'already at the target'), ('pll-off', 'not decoded'),
                           ('dvfs-irq', 'DVFS channel 0 not usable'), ('dvfs-type', 'DVFS channel 0 not usable'),
                           ('dvfs-pointer', 'DVFS channel 0 has an invalid queue pointer'),
                           ('arg-1500000', '1500000 kHz is not a stock cluster-0 level'), ('arg-0', 'off (e1scpuclk=0)')):
            with self.subTest(case=case):
                out, n, bad, _ = self.run_case(case)
                self.assertEqual((n, bad), (0, 0), out)
                self.assertIn(text, out)
                self.assertIn('writes=2 bad=0 ldo9=0xf0 ldo18=0xd8', out)

    def test_other_stock_level_by_boot_arg(self):
        out, n, bad, con3 = self.run_case('arg-1440000')
        self.assertEqual((n, bad), (1, 0))
        self.assertIn('dvfs ch0 ', out)
        self.assertIn(' 0015f900 00000000 00000000', out)

    def test_silent_firmware_times_out_once_and_pmic_still_works(self):
        out, n, bad, _ = self.run_case('dvfs-silent')
        self.assertEqual((n, bad), (1, 0))
        self.assertIn('on channel 0: error 60', out)
        self.assertIn('writes=2 bad=0 ldo9=0xf0 ldo18=0xd8', out)

    def test_ignored_request_shows_in_the_readback(self):
        out, n, _, _ = self.run_case('dvfs-ignored')
        self.assertEqual(n, 1)
        self.assertIn('e1s-cpuclk: after: pll con3 0x80230102 = 672000 kHz', out)


class Analyser(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('cpuclk173', HERE / 'cpuclk173.py')
        self.a = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.a)

    def host_text(self, case):
        return subprocess.run([str(Nat123Regression.exe), '2', case], check=True, text=True, capture_output=True, timeout=20).stdout

    @classmethod
    def setUpClass(cls):
        Nat123Regression.setUpClass()

    def test_verdicts_on_host_runs(self):
        # the host timer makes every add rate equal, so a moved PLL reads C1 there; C2 needs the rate to rise as well
        for case, want in (('normal', 'C1'), ('at-max', 'C-skip'), ('dvfs-silent', 'C-err'), ('dvfs-ignored', 'C-same')):
            with self.subTest(case=case):
                self.assertEqual(self.a.analyse(self.host_text(case))['verdict'], want)
        self.assertEqual(self.a.analyse(self.host_text('at-max'))['reason'], 'PLL already at the target')

    def test_c2_and_inconclusive(self):
        t = ('[  1.0]: e1s-cpuclk: before: pll con3 0x80230102 = 672000 kHz; 671 adds/us; mbox INTMR1 0x00000000\n'
             '[  1.1]: e1s-cpuclk: FREQ_REQ cluster 0 1959000 kHz on channel 0: error 0, reply 00010002 001de458 00000000 00000000\n'
             '[  1.2]: e1s-cpuclk: after: pll con3 0x80660102 = 1958400 kHz; 1950 adds/us\n')
        r = self.a.analyse(t)
        self.assertEqual((r['verdict'], r['before']['fields'], r['rate_ratio']), ('C2', dict(enable=True, m=35, p=1, s=2), 2.906))
        self.assertEqual(self.a.analyse('nothing')['verdict'], 'inconclusive')


if __name__ == '__main__':
    unittest.main()
