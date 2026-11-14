#!/usr/bin/env python3
"""NAT-174 host checks of the swipe thread (e1s_touch.c = original + docs/procedures/nat-174/e1s_touch_combined.patch).

1. NAT-169's pin-level peer cases on the new patch: the event thread's frames, DAT writes and posts are unchanged (the swipe thread
   starts after the event thread, which never returns in that harness).
2. host/clock174.c: e1s_swipe_thread() alone on a simulated clock; every post with its time. Synthetic.
"""
import importlib.util
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
P174 = HERE / 'e1s_touch_combined.patch'
spec = importlib.util.spec_from_file_location('t169', ROOT / 'docs/procedures/nat-169/test_nat169.py')
t169 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t169)
CLOCK = ('static uint64_t host_clock;\nstatic inline uint64_t mach_absolute_time(void) { return host_clock; }\n'
         'static inline void absolutetime_to_nanoseconds(uint64_t a, uint64_t *n) { *n = a; }\n')


def run_peer(patch, **kw):
    """t169.run_case with the clock shim the new code needs (it is never called in that harness)."""
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        p = Path(tmp) / 'p.patch'
        p.write_text(Path(patch).read_text())
        saved = t169.run_case.__globals__['HOST']
        try:
            # a shim.h that includes NAT-121's and adds the clock functions
            shim = Path(tmp) / 'shim.h'
            shim.write_text('#include "%s"\n%s' % (saved / 'shim.h', CLOCK))
            t169.run_case.__globals__['HOST'] = Path(tmp)
            return t169.run_case(p, **kw)
        finally:
            t169.run_case.__globals__['HOST'] = saved


def run_clock(swipe=None):
    with tempfile.TemporaryDirectory(prefix='nat174-', dir=os.environ.get('TMPDIR')) as tmp:
        tmp = Path(tmp)
        src = tmp / 't.c'
        src.write_text(t169.ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(src), str(P174)], check=True)
        text = '\n'.join(l for l in src.read_text().splitlines() if not l.startswith('#include'))
        for o, n in (('return *(volatile uint32_t *)reg;', 'return host_rd(reg);'),
                     ('*(volatile uint32_t *)reg = value;', 'host_wr(reg, value);')):
            text = text.replace(o, n)
        pre = ('#include "shim.h"\nuint32_t host_rd(uintptr_t); void host_wr(uintptr_t,uint32_t);\n'
               'extern uint64_t host_ns; void host_delay(uint64_t, uint64_t);\n#define delay_for_interval host_delay\n'
               'static inline uint64_t mach_absolute_time(void) { return host_ns; }\n'
               'static inline void absolutetime_to_nanoseconds(uint64_t a, uint64_t *n) { *n = a; }\n')
        text += ('\nint main(void) { PE_parse_boot_argn("e1stouch_swipe", &e1s_swipe, 4); '
                 'if (e1s_swipe) e1s_swipe_thread(0, 0); printf("RESULT off\\n"); return 0; }\n')
        src.write_text(pre + text)
        exe = tmp / 't'
        subprocess.run(['cc', '-std=gnu11', '-w', '-I', str(ROOT / 'docs/procedures/nat-121/host'), str(src), str(HERE / 'host/clock174.c'),
                        '-o', str(exe)], check=True)
        env = dict(os.environ)
        if swipe is not None:
            env['E1STOUCH_SWIPE'] = str(swipe)
        return subprocess.run([str(exe)], check=True, capture_output=True, text=True, timeout=60, env=env).stdout


def posts(out):
    return [tuple(int(x) for x in m.groups()) for m in re.finditer(r'post (\d+) (\d+) (\d+) (\d+) at (\d+)', out)]


class EventThreadUnchanged(unittest.TestCase):
    def test_same_frames_writes_and_posts_as_nat169(self):
        for kw in (dict(), dict(irq=1, late=1500)):
            with self.subTest(**kw):
                a, b = t169.run_case(t169.P169, **kw), run_peer(P174, **kw)
                self.assertEqual(t169.frames(a), t169.frames(b))
                self.assertEqual(t169.posts(a), t169.posts(b))
                self.assertEqual(t169.counts(a), t169.counts(b))


