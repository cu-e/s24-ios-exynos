#!/usr/bin/env python3
"""NAT-115 host tests: analyze116.py on synthetic kernel texts built from the line formats the patched kernel prints (format
strings read from the committed patch, so a change of the kernel's wording breaks these tests), plus the real NAT-113 run as the
'no feed' control. Run: python3 -B -I docs/procedures/nat-115/test_nat115.py"""
import json, re, subprocess, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import analyze116 as A  # noqa: E402

PATCH = (HERE/'kernel-combined.patch').read_text()
NAT113_TEXT = ROOT/'artifacts/nat-113/analysis/kernel-text.txt'
NAT113_PIX = ROOT/'artifacts/nat-113/analysis/pixels.json'


def cfmt(fmt, *args):
    """Render a C printf format (the subset the kernel lines use) with python values: drop ll/l length modifiers, %u -> %d."""
    py = re.sub(r'%(0?\d*)l{1,2}([xdu])', r'%\1\2', fmt).replace('%u', '%d')
    py = re.sub(r'%(0?\d*)u', r'%\1d', py)
    return py % args


def kernel_fmt(prefix):
    """The format string of the kernel printf whose (concatenated) literal starts with `prefix`, as it is in the patch."""
    src = '\n'.join(l[1:] for l in PATCH.splitlines() if l.startswith('+'))
    for m in re.finditer(r'printf\(((?:\s*"(?:[^"\\]|\\.)*")+)', src):
        s = ''.join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
        if s.startswith(prefix):
            return s.encode().decode('unicode_escape').rstrip('\n')
    raise AssertionError('no kernel line starting with %r' % prefix)


FED = kernel_fmt('e1s_wdt: fed every 10 s')
CUT = kernel_fmt('e1s_wdt: loader_return_after %u cut')
PROC = kernel_fmt('waitdump: %s[%d] threads')
THR = kernel_fmt('waitdump: %s[%d] t%u tid')


def thread_line(name, pid, n, state, hint, owner=0, ts='-', ts_ctx=0, svc='', cpu=(0, 50, 0, 10)):
    return cfmt(THR, name, pid, n, 1000 + n, state, hint, 31, cpu[0], cpu[1], cpu[2], cpu[3], 0x1a2b, 0x3c4d, owner, 0, ts, ts_ctx, 0, svc)


def text(fed=True, cut=False, expired=True, threads=(), procs=()):
    ls = ['[  186.0]: boot']
    if fed:
        ls.append(cfmt(FED, 155, 0x21, 65355, 60000, 65350))
    if cut:
        ls.append(cfmt(CUT, 150, 63))
    ls += ['[  229.033253]: MiniIOMobileFramebuffer: swap 1 (#0): surfaces 2 0 0 0, layers set 0x80000007 cleared 0x80000006']
    if expired:
        ls.append('--- loader_return_after expired ---')
        ls.append('waitdump: begin at 123')
        for name, pid in procs:
            ls.append(cfmt(PROC, name, pid, 5, 0, 0))
        ls += list(threads)
        ls.append('waitdump: end')
    return '\n'.join(ls) + '\n'


PIX_LOGO = dict(complete=True, frames=[dict(f=0, ns=0, nzb=9816, of=913500, fnv=A.LOGO_FNV)] * 3)
PIX_NEW = dict(complete=True, frames=[dict(f=0, ns=0, nzb=9816, of=913500, fnv=A.LOGO_FNV), dict(f=1, ns=5, nzb=400000, of=913500, fnv=0x1234)])


