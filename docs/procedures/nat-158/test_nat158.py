"""NAT-158 host tests: scJ is scH with fb_filter=0 where the recording tokens were and NAT-157's loader fix, and nothing else.
The command line, the payload byte for byte outside the loader and the cmdline field, the loader objects, the loader's own checkpoint
check with the NAT-143 symbols, the relocation gate, the one-line change to NAT-145's check, and the counted session derivation."""
import difflib
import hashlib
import importlib.util
import inspect
import json
import sys
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
H = ROOT / 'artifacts/nat-152/build-001'
J = ROOT / 'artifacts/nat-158/build-001'
HN, JN = 'loader-diag-xnu-scH-md1', 'loader-diag-xnu-scJ-md1'
LOADER_BYTES = 446464     # Image.payload = the loader Image, then payload.adt8.bin (checked below)


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


class CommandLine(unittest.TestCase):
    def test_recording_replaced_in_place(self):
        need(H / 'build.json', J / 'build.json')
        h, j = cmdline(H, HN), cmdline(J, JN)
        self.assertEqual(j, h.replace('rec_secs=270 rec_mb=64', 'fb_filter=0').replace('nat_attempt=NAT152-scH', 'nat_attempt=NAT158-scJ'))
        t = j.split()
        self.assertEqual(t.count('fb_filter=0'), 1)
        self.assertFalse([x for x in t if x.startswith(('rec_', 'fb_threads', 'fbscale', 'fb_hz', 'fb_beat'))])
        self.assertEqual([x for x in h.split() if x not in t], ['nat_attempt=NAT152-scH', 'rec_secs=270', 'rec_mb=64'])
        self.assertEqual(len(j.encode()), 242)

    def test_nat145_check_one_line(self):
        b = load('nat158_build_t', HERE / 'build.py')
        old = textwrap.dedent(inspect.getsource(b.b145.main)).splitlines()
        new = b.main145_source().splitlines()
        changed = [l for l in difflib.unified_diff(old, new, lineterm='', n=0) if l[:1] in '+-' and l[:3] not in ('+++', '---')]
        self.assertEqual(changed, ['-' + b.CHECK145_OLD.rstrip('\n'), '+' + b.CHECK145_NEW.rstrip('\n')])
        self.assertIs(b.make_main145().__globals__, vars(b.b145))


class Payload(unittest.TestCase):
    def test_only_loader_and_cmdline_field_differ(self):
        need(H / HN / 'Image.payload', J / JN / 'Image.payload')
        for d, n in ((H, HN), (J, JN)):
            p, a = (d / n / 'Image.payload').read_bytes(), (d / n / 'payload.adt8.bin').read_bytes()
            self.assertEqual(p[LOADER_BYTES:], a)
        ph, pj = (H / HN / 'Image.payload').read_bytes(), (J / JN / 'Image.payload').read_bytes()
        self.assertEqual(len(ph), len(pj))
        ah, aj = ph[LOADER_BYTES:], pj[LOADER_BYTES:]
        start = ah.index(b'rd=md1 ')
        self.assertEqual(start, aj.index(b'rd=md1 '))
        field = ah.index(b'\0', start) + 1
        while ah[field] == 0 and aj[field] == 0 and field < start + 256:
            field += 1
        self.assertLessEqual(field - start, 256)
        self.assertEqual(ah[field:], aj[field:])           # kernel, ramdisk, ADT: every byte after the cmdline field
        self.assertEqual(ah[:start], aj[:start])
        self.assertEqual(aj[start:start + 242], cmdline(J, JN).encode())
        self.assertEqual(set(aj[start + 242:field]), {0})

    def test_loader_objects(self):
        need(H / HN / '10-ckpt3.c.o', J / JN / '10-ckpt3.c.o')
        diff = sorted(p.name for p in (J / JN).glob('[0-9][0-9]-*.o')
                      if hashlib.sha256(p.read_bytes()).digest() != hashlib.sha256((H / HN / p.name).read_bytes()).digest())
        # markerlib52 carries the image name (nat-052/build.py: -DNAT047_TAG="NAME", same length); ckpt3 the NAT-157 fix
        self.assertEqual(diff, ['08-markerlib52.c.o', '10-ckpt3.c.o'])
        self.assertIn('static const char site[6][40]', (J / JN / 'source/shim/e1s-xnu/ckpt3.c').read_text())

    def test_relocations(self):
        need(J / JN / '00-start.S.o')
        r = load('nat158_reloc_t', ROOT / 'docs/procedures/nat-157/relocscan.py').scan(J / JN)
        self.assertEqual([(x['object'], x['symbol']) for x in r], [('00-start.S.o', '_payload_start')])
        self.assertTrue(all(x['allowed'] for x in r))

    def test_loader_checkpoint_check(self):
        need(J / 'build.json')
        chk = load('nat158_chk_t', ROOT / 'docs/procedures/nat-150/check_loader_sites.py')
        res, consts = chk.run(J, JN)
        self.assertEqual(res, dict(rc=0, verdict='ok', bad=0))
        self.assertEqual(chk.symbolize(ROOT / 'artifacts/nat-152/kernel-001', consts),
                         chk.symbolize(ROOT / 'artifacts/nat-143/kernel-001', consts))


class Session(unittest.TestCase):
    def test_counted_derivation(self):
        need(ROOT / 'artifacts/nat-158/package-001/package.json')
        d = load('nat158_derive_t', HERE / 'derive159.py')
        text = d.build()
        self.assertEqual((HERE / 'session_nat159.py').read_text(), text)
        img = json.loads((ROOT / 'artifacts/nat-158/package-001/package.json').read_text())['images'][JN]
        for s in (img['recovery_sha256'], img['payload_sha256'], "'NAT-158')", '*-nat159-%s-single-run-*.md'):
            self.assertIn(s, text)
        old = (ROOT / 'docs/procedures/nat-152/session_nat153.py').read_text().splitlines()
        changed = sum(1 for l in difflib.unified_diff(old, text.splitlines(), lineterm='', n=0) if l[:1] == '+' and l[:3] != '+++')
        self.assertEqual(changed, 8)


if __name__ == '__main__':
    unittest.main()
