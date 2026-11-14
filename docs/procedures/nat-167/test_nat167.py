"""NAT-167 host tests: the kernel differs from NAT-165's only in e1s_touch.o, whose patch is NAT-143's plus the half-bit default;
the image is scM's with the tag changed; loader gates pass; the default is what the built object carries (the ID-poll path and the
event path both use e1s_halfbit through spi_delay); counted session."""
import difflib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
M = ROOT / 'artifacts/nat-165/build-001'
N = ROOT / 'artifacts/nat-167/build-001'
MN, NN = 'loader-diag-xnu-scM-md1', 'loader-diag-xnu-scN-md1'
SRC = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_touch.c'


def need(*paths):
    for p in paths:
        if not p.exists():
            raise unittest.SkipTest('%s missing' % p)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


class Kernel(unittest.TestCase):
    def test_one_object_one_value(self):
        need(ROOT / 'artifacts/nat-167/kernel-001/rebuild.json')
        b = load('nat167_b_t', HERE / 'build.py')
        b.check_kernel()
        self.assertTrue(b.patch_delta())

    def test_halfbit_used_only_in_spi_delay(self):
        need(SRC)
        src = SRC.read_text()
        uses = [l.strip() for l in src.splitlines() if 'e1s_halfbit' in l]
        self.assertEqual(uses, ['static uint32_t e1s_halfbit = 400;', 'for (volatile uint32_t i = 0; i < e1s_halfbit; i++) {',
                                'PE_parse_boot_argn("e1stouch_delay", &e1s_halfbit, sizeof(e1s_halfbit));',
                                'if (e1s_halfbit == 0) {', 'e1s_halfbit = 1;'])

    def test_object_carries_new_default(self):
        """The rebuilt e1s_touch.o's __DATA,__data holds 8 at _e1s_halfbit where NAT-165's holds 400 (cctools nm/otool)."""
        import subprocess
        t = ROOT / 'artifacts/xnu-macho-tools/macho-session4/prefix/bin/aarch64-apple-darwin-'
        vals = {}
        for d in ('nat-165', 'nat-167'):
            o = ROOT / ('artifacts/%s/kernel-001/compile/bsd_e1s_touch.o/e1s_touch.o' % d)
            need(o, Path(str(t) + 'nm'))
            nm = subprocess.run([str(t) + 'nm', str(o)], capture_output=True, text=True, check=True).stdout
            addr = [int(l.split()[0], 16) for l in nm.splitlines() if l.split()[-1:] == ['_e1s_halfbit']][0]
            words = {}
            for l in subprocess.run([str(t) + 'otool', '-d', str(o)], capture_output=True, text=True, check=True).stdout.splitlines():
                parts = l.split()
                if parts and all(c in '0123456789abcdef' for c in parts[0]) and len(parts[0]) == 16:
                    for i, w in enumerate(parts[1:]):
                        words[int(parts[0], 16) + 4 * i] = int(w, 16)
            vals[d] = words[addr]
        self.assertEqual(vals, {'nat-165': 400, 'nat-167': 8})


class Image(unittest.TestCase):
    def test_cmdline_and_gates(self):
        need(M / 'build.json', N / 'build.json')
        m = json.loads((M / 'build.json').read_text())['payload_fixes'][MN]['cmdline']
        n = json.loads((N / 'build.json').read_text())['payload_fixes'][NN]['cmdline']
        self.assertEqual(n, m.replace('NAT165-scM', 'NAT167-scN'))
        r = load('nat167_reloc_t', ROOT / 'docs/procedures/nat-157/relocscan.py').scan(N / NN)
        self.assertEqual([(x['object'], x['allowed']) for x in r], [('00-start.S.o', True)])
        chk = load('nat167_chk_t', ROOT / 'docs/procedures/nat-150/check_loader_sites.py')
        res, consts = chk.run(N, NN)
        self.assertEqual(res, dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(chk.symbolize(ROOT / 'artifacts/nat-167/kernel-001', consts),
                         chk.symbolize(ROOT / 'artifacts/nat-143/kernel-001', consts))


class Session(unittest.TestCase):
    def test_counted_derivation(self):
        need(ROOT / 'artifacts/nat-167/package-001/package.json')
        text = load('nat167_derive_t', HERE / 'derive168.py').build()
        self.assertEqual((HERE / 'session_nat168.py').read_text(), text)
        img = json.loads((ROOT / 'artifacts/nat-167/package-001/package.json').read_text())['images'][NN]
        for s in (img['recovery_sha256'], img['payload_sha256'], "'NAT-167')", '*-nat168-%s-single-run-*.md'):
            self.assertIn(s, text)
        old = (ROOT / 'docs/procedures/nat-158/session_nat159.py').read_text().splitlines()
        self.assertEqual(sum(1 for l in difflib.unified_diff(old, text.splitlines(), lineterm='', n=0) if l[:1] == '+' and l[:3] != '+++'), 8)


if __name__ == '__main__':
    unittest.main()
