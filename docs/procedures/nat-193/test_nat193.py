#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-193 host tests: scZ's command line is scV's with fbscale=2 in place of touch_lat=1 (and the tag); the payload differs from scV's
only in the command line and the tag-derived loader constants; same kernel and md0 root; the driver source turns fbscale=2 into a
750x1624 display; bbd188 (NAT-194's verdict) gives the same answer on NAT-186's log with every touch_lat line removed; the session
derivation is current."""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCV = ROOT / 'artifacts/nat-185/build-001'
SCZ = ROOT / 'artifacts/nat-193/build-001'
V, Z = 'loader-diag-xnu-scV-md1', 'loader-diag-xnu-scZ-md1'
DRIVER = ROOT / 'artifacts/nat-185/kernel-001/src/iokit_MiniIOMobileFramebuffer.cpo/MiniIOMobileFramebuffer.cpp'
LOG186 = ROOT / 'artifacts/nat-186/analysis/kernel-text.txt'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def rec(build, name):
    return json.loads((build / 'build.json').read_text())['payload_fixes'][name]


class Image(unittest.TestCase):
    def test_cmdline(self):
        v, z = rec(SCV, V)['cmdline'], rec(SCZ, Z)['cmdline']
        tv, tz = v.split(), z.split()
        self.assertEqual(len(tv), len(tz))
        diff = [(a, b) for a, b in zip(tv, tz) if a != b]
        self.assertEqual(diff, [('nat_attempt=NAT185-scV', 'nat_attempt=NAT193-scZ'), ('touch_lat=1', 'fbscale=2')])
        self.assertEqual(len(z.encode()), 252)
        for keep in ('e1sufs=0', 'fb_filter=0', 'e1skeys=0', 'e1spmic=2', 'small_cores=0', 'e1s_wdt_pet=1', 'loader_return_after=270'):
            self.assertIn(keep, tz)

    def test_same_kernel_and_root(self):
        v, z = (json.loads((b / 'build.json').read_text()) for b in (SCV, SCZ))
        self.assertEqual(v['nat185_changes']['kernel'], z['nat185_changes']['kernel'])
        self.assertEqual(rec(SCV, V)['ramdisk_sha256'], rec(SCZ, Z)['ramdisk_sha256'])
        self.assertEqual(rec(SCV, V)['ramdisk1_reserve'], rec(SCZ, Z)['ramdisk1_reserve'])
        self.assertEqual((rec(SCV, V)['adt_off'], rec(SCV, V)['adt_size']), (rec(SCZ, Z)['adt_off'], rec(SCZ, Z)['adt_size']))
        self.assertEqual(z['nat152_changes']['loader_sites_check'], dict(rc=0, verdict='ok', bad=0))

    def test_payload_diff(self):
        a = (SCV / V / 'Image.payload').read_bytes()
        b = (SCZ / Z / 'Image.payload').read_bytes()
        self.assertEqual(len(a), len(b))
        cv = rec(SCV, V)['cmdline'].encode()
        at = a.find(cv)
        self.assertGreater(at, 0)
        self.assertEqual(b.find(rec(SCZ, Z)['cmdline'].encode()), at)
        outside = [i for i in range(len(a)) if a[i] != b[i] and not at <= i < at + len(cv)]
        # the rest: tag-derived immediates in the loader's markerlib52/ckpt3 code, inside the loader image (first 0x10000 bytes)
        self.assertTrue(outside and max(outside) < 0x10000, (len(outside), max(outside) if outside else None))
        self.assertLess(len(outside), 32)
        # from the command line on, everything (XNU segments, ADT, md0) is identical
        self.assertEqual(a[at + len(cv):], b[at + len(cv):])


class Driver(unittest.TestCase):
    def test_fbscale_source(self):
        s = DRIVER.read_text()
        self.assertIn('static TUNABLE(uint32_t, gFBScale, "fbscale", 0);', s)
        self.assertIn('#define kFBPointsWide           375', s)
        self.assertIn('#define kFBPointsHigh           812', s)
        m = re.search(r'if \(gFBScale != 0 && gFBScale != kFBDefaultScale\) \{(.*?)\n\t\}\n', s, re.S)
        self.assertIsNotNone(m)
        self.assertIn('fWidth = kFBPointsWide * scale;', m[1])
        self.assertIn('fHeight = kFBPointsHigh * scale;', m[1])
        self.assertIn('"display-scale"', m[1])
        self.assertIn('"artwork-scale-factor"', m[1])
        self.assertEqual((375 * 2, 812 * 2), (750, 1624))
        # the run table is built for any nearest-neighbour map (NAT-183 tests 750 -> 1080 byte for byte)
        self.assertIn('fColumnRun[n].from = fColumn[x];', s)
        self.assertIn('750', (ROOT / 'docs/procedures/nat-183/test_nat183.py').read_text())


class Analyser(unittest.TestCase):
    def test_bbd188_without_touch_lat(self):
        b = _load('bbd188', ROOT / 'docs/procedures/nat-187/bbd188.py')
        text = LOG186.read_text(encoding='utf-8', errors='replace')
        stripped = '\n'.join(l for l in text.splitlines() if 'tl: ' not in l)
        self.assertLess(len(stripped), len(text))
        full, cut = b.analyse(text, b.BASELINE_MS), b.analyse(stripped, b.BASELINE_MS)
        self.assertEqual(full['ms_per_frame_median'], b.BASELINE_MS)
        self.assertEqual(cut['ms_per_frame_median'], full['ms_per_frame_median'])
        self.assertEqual(cut['rows'], full['rows'])

    def test_session_derivation(self):
        r = subprocess.run([sys.executable, '-B', str(HERE / 'derive194.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        p = json.loads((ROOT / 'artifacts/nat-193/package-001/package.json').read_text())['images'][Z]
        s = (HERE / 'session_nat194.py').read_text()
        self.assertIn(p['recovery_sha256'], s)
        self.assertIn(p['payload_sha256'], s)
        self.assertEqual(p['recovery_sha256'], hashlib.sha256((ROOT / 'artifacts/nat-193/package-001' / Z / 'recovery.img').read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main(verbosity=2)
