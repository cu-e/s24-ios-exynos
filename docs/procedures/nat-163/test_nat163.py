"""NAT-163 host tests: scL is scJ with touch_lat=1 and nothing else (command line, payload after the cmdline field, loader objects,
gates, counted session), the kernel carries the driver's tl formats, and tl164.py decodes synthetic lines in those exact formats."""
import difflib
import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
J = ROOT / 'artifacts/nat-158/build-001'
L = ROOT / 'artifacts/nat-163/build-001'
JN, LN = 'loader-diag-xnu-scJ-md1', 'loader-diag-xnu-scL-md1'
LOADER_BYTES = 446464


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


T = load('nat163_tl', HERE / 'tl164.py')


def cmdline(build, name):
    return json.loads((build / 'build.json').read_text())['payload_fixes'][name]['cmdline']


class Image(unittest.TestCase):
    def test_cmdline(self):
        need(J / 'build.json', L / 'build.json')
        j, l = cmdline(J, JN), cmdline(L, LN)
        self.assertEqual(l, j.replace('fb_filter=0 ', 'fb_filter=0 touch_lat=1 ').replace('NAT158-scJ', 'NAT163-scL'))
        self.assertEqual(len(l.encode()), 254)

    def test_payload_and_objects(self):
        need(J / JN / 'Image.payload', L / LN / 'Image.payload')
        aj, al = (J / JN / 'payload.adt8.bin').read_bytes(), (L / LN / 'payload.adt8.bin').read_bytes()
        self.assertEqual((L / LN / 'Image.payload').read_bytes()[LOADER_BYTES:], al)
        start = aj.index(b'rd=md1 ')
        self.assertEqual(aj[:start], al[:start])
        self.assertEqual(aj[start + 256:], al[start + 256:])
        self.assertEqual(al[start:start + 254], cmdline(L, LN).encode())
        diff = sorted(p.name for p in (L / LN).glob('[0-9][0-9]-*.o')
                      if hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256((J / JN / p.name).read_bytes()).digest())
        self.assertEqual(diff, ['08-markerlib52.c.o'])

    def test_gates(self):
        need(L / 'build.json')
        r = load('nat163_reloc_t', ROOT / 'docs/procedures/nat-157/relocscan.py').scan(L / LN)
        self.assertEqual([(x['object'], x['allowed']) for x in r], [('00-start.S.o', True)])
        chk = load('nat163_chk_t', ROOT / 'docs/procedures/nat-150/check_loader_sites.py')
        res, consts = chk.run(L, LN)
        self.assertEqual(res, dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(chk.symbolize(ROOT / 'artifacts/nat-152/kernel-001', consts),
                         chk.symbolize(ROOT / 'artifacts/nat-143/kernel-001', consts))

    def test_kernel_has_the_formats(self):
        k = ROOT / 'artifacts/nat-152/kernel-001/kernel.no-storage'
        need(k)
        data = k.read_bytes()
        for f in (b'tl: s %u at %llu\n', b'tl: v %u ready %llu shown %llu done %llu\n', b'tl: p %u %u %u %u at %llu\n', b'touch_lat'):
            self.assertIn(f, data)


class Decoder(unittest.TestCase):
    def test_synthetic(self):
        lines = []
        t = 10_000_000
        for i in range(1, 21):                       # idle: one swap every 100 ms, frame ready +1 ms, shown +2 ms, done +28 ms
            lines += ['[  10.0]: tl: s %d at %d' % (i, t), '[  10.0]: tl: v %d ready %d shown %d done %d' % (i, t + 1000, t + 2000, t + 28000)]
            t += 100_000
        t += 5_000_000
        for i in range(21, 41):                      # touch: a sample, then a swap every 50 ms
            lines += ['[  20.0]: tl: p 1 0 500 900 at %d' % (t - 3000), '[  20.0]: tl: s %d at %d' % (i, t),
                      '[  20.0]: tl: v %d ready %d shown %d done %d' % (i, t + 1000, t + 1000, t + 27000)]
            t += 50_000
        r = T.analyse('\n'.join(lines) + '\n')
        self.assertEqual((r['swaps'], r['frames'], r['touch_samples']), (40, 40, 20))
        self.assertEqual(r['idle']['swaps'], 20)
        self.assertEqual(r['idle']['swap_interval']['median'], 100.0)
        self.assertEqual(r['idle']['copy']['median'], 26.0)
        self.assertEqual(r['idle']['beat_wait']['median'], 1.0)
        self.assertEqual(r['idle']['swap_to_done']['median'], 28.0)
        self.assertEqual(r['touch']['swap_interval']['median'], 50.0)
        self.assertEqual(r['touch_to_panel']['median'], 30.0)       # 3 ms to the swap + 27 ms to done
        self.assertEqual(r['idle']['share_60hz'], 0.0)

    def test_real_line_shapes(self):
        """A dump line as kl_reader2 prints it: timestamp prefix, then the driver's text."""
        r = T.analyse('[  352.169451]: tl: s 7 at 352169000\n[  352.195000]: tl: v 7 ready 352170000 shown 352170000 done 352196000\n')
        self.assertEqual((r['swaps'], r['frames']), (1, 1))
        self.assertEqual(r['idle']['copy']['median'], 26.0)


class Session(unittest.TestCase):
    def test_counted_derivation(self):
        need(ROOT / 'artifacts/nat-163/package-001/package.json')
        text = load('nat163_derive_t', HERE / 'derive164.py').build()
        self.assertEqual((HERE / 'session_nat164.py').read_text(), text)
        img = json.loads((ROOT / 'artifacts/nat-163/package-001/package.json').read_text())['images'][LN]
        for s in (img['recovery_sha256'], img['payload_sha256'], "'NAT-163')", '*-nat164-%s-single-run-*.md'):
            self.assertIn(s, text)
        old = (ROOT / 'docs/procedures/nat-158/session_nat159.py').read_text().splitlines()
        self.assertEqual(sum(1 for l in difflib.unified_diff(old, text.splitlines(), lineterm='', n=0) if l[:1] == '+' and l[:3] != '+++'), 8)


if __name__ == '__main__':
    unittest.main()
