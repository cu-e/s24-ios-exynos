#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-203 host tests.

1. The md0 root: against NAT-110's tree exactly one file added (lib/libhakios.media.dylib, the pinned donor blob, mode 0755) and
   one changed (etc/inject.conf gains one line, the two old lines unchanged); the APFS image holds both as written (apfs-tool).
2. The donor library: its name check (only "mediaserverd"), the prewarm method replaced only at its 20F66 address 0x1a2115c0c, which
   is a function start in the donor cache whose tail call reaches the function NAT-202's fault frame is in (+0x4e4 of 0x1a2115cc4).
3. The image: kernel = NAT-201's, command line = e2s's with the tag changed, and the payload holds the new md0 and not the old one.
4. media204.py: NAT-202's own kernel text gives M-same (46 at the site); synthetic M-fixed, M-other (signal exit, other site), M-none.
5. Package hashes and the counted session derivation.
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
import media204  # noqa: E402
import build_hbm_root as hbm  # noqa: E402

MD0 = ROOT / 'artifacts/nat-203/pid1-sc2-hbm'
BASE = ROOT / 'artifacts/nat-110/pid1-sc2-hb'


class Root(unittest.TestCase):
    def test_tree(self):
        a, b = hbm.tree(BASE / 'root'), hbm.tree(MD0 / 'root')
        added, removed, changed = hbm.tree_diff(a, b)
        self.assertEqual((added, removed, changed), (['lib/libhakios.media.dylib'], [], ['etc/inject.conf']))
        lib = MD0 / 'root/lib/libhakios.media.dylib'
        self.assertEqual(hashlib.sha256(lib.read_bytes()).hexdigest(), hbm.MEDIA_SHA256)
        self.assertEqual(lib.stat().st_mode & 0o777, 0o755)
        old = (BASE / 'root/etc/inject.conf').read_bytes().splitlines()
        new = (MD0 / 'root/etc/inject.conf').read_bytes().splitlines()
        self.assertEqual(new[:-1], old)
        self.assertEqual(new[-1], b'/redwood/lib/libhakios.media.dylib mediaserverd')
        self.assertLess(len(b'\n'.join(new)), 512, "the kernel's exec_inject_conf[512]")

    def test_image(self):
        rec = json.loads((MD0 / 'build.json').read_text())
        img = (MD0 / 'root.apfs').read_bytes()
        self.assertEqual(hashlib.sha256(img).hexdigest(), rec['root_apfs']['sha256'])
        self.assertTrue(all(rec['apfs_tool_readback'].values()))
        self.assertEqual(rec['verify_content']['exit'], 0)

    def test_donor_blob(self):
        self.assertEqual(hashlib.sha256(hbm.donor_blob()).hexdigest(), hbm.MEDIA_SHA256)


class Donor(unittest.TestCase):
    def test_source(self):
        src = subprocess.run(['git', '-C', str(hbm.DONOR), 'show', hbm.DONOR_SHA + ':userland/src/inject_media.c'], capture_output=True, text=True,
                             check=True).stdout
        self.assertIn('strcmp(name, "mediaserverd") != 0', src)
        self.assertRegex(src, r'"BWCoreImageFilterRenderer", "prewarmPortraitFilterVersion:semanticStyleFilters:", 0x1a2115c0cUL')
        self.assertIn('(uintptr_t)original != r->expected + slide', src, 'a method not at its address is left alone')
        self.assertIn('open("/dev/hakios-torch", O_WRONLY)', src)
        self.assertNotIn('hakios-torch', (ROOT / 'artifacts/nat-203/build-001/build.json').read_text())

    def test_cache_function(self):
        sys.path.insert(0, str(ROOT / 'docs/procedures/nat-189'))
        import dscsym
        c = dscsym.Cache(str(ROOT / 'artifacts/apple-inputs/work/cryptex-os/System/Library/Caches/com.apple.dyld'), str(ROOT / 'artifacts/nat-189/dsc-symbols'))
        w = lambda a: int.from_bytes(c.read(a, 4), 'little')
        self.assertEqual(w(0x1a2115c0c), 0xa9be4ff4, 'stp x20, x19, [sp, #-0x20]!')
        self.assertEqual(w(0x1a2115c08) >> 26, 0b000101, 'the word before is a b (the previous function ends)')
        b = w(0x1a2115c68)
        self.assertEqual(b >> 26, 0b000101)
        off = (b & 0x3ffffff) << 2
        self.assertEqual(0x1a2115c68 + off, 0x1a2115cc4, 'the prewarm tail-calls the function of the NAT-202 frame')
        t = json.loads((ROOT / 'artifacts/nat-202/analysis/trap202.json').read_text())
        frames = [int(a, 16) - int(t['first_mediaserverd'][0]['slide'], 16) for a in t['first_mediaserverd'][0]['frames']]
        self.assertIn(0x1a2115cc4 + 0x4e4, frames)


