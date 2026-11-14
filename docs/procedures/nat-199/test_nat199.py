#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-199 host tests.

1. The patch's own uar_hash/uar_say/uar_match/uar_scan text, compiled on the host against a synthetic loader log in NAT-116's real
   format:
   - one "reason" line and its "throw stack" line are said;
   - the same text a second time, and the function's own printed lines, are not said again;
   - a different reason is said;
   - a log without the text says nothing but the count line.
2. The patch only adds code (no line of the original removed, besides none); user_abort_trace still prints its line and then calls
   user_abort_reason_later().
3. The kernel: segments equal e21's (NAT-197), the loader-checked symbols in place, the reason-scan string present once; loader sites
   rc 0; package and session derivation.
"""
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
TOOLS = ROOT / 'artifacts/xnu-macho-tools/macho-session4/prefix/bin'
REASON = ("1970-01-01 00:05:00.-267 SpringBoard[75:762] *** Terminating app due to uncaught exception 'NSInternalInconsistencyException', "
          "reason: 'Failed to load bounding path bitmap data'\n*** First throw call stack:\n(0x1caad148c 0x1c3db9050 0x1c52bf900)\n"
          "libc++abi: terminating due to uncaught exception of type NSException\n")
OTHER = ("1970-01-01 00:05:09.-001 SpringBoard[90:800] *** Terminating app due to uncaught exception 'NSRangeException', "
         "reason: 'index 3 beyond bounds'\n*** First throw call stack:\n(0x1 0x2)\n")


def patched():
    return '\n'.join(l[1:] for l in (HERE / 'user_exception_trace.patch').read_text().splitlines() if l.startswith('+') and not l.startswith('+++'))


def func(text, name):
    m = re.search(r'^(static [^\n]*\n%s\([^)]*\)\n\{.*?^\})' % name, text, re.S | re.M)
    assert m, name
    return m.group(1)


HARNESS = r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#define __unused __attribute__((unused))
#define os_atomic_load(p, o) (*(p))
typedef void *thread_call_param_t;
char loader_log[1536 * 1024];
uint32_t loader_log_len;
@DEFINES@
static uint32_t uar_seen[UAR_SEEN];
static unsigned uar_seen_count;
@FUNCS@
static void put(const char *s) { size_t n = strlen(s); memcpy(loader_log + loader_log_len, s, n); loader_log_len += n; }
int main(int argc, char **argv) {
  FILE *f = fopen(argv[1], "rb"); static char buf[1 << 20]; size_t n = fread(buf, 1, sizeof(buf) - 1, f); buf[n] = 0; fclose(f);
  /* the input is split into scans by lines "@@SCAN"; what the scan prints is appended to the log, as the console does */
  char *p = buf;
  for (;;) {
    char *q = strstr(p, "@@SCAN\n");
    if (q) *q = 0;
    put(p);
    {
      char out[1 << 16]; FILE *o = fmemopen(out, sizeof(out), "w"); FILE *save = stdout; stdout = o;
      uar_scan(NULL, NULL);
      fflush(o); long m = ftell(o); fclose(o); stdout = save; out[m] = 0;
      fputs(out, stdout); fputs("@@END\n", stdout);
      put(out);
    }
    if (!q) break;
    p = q + 7;
  }
  return 0;
}
'''


class Harness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        t = patched()
        defs = '\n'.join(l for l in t.splitlines() if re.match(r'#define UAR_', l))
        funcs = '\n\n'.join(func(t, n) for n in ('uar_hash', 'uar_say', 'uar_match', 'uar_scan'))
        cls.dir = Path(tempfile.mkdtemp(prefix='nat199-'))
        c = cls.dir / 'h.c'
        c.write_text(HARNESS.replace('@DEFINES@', defs).replace('@FUNCS@', funcs))
        subprocess.run(['cc', '-O1', '-Wall', '-Werror', '-Wno-unused-function', '-o', str(cls.dir / 'h'), str(c)], check=True)

    def scans(self, text):
        f = self.dir / 'in.txt'
        f.write_text(text)
        out = subprocess.run([str(self.dir / 'h'), str(f)], capture_output=True, text=True, check=True).stdout
        return [s.strip('\n').splitlines() for s in out.split('@@END\n')[:-1]]

    def test_reason_and_stack_once(self):
        s = self.scans('noise\n' * 1000 + REASON + 'more\n@@SCAN\n' + REASON + '@@SCAN\n' + OTHER)
        self.assertEqual(len(s), 3)
        first = s[0]
        self.assertTrue(first[0].startswith("userabort: reason: Terminating app due to uncaught exception 'NSInternalInconsistencyException'"),
                        first)
        self.assertEqual(first[1], 'userabort: throw stack: (0x1caad148c 0x1c3db9050 0x1c52bf900)')
        self.assertRegex(first[2], r'^userabort: reason scan: 1 line\(s\) in \d+ bytes of the loader log, 1 distinct said$')
        # the same text again and scan 1's own lines: nothing new
        self.assertEqual(len(s[1]), 1)
        self.assertRegex(s[1][0], r'reason scan: 3 line\(s\) .* 1 distinct said$')
        # a different reason is said
        self.assertIn("NSRangeException", s[2][0])
        self.assertEqual(s[2][1], 'userabort: throw stack: (0x1 0x2)')
        self.assertRegex(s[2][-1], r'2 distinct said$')

    def test_nothing(self):
        s = self.scans('nothing here\n' * 10)
        self.assertEqual(len(s[0]), 1)
        self.assertRegex(s[0][0], r'^userabort: reason scan: 0 line\(s\) in 130 bytes of the loader log, 0 distinct said$')

    def test_unprintable_and_bounds(self):
        s = self.scans('x' * 50 + 'Terminating app due to uncaught exception \x01\x02' + 'y' * 2000)
        self.assertEqual(len(s[0][0]), len('userabort: reason: ') + 600)
        self.assertIn('exception ..', s[0][0])


class Patch(unittest.TestCase):
    def test_only_adds(self):
        lines = (HERE / 'user_exception_trace.patch').read_text().splitlines()
        self.assertFalse([l for l in lines if l.startswith('-') and not l.startswith('---')])
        t = patched()
        self.assertIn('user_abort_reason_later();', t)
        self.assertNotRegex(t, r'\bcopyout\b|\bmsr\b|ml_io_map|\bloader_log\[[^]]*\]\s*=[^=]')   # the log is only read

    def test_no_write_to_log(self):
        body = func(patched(), 'uar_scan') + func(patched(), 'uar_say')
        self.assertNotRegex(body, r'loader_log\[[^\]]*\]\s*=(?!=)')
        self.assertNotIn('loader_log_len =', body)


class Kernel(unittest.TestCase):
    def test_layout(self):
        a = next((ROOT / 'artifacts/nat-197/kernel-001').glob('link*/kernel/kernel.unstripped'))
        b = next((ROOT / 'artifacts/nat-199/kernel-001').glob('link*/kernel/kernel.unstripped'))
        seg = lambda k: [l for l in subprocess.run([str(TOOLS / 'aarch64-apple-darwin-size'), '-m', str(k)], capture_output=True, text=True,
                                                   check=True).stdout.splitlines() if l.startswith('Segment')]
        self.assertEqual(seg(a), seg(b))
        nm = lambda k: dict(reversed(l.split(' ', 2)[::2]) for l in subprocess.run([str(TOOLS / 'aarch64-apple-darwin-nm'), str(k)],
                                                                                    capture_output=True, text=True, check=True).stdout.splitlines() if l.count(' ') >= 2)
        na, nb = nm(a), nm(b)
        for s in ('_LowResetVectorBase', '_reset_vector', '_start_cpu', '_psci_smp_early_marks', '_loader_log', '_loader_log_len',
                  '_loader_stub_slot', '_common_start'):
            if s in na:
                self.assertEqual(na[s], nb[s], s)
        r = json.loads((ROOT / 'artifacts/nat-199/kernel-001/rebuild.json').read_text())
        self.assertEqual(r['undefined_symbols'], 0)
        self.assertEqual(r['expect_strings']['userabort: reason scan: %u line(s) in %u bytes of the loader log, %u distinct said'], 1)
        b = json.loads((ROOT / 'artifacts/nat-199/build-001/build.json').read_text())
        self.assertEqual(b['nat152_changes']['loader_sites_check'], dict(rc=0, verdict='ok', bad=0))

    def test_session(self):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'derive200.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((ROOT / 'artifacts/nat-199/package-001/package.json').read_text())['images']['loader-diag-xnu-e2r-md1']
        s = (HERE / 'session_nat200.py').read_text()
        self.assertIn(p['recovery_sha256'], s)
        self.assertIn(p['payload_sha256'], s)
        img = ROOT / 'artifacts/nat-199/package-001/loader-diag-xnu-e2r-md1/recovery.img'
        self.assertEqual(hashlib.sha256(img.read_bytes()).hexdigest(), p['recovery_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
