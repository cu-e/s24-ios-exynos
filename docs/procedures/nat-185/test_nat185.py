#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-185 host tests: the patched e1s_display.c (NAT-176's snapshot plus the process-time sampler) built against a simulated kernel
(host/shim185.h, host/fake185.c: processes with fixed CPU shares, one born at 252.5 s and gone at 300 s, optional idle fillers to
overflow the table, cpu0's idle counter at 20 % of the time); the printed spans, sums, kernel share, idle and top lists; the e1stop=0
switch; the patch relative to NAT-176's; the analyser top186.py."""
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_display.c'
PATCH = HERE / 'e1s_display.patch'
P176 = HERE.parent / 'nat-176/e1s_display.patch'


def patched(patch=PATCH):
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        t = Path(tmp) / 'e1s_display.c'
        t.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(t), str(patch)], check=True)
        return t.read_text()


def run(env=None, text=None):
    with tempfile.TemporaryDirectory(prefix='nat185-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        body = '\n'.join(l for l in (text or patched()).splitlines() if not l.startswith('#include'))
        src = tmp / 'd.c'
        src.write_text('#include "shim185.h"\nextern bool ml_cpu_idle_time(int cpu_id, uint64_t *idle);\n'
                       'extern uintptr_t ml_io_map(uintptr_t pa, uintptr_t size);\n' + body)
        exe = tmp / 'd'
        subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wno-unused-function', '-Wno-redundant-decls', '-Werror', '-I', str(HERE / 'host'),
                        str(src), str(HERE / 'host/fake185.c'), '-o', str(exe)], check=True)
        e = dict(os.environ, HOST_THREAD='0')
        e.update(env or {})
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=60, env=e)
        assert r.returncode == 0, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
        return r.stdout


def spans(out):
    return {int(m[1]): tuple(int(x) for x in m.groups()[1:]) for m in re.finditer(
        r'^e1s-top: (\d+) s span (\d+) us busy (\d+) us kernel (\d+) us idle0 (\d+) us procs (\d+) lost (\d+)$', out, re.M)}


def tops(out):
    return {int(m[1]): re.findall(r'(\S+)\[(-?\d+)\] (\d+)', m[2]) for m in re.finditer(r'^e1s-top: (\d+) s top(.*)$', out, re.M)}


class Sampler(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run()

    def test_windows(self):
        s = spans(self.out)
        self.assertEqual(sorted(s), list(range(205, 376, 5)))
        self.assertIn('e1s-top: done', self.out)
        for t, (span, busy, kernel, idle, procs, lost) in s.items():
            self.assertAlmostEqual(span, 5_000_000, delta=150_000)
            want = (0.78 + (0.05 if 255 < t < 300 else 0)) * span     # gone at 300: its last span is missing
            if t == 255:
                want = 0.78 * span + 0.05 * 2.5e6                     # born at 252.5: its whole life so far
            self.assertAlmostEqual(busy, want, delta=0.01 * span, msg=t)
            self.assertAlmostEqual(kernel, 0.10 * span, delta=0.005 * span)
            self.assertAlmostEqual(idle, 0.20 * span, delta=0.005 * span)
            self.assertEqual((procs, lost), (6 if 255 <= t < 300 else 5, 0), t)

    def test_top(self):
        tp = tops(self.out)
        self.assertEqual([n for n, _, _ in tp[220]], ['SpringBoard', 'backboardd', 'kernel_task', 'a-very-long-process', 'launchd'][:5])
        self.assertEqual([p for _, p, _ in tp[220]][:3], ['50', '40', '0'])
        self.assertEqual(tp[280][2][0], 'kernel_task')
        self.assertIn('mediaserverd', [n for n, _, _ in tp[280]])
        self.assertNotIn('mediaserverd', [n for n, _, _ in tp[310]])

    def test_overflow(self):
        s = spans(run({'HOST_FILLERS': '200'}))
        self.assertEqual(s[220][4:], (160, 45))

    def test_off_and_dpp_unchanged(self):
        out = run({'BOOTARG_e1stop': '0', 'HOST_THREAD': '9'})
        self.assertNotIn('e1s-top', out)
        self.assertIn('threads 1', out)
        out = run({'HOST_THREAD': '1'})
        self.assertIn('e1s-dpp: late', out)

    def test_mutants(self):
        text = patched()
        for o, n in (('e->total - e1s_top_old[j].total', 'e->total'),
                     ('if (e->pid == 0) {', 'if (e->pid == 1) {'),
                     ('e1s_top_new[i].delta > e1s_top_new[best].delta', 'e1s_top_new[i].delta < e1s_top_new[best].delta'),
                     ('e->delta = e->total;\n', 'e->delta = 0;\n')):
            self.assertEqual(text.count(o), 1, o)
            out = run(text=text.replace(o, n))
            ok = True
            try:
                s, tp = spans(out), tops(out)
                ok = abs(s[220][1] - 0.78 * s[220][0]) < 0.01 * s[220][0] and abs(s[220][2] - 0.1 * s[220][0]) < 0.005 * s[220][0] \
                    and [x[0] for x in tp[220]][:2] == ['SpringBoard', 'backboardd'] and abs(s[255][1] - 4.025e6) < 0.06e6
            except KeyError:
                ok = False
            self.assertFalse(ok, n)


class PatchScope(unittest.TestCase):
    def test_extends_176_without_register_access(self):
        a, b = patched(P176), patched()
        al, bl = a.splitlines(), b.splitlines()
        import difflib
        removed = [l for l in difflib.ndiff(al, bl) if l.startswith('- ')]
        self.assertEqual(removed, [])
        added = [l[2:] for l in difflib.ndiff(al, bl) if l.startswith('+ ')]
        self.assertFalse([l for l in added if 'ml_io_map' in l or 'volatile' in l or 'e1s_display_read' in l])


def _top186():
    spec = importlib.util.spec_from_file_location('t185_top186', HERE / 'top186.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Analyser(unittest.TestCase):
    def test_on_harness(self):
        r = _top186().analyse(run())
        self.assertEqual(r['verdict'], 'U-mid')
        self.assertEqual(r['top_over_swipes'][0]['name'], 'SpringBoard')
        self.assertAlmostEqual(r['top_over_swipes'][0]['share'], 0.40, delta=0.01)
        self.assertTrue(r['idle_counter_agrees'] is False or r['idle_counter_agrees'] is True)

    def test_verdicts(self):
        a = _top186()
        self.assertEqual(a.analyse('')['verdict'], 'U-none')
        line = 'e1s-top: %d s span 5000000 us busy %d us kernel 1 us idle0 0 us procs 9 lost 0\n'
        for busy, v in ((4600000, 'U-sat'), (4500000, 'U-sat'), (4499999, 'U-mid'), (3500000, 'U-mid'), (3499999, 'U-free')):
            self.assertEqual(a.analyse(''.join(line % (t, busy) for t in range(220, 260, 5)))['verdict'], v, busy)
        self.assertEqual(a.analyse(line % (200, 4900000))['verdict'], 'U-none')      # outside the swipe phase


if __name__ == '__main__':
    unittest.main()