class Analyse(unittest.TestCase):
    def run_a(self, t, pix):
        return A.classify(A.parse(t), pix)

    def test_formats_parse(self):
        r = A.parse(text(threads=[thread_line('SpringBoard', 13, 0, 0x1, 2, owner=25, svc='com.apple.lsd.mapdb')],
                         procs=[('SpringBoard', 13), ('lsd', 25)]))
        self.assertEqual(r['fed'], 155)
        self.assertEqual(len(r['threads']), 1)
        self.assertEqual(r['threads'][0]['owner'], 25)
        self.assertEqual(r['threads'][0]['svc'], 'com.apple.lsd.mapdb')
        self.assertEqual(r['procs'][25]['name'], 'lsd')

    def test_no_feed_is_x_window(self):
        for kw in (dict(fed=False), dict(cut=True), dict(expired=False)):
            with self.subTest(kw=kw):
                self.assertEqual(self.run_a(text(**kw), PIX_LOGO)['verdict'], 'X-window')
        self.assertEqual(self.run_a(text(), dict(complete=False))['verdict'], 'X-window')

    def test_new_frame_is_h1(self):
        self.assertEqual(self.run_a(text(), PIX_NEW)['verdict'], 'H1-frame')

    def test_logo_frames_are_not_new(self):
        """Only NAT-113's logo hash (0xd5b719ed) counts as 'the logo'; frames with it are not new."""
        self.assertNotEqual(self.run_a(text(), PIX_LOGO)['verdict'], 'H1-frame')
        pix = dict(complete=True, frames=[dict(f=0, ns=0, nzb=9816, of=913500, fnv=0xd5b719ee)])
        self.assertEqual(self.run_a(text(), pix)['verdict'], 'H1-frame')

    def test_empty_frame_is_not_new(self):
        """A recorded frame with no non-zero bytes (black) is not a new picture."""
        pix = dict(complete=True, frames=[dict(f=0, ns=0, nzb=0, of=913500, fnv=0x811c9dc5)])
        self.assertNotEqual(self.run_a(text(), pix)['verdict'], 'H1-frame')

    def test_logo_only_runnable_is_h2(self):
        t = text(threads=[thread_line('SpringBoard', 13, 0, 0x4, 0)], procs=[('SpringBoard', 13)])
        self.assertEqual(self.run_a(t, PIX_LOGO)['verdict'], 'H2-cpu')

    def test_waits_on_daemon_is_h3(self):
        t = text(threads=[thread_line('SpringBoard', 13, 0, 0x1, 2, owner=25, svc='com.apple.lsd.mapdb')], procs=[('SpringBoard', 13), ('lsd', 25)])
        v = self.run_a(t, PIX_LOGO)
        self.assertEqual(v['verdict'], 'H3-wait')
        self.assertEqual(v['waits_on']['name'], 'lsd')

    def test_turnstile_owner_is_h3(self):
        t = text(threads=[thread_line('SpringBoard', 13, 0, 0x1, 16, ts='P', ts_ctx=17)], procs=[('SpringBoard', 13), ('containermanagerd', 17)])
        v = self.run_a(t, PIX_LOGO)
        self.assertEqual((v['verdict'], v['waits_on']['name']), ('H3-wait', 'containermanagerd'))

    def test_waits_on_backboardd_is_h4(self):
        t = text(threads=[thread_line('SpringBoard', 13, 0, 0x1, 2, owner=16)], procs=[('SpringBoard', 13), ('backboardd', 16)])
        self.assertEqual(self.run_a(t, PIX_LOGO)['verdict'], 'H4-display')

    def test_backboardd_on_framebuffer_is_h4(self):
        t = text(threads=[thread_line('SpringBoard', 13, 0, 0x1, 2), thread_line('backboardd', 16, 0, 0x1, 2, svc='IOMobileFramebuffer')],
                 procs=[('SpringBoard', 13), ('backboardd', 16)])
        self.assertEqual(self.run_a(t, PIX_LOGO)['verdict'], 'H4-display')

    def test_unreadable_wait_is_x_none(self):
        t = text(threads=[thread_line('SpringBoard', 13, 0, 0x1, 2)], procs=[('SpringBoard', 13)])
        self.assertEqual(self.run_a(t, PIX_LOGO)['verdict'], 'X-none')
        self.assertEqual(self.run_a(text(), PIX_LOGO)['verdict'], 'X-none')

    def test_thread_order_uses_first_thread(self):
        t = text(threads=[thread_line('SpringBoard', 13, 1, 0x4, 0), thread_line('SpringBoard', 13, 0, 0x1, 2, owner=25)],
                 procs=[('SpringBoard', 13), ('lsd', 25)])
        self.assertEqual(self.run_a(t, PIX_LOGO)['verdict'], 'H3-wait')

    @unittest.skipUnless(NAT113_TEXT.exists() and NAT113_PIX.exists(), 'NAT-113 run artifacts absent')
    def test_real_nat113_run_is_x_window(self):
        """NAT-113's kernel had no feed: the analyser must refuse to read H1-H4 from it."""
        v = A.classify(A.parse(NAT113_TEXT.read_text(errors='replace')), json.load(open(NAT113_PIX)))
        self.assertEqual(v['verdict'], 'X-window')
        self.assertEqual(len(A.parse(NAT113_TEXT.read_text(errors='replace'))['swaps']), 3)


