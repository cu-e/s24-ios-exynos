#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-187 host tests: the accessibility root differs from NAT-110's by exactly the plist and the var.skel line; the plist holds
exactly the two booleans; domain and keys are strings of the donor dyld shared cache (when present locally); the image build used
that root and NAT-185's kernel; the analyser bbd188.py and its registered baseline."""
import hashlib
import importlib.util
import json
import plistlib
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AX = ROOT / 'artifacts/nat-187/pid1-sc2-hb-ax'
BASE = ROOT / 'artifacts/nat-110/pid1-sc2-hb'
CACHE = ROOT / 'artifacts/apple-inputs/work/cryptex-os/System/Library/Caches/com.apple.dyld'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


class Root(unittest.TestCase):
    def test_tree_diff(self):
        def files(r):
            return {str(p.relative_to(r)): p.read_bytes() for p in r.rglob('*') if p.is_file() and not p.is_symlink()}
        a, b = files(BASE / 'root'), files(AX / 'root')
        self.assertEqual(sorted(set(b) - set(a)), ['var/mobile/Library/Preferences/com.apple.Accessibility.plist'])
        self.assertEqual(sorted(set(a) - set(b)), [])
        self.assertEqual(sorted(k for k in a if a[k] != b[k]), ['etc/var.skel'])
        extra = set(b['etc/var.skel'].decode().splitlines()) - set(a['etc/var.skel'].decode().splitlines())
        self.assertEqual(extra, {'f\t644\t501\t501\t/private/var/mobile/Library/Preferences/com.apple.Accessibility.plist\t'
                                 '/var/mobile/Library/Preferences/com.apple.Accessibility.plist'})
        p = AX / 'root/var/mobile/Library/Preferences/com.apple.Accessibility.plist'
        self.assertEqual(p.stat().st_mode & 0o777, 0o644)
        self.assertEqual(plistlib.loads(p.read_bytes()), {'EnhancedBackgroundContrastEnabled': True, 'ReduceMotionEnabled': True})
        self.assertTrue(p.read_bytes().startswith(b'bplist00'))

    def test_build_record(self):
        rec = json.loads((AX / 'build.json').read_text())
        self.assertEqual(rec['root_apfs']['sha256'], hashlib.sha256((AX / 'root.apfs').read_bytes()).hexdigest())
        self.assertEqual(rec['root_apfs']['bytes'], 4194304)
        self.assertEqual(rec['kernel_apfs_lib_readback']['mismatches'], [])
        self.assertEqual(rec['kernel_apfs_lib_readback']['files_compared'], rec['files'])
        b = json.loads((ROOT / 'artifacts/nat-187/build-001/build.json').read_text())
        self.assertEqual(b['nat187_changes']['md0_sha256'], rec['root_apfs']['sha256'])
        self.assertEqual(b['nat115_changes']['md0_sha256'], rec['root_apfs']['sha256'])
        self.assertEqual(b['nat187_changes']['kernel'], 'd7e7fee154104aaf9c59a4d2145c3901763259296ebd85cb373c388a4667c8b3')

    def test_keys_in_donor(self):
        f = CACHE / 'dyld_shared_cache_arm64.05'
        if not f.exists():
            self.skipTest('donor cache not present')
        data = f.read_bytes()
        for s in (b'\x00EnhancedBackgroundContrastEnabled\x00', b'\x00ReduceMotionEnabled\x00', b'\x00com.apple.Accessibility\x00'):
            self.assertIn(s, data)


class Analyser(unittest.TestCase):
    def test_verdicts_and_baseline(self):
        a = _load('t187_bbd188', HERE / 'bbd188.py')
        self.assertEqual(a.BASELINE_MS, 67.95)
        self.assertEqual(a.analyse('', 67.95)['verdict'], 'B-none')
        def text(bbd_us, frames):
            out = []
            for t in range(220, 260, 5):
                out.append('[%7.3f]: MiniIOMobileFramebuffer: %d frames in 5000 ms (x a second), 1 us each\n' % (t - 0.5, frames))
                out.append('[%7.3f]: e1s-top: %d s span 5000000 us busy 5000000 us kernel 1 us idle0 0 us procs 9 lost 0\n' % (t, t))
                out.append('[%7.3f]: e1s-top: %d s top backboardd[16] %d SpringBoard[12] 5\n' % (t, t, bbd_us))
            return ''.join(out)
        for frames, v in ((200, 'B2'), (118, 'B2'), (117, 'B1'), (74, 'B1'), (73, 'B0')):
            r = a.analyse(text(4_000_000, frames), 67.95)
            self.assertEqual(r['verdict'], v, (frames, r['ms_per_frame_median']))
        nat186 = ROOT / 'artifacts/nat-186/analysis/kernel-text.txt'
        if nat186.exists():
            self.assertEqual(a.analyse(nat186.read_text(errors='replace'), 67.95)['ms_per_frame_median'], 67.95)


if __name__ == '__main__':
    unittest.main()
