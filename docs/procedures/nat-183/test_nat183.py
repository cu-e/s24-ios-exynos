#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-183 host tests: the run table built in drawLayer() and the per-row copies in drawRows() (both cut verbatim from the patched
MiniIOMobileFramebuffer.cpp) write exactly what the per-pixel loop writes, for the driver's real maps and random ones; the patch only
adds (the per-pixel loop stays as the fallback when the table could not be allocated)."""
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
#include <stdbool.h>
static unsigned calls;
#define memcpy(d, s, n) (calls++, memcpy((d), (s), (n)))
struct ColumnRun { uint32_t to, from, count; };
struct Job { const struct ColumnRun * runs; uint32_t runCount; };
static uint32_t fColumn[4096];
static struct ColumnRun fRunStore[4096], * fColumnRun = fRunStore;
static uint32_t lcg = 12345;
static uint32_t rnd(void) { lcg = lcg * 1103515245u + 12345u; return lcg >> 8; }

static void build(struct Job * jobp, int32_t cx0, int32_t cx1, bool filter)
{
	struct Job job;
%(build)s
	*jobp = job;
}

static void row(const struct Job * job, uint32_t * to, const uint32_t * from, int32_t cx0, int32_t cx1)
{
	if (0) {
	} else if (job->runs != NULL) {
%(copy)s
	} else {
		for (int32_t x = cx0; x < cx1; x++) {
			to[x] = from[fColumn[x]];
		}
	}
}

static int check(const char *name, int32_t x0, int32_t x1, int32_t srcw, int print)
{
	uint32_t *from = malloc(4 * (size_t)srcw + 4), *a = malloc(4 * 4096), *b = malloc(4 * 4096);
	struct Job job;
	for (int32_t i = 0; i < srcw; i++) from[i] = rnd() | 1u;
	for (int i = 0; i < 4096; i++) a[i] = b[i] = 0xdeadbeef;
	for (int32_t x = x0; x < x1; x++) a[x] = from[fColumn[x]];
	build(&job, x0, x1, false);
	if (job.runs == NULL) return 1;
	calls = 0;
	row(&job, b, from, x0, x1);
	int bad = memcmp(a, b, 4 * 4096) != 0 || calls != job.runCount;
	if (print) printf("%%s runs %%u calls %%u bad %%d\n", name, job.runCount, calls, bad);
	free(from); free(a); free(b);
	return bad;
}

static void nearest(int32_t n, int32_t sx, int32_t sw, int32_t px0, int32_t px1)
{ for (int32_t x = 0; x < n; x++) fColumn[x] = (uint32_t)(sx + (int64_t)(x - px0) * sw / (px1 - px0)); }

int main(void)
{
	int bad = 0;
	struct Job j;
	build(&j, 0, 10, true);
	printf("filter runs %%s\n", j.runs == NULL && j.runCount == 0 ? "none" : "SET");
	bad |= j.runs != NULL || j.runCount != 0;
	fColumnRun = NULL;
	build(&j, 0, 10, false);
	printf("no table runs %%s\n", j.runs == NULL ? "none" : "SET");
	bad |= j.runs != NULL;
	fColumnRun = fRunStore;
	nearest(1080, 0, 1125, 0, 1080); bad |= check("iphone", 0, 1080, 1125, 1);
	bad |= check("crop", 37, 901, 1125, 1);
	bad |= check("empty", 500, 500, 1125, 1);
	nearest(1080, 0, 750, 0, 1080); bad |= check("fbscale2", 0, 1080, 750, 1);
	nearest(1080, 20, 300, 100, 700); bad |= check("layer", 100, 700, 400, 1);
	for (int t = 0; t < 2000; t++) {
		int32_t n = 1 + (int32_t)(rnd() %% 1500), c = (int32_t)(rnd() %% 8);
		for (int32_t x = 0; x < n; x++) { uint32_t r = rnd() %% 10; c += r < 6 ? 1 : (r < 8 ? 0 : (int32_t)(rnd() %% 5)); fColumn[x] = (uint32_t)c; }
		int32_t x0 = (int32_t)(rnd() %% (uint32_t)n), x1 = x0 + (int32_t)(rnd() %% (uint32_t)(n - x0 + 1));
		bad |= check("random", x0, x1, c + 1, 0);
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


def pieces(text):
    b = re.search(r'\n(\tjob\.runs = NULL;\n.*?\t\tjob\.runCount = n;\n\t}\n)', text, re.S)
    c = re.search(r'\t\t} else if \(job->runs != NULL\) {\n(.*?)\t\t} else {\n', text, re.S)
    assert b and c, 'pieces not found'
    return b.group(1), c.group(1)


def run(build, copy):
    with tempfile.TemporaryDirectory(prefix='nat183-', dir=os.environ.get('TMPDIR')) as tmp:
        src = Path(tmp) / 'h.c'
        src.write_text(HARNESS % dict(build=build, copy=copy))
        exe = Path(tmp) / 'h'
        subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Werror', '-Wno-unused-variable', str(src), '-o', str(exe)], check=True)
        r = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout


class Equivalence(unittest.TestCase):
    def test_same_pixels(self):
        rc, out = run(*pieces(patched()))
        self.assertEqual(rc, 0, out)
        self.assertIn('RESULT ok', out)
        self.assertIn('filter runs none', out)
        self.assertIn('no table runs none', out)
        runs = dict(re.findall(r'^(\w+) runs (\d+) calls \d+ bad 0$', out, re.M))
        self.assertEqual(int(runs['iphone']), 45)
        self.assertEqual(int(runs['empty']), 0)

    def test_mutants_caught(self):
        b, c = pieces(patched())
        for o, n, where in (('fColumn[x] == fColumn[x - 1] + 1', 'fColumn[x] >= fColumn[x - 1]', 'b'),
                            ('fColumnRun[n - 1].count++;', 'fColumnRun[n - 1].count += 2;', 'b'),
                            ('fColumnRun[n].from = fColumn[x];', 'fColumnRun[n].from = fColumn[x] + 1;', 'b'),
                            ('(size_t) job->runs[r].count * sizeof(uint32_t)', '(size_t) job->runs[r].count', 'c'),
                            ('if (!filter && fColumnRun != NULL)', 'if (fColumnRun != NULL)', 'b')):
            src = b if where == 'b' else c
            self.assertEqual(src.count(o), 1, o)
            rc, out = run(src.replace(o, n), c) if where == 'b' else run(b, src.replace(o, n))
            self.assertNotIn('RESULT ok', out, n)


class PatchScope(unittest.TestCase):
    def test_only_additions(self):
        lines = PATCH.read_text().splitlines()
        removed = [l for l in lines if l.startswith('-') and not l.startswith('---')]
        self.assertEqual(removed, [])
        text = patched()
        self.assertEqual(text.count('to[x] = from[fColumn[x]];'), 1)          # the per-pixel loop stays, as the fallback
        self.assertEqual(text.count('fColumnRun = IONewZero(struct ColumnRun, fPanelWidth);'), 1)


if __name__ == '__main__':
    unittest.main()