class Image(unittest.TestCase):
    def test_build(self):
        b = json.loads((ROOT / 'artifacts/nat-203/build-001/build.json').read_text())
        a = json.loads((ROOT / 'artifacts/nat-201/build-001/build.json').read_text())
        self.assertEqual(b['nat203_changes']['kernel'], a['nat201_changes']['kernel'])
        self.assertEqual(b['payload_fixes']['loader-diag-xnu-e2m-md1']['cmdline'],
                         a['payload_fixes']['loader-diag-xnu-e2s-md1']['cmdline'].replace('NAT201-e2s', 'NAT203-e2m'))
        self.assertEqual(b['nat152_changes']['loader_sites_check'], dict(rc=0, verdict='ok', bad=0))
        img = (ROOT / 'artifacts/nat-203/package-001/loader-diag-xnu-e2m-md1/recovery.img').read_bytes()
        self.assertGreater(img.find((MD0 / 'root.apfs').read_bytes()), 0)
        self.assertEqual(img.find((BASE / 'root.apfs').read_bytes()), -1)

    def test_session(self):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'derive204.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((ROOT / 'artifacts/nat-203/package-001/package.json').read_text())['images']['loader-diag-xnu-e2m-md1']
        s = (HERE / 'session_nat204.py').read_text()
        self.assertIn(p['recovery_sha256'], s)
        self.assertIn(p['payload_sha256'], s)
        self.assertNotIn('e2r with boot-arg systrace=1', s)
        self.assertIn('user_exception_trace_enabled 1, no boot-arg', s)


LJ = 'com.apple.xpc.launchd|1970-01-01 00:05:%02d.000000 (user/501/com.apple.mediaserverd%s) <Notice>: %s'


class Verdicts(unittest.TestCase):
    def test_nat202_is_same(self):
        r = media204.analyse((ROOT / 'artifacts/nat-202/analysis/kernel-text.txt').read_text(errors='replace'))
        self.assertEqual(r['verdict'], 'M-same')
        self.assertEqual(r['traps_at_nat202_site'], 46)
        self.assertEqual(len(r['exits_by_signal']), 10)

    def test_fixed(self):
        t = '\n'.join([LJ % (1, '', 'internal event: WILL_SPAWN, code = 0'), LJ % (1, ' [50]', 'service state: running'),
                       '[ 120.000000]: hakios: mediaserverd: +[BWCoreImageFilterRenderer prewarmPortraitFilterVersion:semanticStyleFilters:] replaced'])
        r = media204.analyse(t)
        self.assertEqual(r['verdict'], 'M-fixed')
        self.assertEqual((r['spawns'], r['pids']), (1, [50]))
        self.assertTrue(r['library_lines'][0].startswith('+[BWCoreImageFilterRenderer'))

    def test_other(self):
        r = media204.analyse(LJ % (2, ' [51]', 'exited due to SIGABRT | sent by abort'))
        self.assertEqual(r['verdict'], 'M-other')
        trap = ('[ 130.000000]: usertrap: mediaserverd[52] exception 1 code 0x1 0x0: pc 0x1a0001000 lr 0x195b5458c sp 0x16f000000, '
                'shared cache slide 0x1040000')
        self.assertEqual(media204.analyse(trap)['verdict'], 'M-other', 'pc not 0: another site')
        same = trap.replace('pc 0x1a0001000', 'pc 0x0')
        self.assertEqual(media204.analyse(same)['verdict'], 'M-same')
        self.assertEqual(media204.analyse(same.replace('slide 0x1040000', 'slide 0x2000000'))['verdict'], 'M-other', 'lr less the slide')

    def test_none(self):
        self.assertEqual(media204.analyse('[ 1.0]: nothing\n')['verdict'], 'M-none')


if __name__ == '__main__':
    unittest.main(verbosity=2)