class Swipes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run_clock()
        cls.p = posts(cls.out)

    def test_schedule(self):
        downs = [p for p in self.p if p[0] == 1]
        self.assertEqual(len(downs), 54)                       # 215 s .. 375 s every 3 s (the 54th starts at 374 s)
        self.assertGreaterEqual(downs[0][4], 215000000)
        self.assertLess(downs[0][4], 215100001)
        gaps = {b[4] - a[4] for a, b in zip(downs, downs[1:])}
        self.assertEqual(gaps, {3000000})
        self.assertIn('e1s-swipe: done after 54 swipes', self.out)
        self.assertEqual({p[1] for p in self.p}, {9})

    def test_one_swipe_shape(self):
        first = self.p[:14]
        self.assertEqual([p[0] for p in first], [1] + [2] * 12 + [3])
        self.assertEqual([p[2] for p in first][:3], [52428, 49152, 45875])
        self.assertEqual((first[-2][2], first[-1][2]), (13107, 13107))
        self.assertEqual({p[3] for p in first}, {32768})
        self.assertEqual([b[4] - a[4] for a, b in zip(first, first[1:])], [16000] * 13)
        second = self.p[14:28]
        self.assertEqual((second[0][2], second[-1][2]), (13107, 52428))     # the next one goes back

    def test_off(self):
        out = run_clock(0)
        self.assertEqual(posts(out), [])
        self.assertIn('RESULT off', out)


def _load_swipe():
    spec = importlib.util.spec_from_file_location('nat174_swipe175', HERE / 'swipe175.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def synth(swipe_gap_ms, idle_gap_ms=105, swipes=5, real=False):
    """A kernel text with idle swaps every idle_gap_ms and, per swipe, a finger-9 DOWN/12 MOVE/UP and swaps every swipe_gap_ms for
    600 ms; swipes 3 s apart starting at 300 s."""
    lines, sid, t = [], 0, 300000000
    for k in range(swipes):
        d = t + k * 3000000
        lines.append('tl: p 1 9 52428 32768 at %d' % d)
        for i in range(12):
            lines.append('tl: p 2 9 %d 32768 at %d' % (49152 - i * 3000, d + (i + 1) * 16000))
        lines.append('tl: p 3 9 13107 32768 at %d' % (d + 13 * 16000))
        a = d + 5000
        while a < d + 600000:
            sid += 1
            lines += ['tl: s %d at %d' % (sid, a), 'tl: v %d ready %d shown %d done %d' % (sid, a + 100, a + 200, a + 5000)]
            a += swipe_gap_ms * 1000
        a = d + 1700000                                   # idle stretch, more than GUARD_US after the UP
        while a < d + 2900000:
            sid += 1
            lines.append('tl: s %d at %d' % (sid, a))
            a += idle_gap_ms * 1000
    if real:
        lines.append('tl: p 1 0 30000 30000 at %d' % (t + 1500000))
    return '\n'.join(lines) + '\n'


class Analyser(unittest.TestCase):
    def setUp(self):
        self.m = _load_swipe()

    def test_verdicts(self):
        for gap, want in ((16, 'F60'), (30, 'F30'), (50, 'F-low'), (104, 'S-same')):
            r = self.m.analyse(synth(gap))
            self.assertEqual(r['verdict'], want, (gap, r['swipe_swap_interval'], r['idle_swap_interval']))
            self.assertEqual(r['downs'], 5)
            self.assertEqual(r['finger9_samples'], 70)
        r = self.m.analyse(synth(16))
        self.assertEqual(r['swipe_swap_interval']['median'], 16.0)
        self.assertEqual(r['idle_swap_interval']['median'], 105.0)
        self.assertEqual(r['swipe_share_60hz'], 1.0)
        self.assertEqual(r['down_to_first_swap']['median'], 5.0)
        self.assertEqual(r['swipe_copy']['median'], 4.8)

    def test_none_and_real_finger(self):
        self.assertEqual(self.m.analyse('tl: s 1 at 5\ntl: s 2 at 105005\n')['verdict'], 'S-none')
        self.assertEqual(self.m.analyse('nothing here\n')['verdict'], 'S-none')
        r = self.m.analyse(synth(16, real=True))
        self.assertEqual((r['real_finger_samples'], r['verdict']), (1, 'F60'))


if __name__ == '__main__':
    unittest.main()
