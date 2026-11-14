#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-180 host tests: copyColumnRuns() (cut from the patched MiniIOMobileFramebuffer.cpp) writes exactly what the per-pixel loop it
replaces wrote, for the driver's real column maps and for random ones; the patch changes nothing else."""
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ORIG = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/iokit/Kernel/MiniIOMobileFramebuffer.cpp'
PATCH = HERE / 'MiniIOMobileFramebuffer.patch'

HARNESS = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned calls;
#define memcpy(d, s, n) (calls++, memcpy((d), (s), (n)))
%s
#undef memcpy
static uint32_t lcg = 12345;
static uint32_t rnd(void) { lcg = lcg * 1103515245u + 12345u; return lcg >> 8; }
/* the driver's nearest map (MiniIOMobileFramebuffer.cpp:786) */
static void nearest(uint32_t *col, int32_t n, int32_t sx, int32_t sw, int32_t px0, int32_t px1)
{ for (int32_t x = 0; x < n; x++) col[x] = (uint32_t)(sx + (int64_t)(x - px0) * sw / (px1 - px0)); }
static int check(const char *name, const uint32_t *col, int32_t x0, int32_t x1, int32_t srcw, int print)
{
	uint32_t *from = malloc(sizeof(uint32_t) * (size_t)srcw), *a = malloc(4 * 4096), *b = malloc(4 * 4096);
	for (int32_t i = 0; i < srcw; i++) from[i] = rnd() | 1u;
	for (int i = 0; i < 4096; i++) a[i] = b[i] = 0xdeadbeef;
	for (int32_t x = x0; x < x1; x++) a[x] = from[col[x]];              /* the loop NAT-180 replaces */
	calls = 0;
	copyColumnRuns(b, from, col, x0, x1);
	int bad = memcmp(a, b, 4 * 4096) != 0;
	if (print) printf("%%s calls %%u bad %%d\n", name, calls, bad);
	free(from); free(a); free(b);
	return bad;
}
int main(void)
{
	static uint32_t col[4096];
	int bad = 0;
	nearest(col, 1080, 0, 1125, 0, 1080); bad |= check("iphone", col, 0, 1080, 1125, 1);
	bad |= check("crop", col, 37, 901, 1125, 1);
	bad |= check("empty", col, 500, 500, 1125, 1);
	nearest(col, 1080, 0, 750, 0, 1080); bad |= check("fbscale2", col, 0, 1080, 750, 1);
	nearest(col, 1080, 20, 300, 100, 700); bad |= check("layer", col, 100, 700, 400, 1);
	for (int t = 0; t < 2000; t++) {
		int32_t n = 1 + (int32_t)(rnd() %% 1500), c = (int32_t)(rnd() %% 8), w = 0;
		for (int32_t x = 0; x < n; x++) { uint32_t r = rnd() %% 10; c += r < 6 ? 1 : (r < 8 ? 0 : (int32_t)(rnd() %% 5)); col[x] = (uint32_t)c; }
		w = c + 1;
		int32_t x0 = (int32_t)(rnd() %% (uint32_t)n), x1 = x0 + (int32_t)(rnd() %% (uint32_t)(n - x0 + 1));
		bad |= check("random", col, x0, x1, w, 0);
	}
	printf("RESULT %%s\n", bad ? "bad" : "ok");
	return bad;
}
'''


def patched():
    with tempfile.TemporaryDirectory(dir=os.environ.get('TMPDIR')) as tmp:
        t = Path(tmp) / 'f.cpp'
        t.write_text(ORIG.read_text())
        subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(t), str(PATCH)], check=True)
        return t.read_text()


def helper(text):
    m = re.search(r'static inline void\ncopyColumnRuns\(.*?\n}\n', text, re.S)
    assert m, 'copyColumnRuns not found'
    return m.group(0)


def run(helper_text):
    with tempfile.TemporaryDirectory(prefix='nat180-', dir=os.environ.get('TMPDIR')) as tmp:
        src = Path(tmp) / 'h.c'
        src.write_text(HARNESS % helper_text)
        exe = Path(tmp) / 'h'
        subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Werror', str(src), '-o', str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout


class Equivalence(unittest.TestCase):
    def test_same_pixels(self):
        rc, out = run(helper(patched()))
        self.assertEqual(rc, 0, out)
        self.assertIn('RESULT ok', out)
        calls = dict(re.findall(r'^(\w+) calls (\d+) bad 0$', out, re.M))
        self.assertEqual(int(calls['iphone']), 45)            # 1080 panel columns as 45 runs (one skip per 24) of consecutive picture columns
        self.assertEqual(int(calls['empty']), 0)

    def test_mutants_caught(self):
        h = helper(patched())
        for o, n in (('column[x + 1] == column[x] + 1', 'column[x + 1] >= column[x]'),
                     ('(size_t) (x - start)', '(size_t) (x - start + 1)'),
                     ('uint32_t first = column[x];', 'uint32_t first = column[x] + 1;')):
            self.assertEqual(h.count(o), 1, o)
            rc, out = run(h.replace(o, n))
            self.assertNotIn('RESULT ok', out, n)


class PatchScope(unittest.TestCase):
    def test_only_the_loop(self):
        lines = PATCH.read_text().splitlines()
        removed = [l[1:].strip() for l in lines if l.startswith('-') and not l.startswith('---')]
        self.assertEqual(removed, ['for (int32_t x = cx0; x < cx1; x++) {', 'to[x] = from[fColumn[x]];', '}'])
        added = [l[1:].strip() for l in lines if l.startswith('+') and not l.startswith('+++')]
        code = [l for l in added if l and not l.startswith(('/*', '*'))]
        self.assertIn('copyColumnRuns(to, from, fColumn, cx0, cx1);', code)
        self.assertEqual(sum(1 for l in code if 'copyColumnRuns(' in l), 2)   # the definition and the one call


def _fbcopy():
    import importlib.util
    spec = importlib.util.spec_from_file_location('t180_fbcopy181', HERE / 'fbcopy181.py')
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _stats(t, us):
    return ('[%7.3f]: MiniIOMobileFramebuffer: 50 frames in 5000 ms (10 a second), %d us each in the driver, after 0 us waiting for '
            'the GPU and, 0 of them, 0 us for the next refresh; 0 swaps waited for the frame before, 0 gave up; 0 swaps came a refresh '
            'late themselves\n' % (t, us))


class Analyser(unittest.TestCase):
    def test_verdicts(self):
        a = _fbcopy()
        self.assertEqual(a.analyse('')['verdict'], 'K-none')
        for us, v in ((4100, 'K2'), (5000, 'K2'), (5001, 'K1'), (7999, 'K1'), (8000, 'K0'), (8900, 'K0')):
            r = a.analyse(''.join(_stats(200.0 + 5 * i, us) for i in range(5)))
            self.assertEqual((r['verdict'], r['driver_ms_median']), (v, us / 1000.0), us)
        self.assertEqual(a.analyse(''.join(_stats(200.0 + 5 * i, u) for i, u in enumerate((3000, 3000, 9000))))['verdict'], 'K2')

    def test_baseline_is_k0(self):
        k = ROOT / 'artifacts/nat-177/analysis/kernel-text.txt'
        if not k.exists():
            self.skipTest('no NAT-177 kernel text')
        r = _fbcopy().analyse(k.read_text(errors='replace'))
        self.assertEqual((r['verdict'], r['driver_ms_median'], r['swipe_copy_ms_median'], r['swipe_verdict']), ('K0', 8.914, 8.77, 'F30'))


if __name__ == '__main__':
    unittest.main()
