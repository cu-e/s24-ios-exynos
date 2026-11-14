"""NAT-157 host tests: the rewritten nat036_msg() returns the same string as the table version for every rc and bad, the fixed ckpt3.c
compiled with the loader's flags carries no absolute relocation, relocscan finds the six in the scH image's object and allows the
header's, and wrap_cc() fixes ckpt3.c only, before compiling it."""
import ctypes
import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
IMAGE = ROOT / 'artifacts/nat-152/build-001/loader-diag-xnu-scH-md1'
TREE = IMAGE / 'source/shim/e1s-xnu'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


F = load('nat157_fix', HERE / 'fix_msg.py')
R = load('nat157_reloc', HERE / 'relocscan.py')
B22 = load('nat157_b22', ROOT / 'docs/procedures/nat-022/build.py') if (ROOT / 'docs/procedures/nat-022/build.py').exists() else None


def need(*paths):
    for p in paths:
        if not p.exists():
            raise unittest.SkipTest('%s missing' % p)


def host_lib(src_dir, ckpt3_text, t):
    """nat036_msg() alone (in ckpt3.c it is under #ifndef NAT031_HOST), with the rc values of the tree's own headers."""
    import re
    d = Path(t) / ('t%d' % len(list(Path(t).iterdir())))
    d.mkdir()
    # the two rc enums as the tree's headers define them (ckpt.h: nat031_rc; ckpt3.h: nat036_rc), turned into #defines
    pairs = [m for h in ('ckpt.h', 'ckpt3.h') for m in re.findall(r'\b(NAT0(?:31|36|59)_\w+_BAD|NAT036_OK)\s*=\s*(\d+)',
                                                                   (Path(src_dir) / h).read_text())]
    defs = ''.join('#define %s %s\n' % p for p in sorted(set(pairs)))
    fn = ckpt3_text[ckpt3_text.index('const char *nat036_msg('):]
    fn = fn[:fn.index('\n}\n') + 3]
    (d / 'm.c').write_text('#include <stdint.h>\n' + defs + fn)
    so = d / 'lib.so'
    subprocess.run(['cc', '-O2', '-Wall', '-Werror', '-shared', '-fPIC', str(d / 'm.c'), '-o', str(so)], check=True, capture_output=True)
    lib = ctypes.CDLL(str(so))
    lib.nat036_msg.restype = ctypes.c_char_p
    lib.nat036_msg.argtypes = [ctypes.c_int, ctypes.c_uint32]
    return lib, defs


class Messages(unittest.TestCase):
    def test_same_string_for_every_rc_and_bad(self):
        need(TREE / 'ckpt3.c')
        old = (TREE / 'ckpt3.c').read_text()
        with tempfile.TemporaryDirectory() as t:
            (a, defs), (b, _) = host_lib(TREE, old, t), host_lib(TREE, F.fix_text(old), t)
            self.assertEqual(defs.count('#define'), 9, defs)      # OK and eight failure codes
            n = 0
            for rc in range(-2, 12):
                for bad in (0, 1, 2, 3, 4, 5, 6, 7, 99, 0xffffffff):
                    self.assertEqual(a.nat036_msg(rc, bad), b.nat036_msg(rc, bad), (rc, bad))
                    n += 1
            self.assertEqual(b.nat036_msg(2, 1), b'XNU checkpoint site 1 check failed')   # NAT031_SITE_BAD, site 1: NAT-151's case
            self.assertEqual(n, 140)

    def test_refuses_unknown_text(self):
        with self.assertRaises(SystemExit):
            F.fix_text('const char *nat036_msg(int rc, uint32_t bad) { return 0; }')
        need(TREE / 'ckpt3.c')
        with self.assertRaises(SystemExit):
            F.fix_text(F.fix_text((TREE / 'ckpt3.c').read_text()))      # not twice


class Relocations(unittest.TestCase):
    def test_scH_image_has_the_six(self):
        need(IMAGE / '10-ckpt3.c.o')
        found = R.scan(IMAGE)
        bad = [r for r in found if not r['allowed']]
        self.assertEqual([(r['object'], r['section'], r['type']) for r in bad], [('10-ckpt3.c.o', '.rela.rodata', 'R_AARCH64_ABS64')] * 6)
        self.assertEqual([(r['object'], r['symbol']) for r in found if r['allowed']], [('00-start.S.o', '_payload_start')])

    def test_fixed_ckpt3_compiles_without_absolute_relocations(self):
        """With the loader's own flags (nat-022 FLAGS without -Werror, NO_SIMD, the stop macro), as nat-052/build.py compiles it."""
        need(TREE / 'ckpt3.c')
        if B22 is None or shutil.which('zig') is None:
            raise unittest.SkipTest('zig or nat-022/build.py missing')
        b36 = load('nat157_b36', ROOT / 'docs/procedures/nat-036/build.py')
        flags = [f for f in B22.FLAGS if f not in ('-Werror', '-mgeneral-regs-only')] + B22.NO_SIMD
        with tempfile.TemporaryDirectory() as t:
            d = Path(t) / 'e'
            shutil.copytree(TREE, d)
            out = {}
            for name, text in (('old', (d / 'ckpt3.c').read_text()), ('new', F.fix_text((d / 'ckpt3.c').read_text()))):
                (d / 'ckpt3.c').write_text(text)
                obj = Path(t) / ('10-%s.o' % name)
                subprocess.run(['zig', 'cc', *flags, b36.stop_macro(b36.DEFAULT_STOPS), '-I%s' % d, '-c', str(d / 'ckpt3.c'), '-o', str(obj)],
                               check=True, capture_output=True)
                rel = subprocess.run(['readelf', '-rW', str(obj)], capture_output=True, text=True, check=True).stdout
                out[name] = sum(1 for l in rel.splitlines() if 'R_AARCH64_ABS' in l)
            self.assertEqual(out, {'old': 6, 'new': 0})


class Hook(unittest.TestCase):
    def test_wrap_cc_fixes_ckpt3_only(self):
        need(TREE / 'ckpt3.c')
        calls = []
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            shutil.copy(TREE / 'ckpt3.c', d / 'ckpt3.c')
            (d / 'ckpt.c').write_text('/* untouched */\n')
            cc = F.wrap_cc(lambda src, obj, extra, inc: calls.append((Path(src).name, Path(src).read_text())))
            cc(d / 'ckpt.c', d / 'a.o', [], [d])
            cc(d / 'ckpt3.c', d / 'b.o', [], [d])
            self.assertEqual(calls[0], ('ckpt.c', '/* untouched */\n'))
            self.assertEqual(calls[1][0], 'ckpt3.c')
            self.assertIn('NAT-157: the characters themselves', calls[1][1])
            self.assertNotIn('static const char *const site[]', calls[1][1]); self.assertIn('static const char site[6][40]', calls[1][1])
            self.assertTrue(cc.nat157)


if __name__ == '__main__':
    unittest.main()
