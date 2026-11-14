#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-201 host tests.

1. trap202.py on synthetic kernel text whose `usertrap:` lines are formatted with the printf formats taken from the compiled source
   (artifacts/nat-199/src/user_exception_trace.c), so a format change breaks the test, not the analysis on the phone's text:
   verdicts T-none / T-other / T-media, the register text and frames attach to their trap, sites group across respawns.
2. The patch is NAT-199's plus one line (the tunable's default 0 -> 1); the command line is e2r's with only the tag changed and
   without "systrace" (that boot-arg also turns on the system-call and exec traces).
3. The kernel: against NAT-199's no-storage kernel only the UUID, the build-path strings (nat-199 -> nat-201, same length) and one
   byte (0 -> 1, the default) differ; every symbol and segment in place; both trace formats present once; loader sites rc 0.
4. Package hashes and the counted session derivation.
"""
import hashlib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import trap202  # noqa: E402

SRC = ROOT / 'artifacts/nat-199/src/user_exception_trace.c'
TOOLS = ROOT / 'artifacts/xnu-macho-tools/macho-session4/prefix/bin'


def c_formats():
    t = SRC.read_text()
    lits = re.findall(r'printf\("((?:[^"\\]|\\.)*)"', t)
    return [m.encode().decode('unicode_escape') for m in lits if m.startswith('usertrap:')]


def cfmt(fmt, *args):
    py = re.sub(r'%ll[xu]|%[xu]', lambda m: '%x' if 'x' in m.group(0) else '%d', fmt).replace('%d', '%d')
    return py % args


class Formats(unittest.TestCase):
    def test_source_formats(self):
        f = c_formats()
        self.assertEqual(len(f), 3, f)
        self.assertTrue(f[0].startswith('usertrap: %s[%d] exception %d code 0x%llx 0x%llx: pc 0x%llx lr 0x%llx sp 0x%llx, shared cache slide 0x%x'))
        self.assertTrue(f[1].startswith('usertrap:   x%u -> "%s"'), f[1])
        self.assertTrue(f[2].startswith('usertrap:   called from 0x%llx'))


def trap(name, pid, exc, c0, pc, lr, sp, slide, t):
    f = c_formats()[0].rstrip('\n')
    return '[%11.6f]: ' % t + cfmt(f, name, pid, exc, c0, 0x10, pc, lr, sp, slide)


def text_line(reg, s, t):
    return '[%11.6f]: ' % t + 'usertrap:   x%d -> "%s"' % (reg, s)


def frame(a, t):
    return '[%11.6f]: ' % t + cfmt(c_formats()[2].rstrip('\n'), a)


class Analyse(unittest.TestCase):
    def test_none(self):
        self.assertEqual(trap202.analyse('[   1.000000]: nothing\n')['verdict'], 'T-none')

    def test_other(self):
        # a frame line whose trap line was lost (the ring's start) belongs to nothing
        r = trap202.analyse('\n'.join([frame(0x1a0009999, 9.0), text_line(0, 'lost', 9.0),
                                       trap('backboardd', 40, 6, 1, 0x1a0001234, 0x1a0005678, 0x16f000000, 0x24090000, 10.0)]))
        self.assertEqual(r['other_first'][0]['frames'], [])
        self.assertEqual(r['verdict'], 'T-other')
        self.assertEqual(r['traps_by_process'], {'backboardd': 1})

    def test_media(self):
        slide = 0x24090000
        lines = []
        for i, pid in enumerate((31, 52, 77)):
            lines += [trap('mediaserverd', pid, 1, 1, 0x1c0001000 + slide, 0x1c0002000 + slide, 0x16f000000, slide, 20.0 + 5 * i),
                      text_line(8, 'AudioSession', 20.0 + 5 * i), frame(0x1c0003000 + slide, 20.0 + 5 * i), frame(0x100004abc, 20.0 + 5 * i)]
        lines.insert(4, trap('SpringBoard', 13, 6, 1, 0x1c9000000 + slide, 0x1c9000010 + slide, 0x16f100000, slide, 22.0))
        r = trap202.analyse('\n'.join(lines))
        self.assertEqual(r['verdict'], 'T-media')
        self.assertEqual(r['mediaserverd_traps'], 3)
        self.assertEqual(r['mediaserverd_sites'], [dict(exception='EXC_BAD_ACCESS', code0='0x1', pc_unslid='0x1c0001000', lr_unslid='0x1c0002000', count=3)])
        m = r['first_mediaserverd'][0]
        self.assertEqual(m['texts'], {'x8': 'AudioSession'})
        self.assertEqual(m['frames'], ['0x%x' % (0x1c0003000 + slide), '0x100004abc'])
        self.assertEqual(r['other_first'][0]['frames'], [], 'the SpringBoard trap does not take mediaserverd frames')
        self.assertEqual(r['first_mediaserverd'][1]['frames'][0], '0x%x' % (0x1c0003000 + slide), 'frames after SpringBoard go to pid 52')


class Image(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = json.loads((ROOT / 'artifacts/nat-201/build-001/build.json').read_text())
        cls.a = json.loads((ROOT / 'artifacts/nat-199/build-001/build.json').read_text())

    def test_cmdline(self):
        new = self.b['payload_fixes']['loader-diag-xnu-e2s-md1']['cmdline']
        old = self.a['payload_fixes']['loader-diag-xnu-e2r-md1']['cmdline']
        self.assertEqual(new, old.replace('nat_attempt=NAT199-e2r', 'nat_attempt=NAT201-e2s'))
        self.assertNotIn('systrace', new, 'the boot-arg would also turn on the system-call and exec traces')
        self.assertLess(len(new.encode()), 256)

    def test_patch(self):
        a = (ROOT / 'docs/procedures/nat-199/user_exception_trace.patch').read_text().splitlines()
        b = (HERE / 'user_exception_trace.patch').read_text().splitlines()
        self.assertTrue(all(l in b for l in a))
        changed = [l for l in b if l not in a and l[:1] in '+-']
        self.assertEqual(len(changed), 2)
        self.assertEqual(changed[0], '-static TUNABLE(uint32_t, user_exception_trace_enabled, "systrace", 0);')
        self.assertTrue(changed[1].startswith('+static TUNABLE(uint32_t, user_exception_trace_enabled, "systrace", 1);'))
        src = (ROOT / 'artifacts/nat-201/src/user_exception_trace.c').read_text()
        self.assertEqual(src.replace('"systrace", 1);\t/* NAT-201: on without the boot-arg, so failed system calls stay unlogged */', '"systrace", 0);'),
                         SRC.read_text())

    def test_kernel(self):
        ns_a = (ROOT / 'artifacts/nat-199/kernel-001/kernel.no-storage').read_bytes()
        ns_b = (ROOT / 'artifacts/nat-201/kernel-001/kernel.no-storage').read_bytes()
        self.assertEqual(hashlib.sha256(ns_b).hexdigest(), self.b['nat201_changes']['kernel'])
        self.assertEqual(len(ns_a), len(ns_b))
        d = [i for i in range(len(ns_a)) if ns_a[i] != ns_b[i]]
        uuid = [i for i in d if 0x11d0 <= i < 0x11e0]
        path = [i for i in d if ns_b[i - 12:i + 12].find(b'nat-201/') >= 0]
        rest = [i for i in d if i not in uuid and i not in path]
        self.assertEqual(len(uuid), 16)
        self.assertTrue(all(ns_a[i:i + 1] == b'9' or ns_a[i] in b'0189' for i in path))
        self.assertEqual(len(rest), 1, [hex(i) for i in rest])
        self.assertEqual((ns_a[rest[0]], ns_b[rest[0]]), (0, 1), 'the one changed value is the tunable default')
        kb = next((ROOT / 'artifacts/nat-201/kernel-001').glob('link*/kernel/kernel.unstripped'))
        ka = next((ROOT / 'artifacts/nat-199/kernel-001').glob('link*/kernel/kernel.unstripped'))
        nm = lambda k: {l.split()[2]: int(l.split()[0], 16) for l in subprocess.run([str(TOOLS / 'aarch64-apple-darwin-nm'), str(k)], capture_output=True,
                                                                                    text=True, check=True).stdout.splitlines() if len(l.split()) == 3}
        sa, sb = nm(ka), nm(kb)
        self.assertEqual(sa, sb, 'every symbol at the same address')
        seg = lambda k: [l for l in subprocess.run([str(TOOLS / 'aarch64-apple-darwin-size'), '-m', str(k)], capture_output=True, text=True,
                                                   check=True).stdout.splitlines() if l.startswith('Segment')]
        self.assertEqual(seg(ka), seg(kb))
        f = c_formats()
        k = kb.read_bytes()
        self.assertEqual(k.count(f[0].encode()), 1)
        self.assertEqual(k.count(f[2].encode()), 1)
        self.assertEqual(self.b['nat152_changes']['loader_sites_check'], dict(rc=0, verdict='ok', bad=0))


class Session(unittest.TestCase):
    def test_session(self):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'derive202.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((ROOT / 'artifacts/nat-201/package-001/package.json').read_text())['images']['loader-diag-xnu-e2s-md1']
        s = (HERE / 'session_nat202.py').read_text()
        self.assertIn(p['recovery_sha256'], s)
        self.assertIn(p['payload_sha256'], s)
        img = ROOT / 'artifacts/nat-201/package-001/loader-diag-xnu-e2s-md1/recovery.img'
        self.assertEqual(hashlib.sha256(img.read_bytes()).hexdigest(), p['recovery_sha256'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