class Build(unittest.TestCase):
    def test_derived_driver(self):
        r = subprocess.run([sys.executable, '-B', '-I', str(HERE/'derive115.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_feed_tests_pass_on_combined_patch(self):
        """NAT-071's tests on the combined patch (feed + wait dump) applied to the original source."""
        orig = ROOT/'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/osfmk/arm64/loader_return.c'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'loader_return.c'
            p.write_bytes(orig.read_bytes())
            subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(p), str(HERE/'kernel-combined.patch')], check=True)
            r = subprocess.run([sys.executable, '-B', '-I', str(ROOT/'docs/procedures/nat-071/test_nat071.py'), '--src', str(p)],
                               capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-2000:])

    def test_combined_is_feed_plus_dump(self):
        """kernel-combined.patch = NAT-071's feed patch + 0002-wait-dump.patch (no other change)."""
        orig = ROOT/'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/osfmk/arm64/loader_return.c'
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d)/'a.c', Path(d)/'b.c'
            a.write_bytes(orig.read_bytes()); b.write_bytes(orig.read_bytes())
            subprocess.run(['patch', '-s', str(a), str(ROOT/'docs/procedures/nat-071/0001-e1s-wdt-pet.patch')], check=True)
            subprocess.run(['patch', '-s', str(a), str(HERE/'0002-wait-dump.patch')], check=True)
            subprocess.run(['patch', '-s', str(b), str(HERE/'kernel-combined.patch')], check=True)
            self.assertEqual(a.read_bytes(), b.read_bytes())

    @unittest.skipUnless((ROOT/'artifacts/nat-115/build-001/build.json').exists(), 'build absent')
    def test_build_record(self):
        d = json.loads((ROOT/'artifacts/nat-115/build-001/build.json').read_text())
        c = d['nat115_changes']
        self.assertEqual(c['kernel_swaps'], 1)
        self.assertLess(c['cmdline_bytes'], 256)
        for t in ('loader_return_after=150', 'e1s_wdt_pet=1', 'wait_dump=1', 'rec_secs=150', 'nat_attempt=NAT115-sc4', 'cpus=1'):
            self.assertEqual(c['cmdline'].split().count(t), 1, t)
        self.assertEqual(d['nat079_params']['deadline_s'], 475)
        k = json.loads((ROOT/'artifacts/nat-115/kernel-001/rebuild.json').read_text())
        self.assertEqual(c['kernel_no_storage_sha256'], k['no_storage_sha256'])
        payload = (ROOT/'artifacts/nat-115/build-001/loader-diag-xnu-sc4-md1/Image.payload').read_bytes()
        for s in (b'e1s_wdt: fed every 10 s for', b'waitdump: %s[%d] t%u tid', c['cmdline'].encode()):
            self.assertEqual(payload.count(s), 1, s)


if __name__ == '__main__':
    unittest.main(verbosity=1)
