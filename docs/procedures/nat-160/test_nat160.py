"""NAT-160 host tests: scK is scJ with fbscale=2 and nothing else. The command line, the payload byte for byte after the cmdline field,
the loader objects (only the compiled-in image name), the loader's checkpoint check with the NAT-143 symbols, the relocation gate, the
driver source's fbscale handling at the pinned SHA, and the counted session derivation."""
import difflib
import hashlib
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
J = ROOT / 'artifacts/nat-158/build-001'
K = ROOT / 'artifacts/nat-160/build-001'
JN, KN = 'loader-diag-xnu-scJ-md1', 'loader-diag-xnu-scK-md1'
LOADER_BYTES = 446464
DRIVER = 'xnu/hackios/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp'


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


def cmdline(build, name):
    return json.loads((build / 'build.json').read_text())['payload_fixes'][name]['cmdline']


class Image(unittest.TestCase):
    def test_cmdline(self):
        need(J / 'build.json', K / 'build.json')
        j, k = cmdline(J, JN), cmdline(K, KN)
        self.assertEqual(k, j.replace('fb_filter=0 ', 'fb_filter=0 fbscale=2 ').replace('NAT158-scJ', 'NAT160-scK'))
        self.assertEqual([t for t in k.split() if t not in j.split()], ['nat_attempt=NAT160-scK', 'fbscale=2'])
        self.assertEqual(len(k.encode()), 252)

    def test_payload_after_cmdline_field(self):
        need(J / JN / 'Image.payload', K / KN / 'Image.payload')
        pj, pk = (J / JN / 'Image.payload').read_bytes(), (K / KN / 'Image.payload').read_bytes()
        self.assertEqual(len(pj), len(pk))
        aj, ak = pj[LOADER_BYTES:], pk[LOADER_BYTES:]
        self.assertEqual(aj, (J / JN / 'payload.adt8.bin').read_bytes())
        self.assertEqual(ak, (K / KN / 'payload.adt8.bin').read_bytes())
        start = aj.index(b'rd=md1 ')
        self.assertEqual(start, ak.index(b'rd=md1 '))
        self.assertEqual(aj[:start], ak[:start])
        self.assertEqual(ak[start:start + 252], cmdline(K, KN).encode())
        self.assertEqual(aj[start + 256:], ak[start + 256:])
        self.assertEqual(set(ak[start + 252:start + 256]), {0})

    def test_loader_objects(self):
        need(J / JN / '10-ckpt3.c.o', K / KN / '10-ckpt3.c.o')
        diff = sorted(p.name for p in (K / KN).glob('[0-9][0-9]-*.o')
                      if hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256((J / JN / p.name).read_bytes()).digest())
        self.assertEqual(diff, ['08-markerlib52.c.o'])     # -DNAT047_TAG="NAME"

    def test_gates(self):
        need(K / 'build.json')
        r = load('nat160_reloc_t', ROOT / 'docs/procedures/nat-157/relocscan.py').scan(K / KN)
        self.assertEqual([(x['object'], x['symbol'], x['allowed']) for x in r], [('00-start.S.o', '_payload_start', True)])
        chk = load('nat160_chk_t', ROOT / 'docs/procedures/nat-150/check_loader_sites.py')
        res, consts = chk.run(K, KN)
        self.assertEqual(res, dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(chk.symbolize(ROOT / 'artifacts/nat-152/kernel-001', consts),
                         chk.symbolize(ROOT / 'artifacts/nat-143/kernel-001', consts))


class Driver(unittest.TestCase):
    def test_fbscale_source(self):
        """fbscale=2 makes the reported size 375x812 points at 2 px and publishes the scale in the device tree (pinned SHA)."""
        src = subprocess.run(['git', '-C', str(ROOT / 'references/s24-port'), 'show', 'c8860decc62c6d6180e609036d027a2997972420:' + DRIVER],
                             capture_output=True, text=True)
        if src.returncode:
            raise unittest.SkipTest('references/s24-port at the pinned SHA missing')
        t = src.stdout
        for s in ('static TUNABLE(uint32_t, gFBScale, "fbscale", 0);', '#define kFBPointsWide           375',
                  '#define kFBPointsHigh           812', 'fWidth = kFBPointsWide * scale;', 'fHeight = kFBPointsHigh * scale;',
                  '{ "/chosen", "display-scale" }, { "/product", "artwork-scale-factor" }'):
            self.assertIn(s, t)


class Session(unittest.TestCase):
    def test_counted_derivation(self):
        need(ROOT / 'artifacts/nat-160/package-001/package.json')
        text = load('nat160_derive_t', HERE / 'derive161.py').build()
        self.assertEqual((HERE / 'session_nat161.py').read_text(), text)
        img = json.loads((ROOT / 'artifacts/nat-160/package-001/package.json').read_text())['images'][KN]
        for s in (img['recovery_sha256'], img['payload_sha256'], "'NAT-160')", '*-nat161-%s-single-run-*.md'):
            self.assertIn(s, text)
        old = (ROOT / 'docs/procedures/nat-158/session_nat159.py').read_text().splitlines()
        self.assertEqual(sum(1 for l in difflib.unified_diff(old, text.splitlines(), lineterm='', n=0) if l[:1] == '+' and l[:3] != '+++'), 8)


if __name__ == '__main__':
    unittest.main()
