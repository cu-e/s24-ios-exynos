#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-187 host build: NAT-110's md0 root (`pid1-sc2-hb`, 396 files) plus the accessibility preferences Reduce Transparency and
Reduce Motion, so the render server (backboardd) draws the blur materials as plain colours.

Exactly two changes against NAT-110's tree:
  1. var/mobile/Library/Preferences/com.apple.Accessibility.plist (0644): a binary plist with EnhancedBackgroundContrastEnabled = true
     (Reduce Transparency) and ReduceMotionEnabled = true (Reduce Motion). The domain and both keys are strings of the donor
     libAccessibility in the iOS 16.5 dyld shared cache (checked by test_nat187.py when the cache is present);
  2. one etc/var.skel line installing it as /private/var/mobile/Library/Preferences/com.apple.Accessibility.plist (0644, 501:501),
     the same form as the eight preference lines NAT-108 added.
Then mkapfs (4 MiB), verify.py content and the kernel apfs_lib readback, as NAT-110 did.

  python3 -B docs/procedures/nat-187/build_ax_root.py [--out artifacts/nat-187/pid1-sc2-hb-ax]
"""
import argparse
import importlib.util
import json
import os
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = ROOT / 'artifacts/nat-110/pid1-sc2-hb'
BASE_SHA256 = '6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c'
BASE_FILES = 396
MD0_BYTES = 4194304
PLIST_REL = 'var/mobile/Library/Preferences/com.apple.Accessibility.plist'
PREFS = {'EnhancedBackgroundContrastEnabled': True, 'ReduceMotionEnabled': True}
SKEL_LINE = ('f\t644\t501\t501\t/private/var/mobile/Library/Preferences/com.apple.Accessibility.plist\t'
             '/var/mobile/Library/Preferences/com.apple.Accessibility.plist\n')
SKEL_AFTER = ('f\t644\t501\t501\t/private/var/mobile/Library/Preferences/com.apple.springboard.plist\t'
              '/var/mobile/Library/Preferences/com.apple.springboard.plist\n')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


B110 = _load('nat187_nat110_root', ROOT / 'docs/procedures/nat-110/build_sc2_hb_root.py')
need, run, sha256_file, tree, tree_diff = B110.need, B110.run, B110.sha256_file, B110.tree, B110.tree_diff


def plist_bytes():
    return plistlib.dumps(PREFS, fmt=plistlib.FMT_BINARY, sort_keys=True)


def build(out_dir, base_dir=BASE, mkapfs=B110.MKAPFS, verify=B110.VERIFY, tool=B110.TOOL):
    for dep in (mkapfs, verify, tool):
        need(Path(dep).is_file(), 'required recipe tool missing: %s' % dep)
    out, base = Path(out_dir), Path(base_dir)
    need(sha256_file(base / 'root.apfs') == BASE_SHA256, 'base root.apfs is not NAT-110\'s')
    before = tree(base / 'root')
    need(sum(1 for v in before.values() if v[0] == 'file') == BASE_FILES, 'base file count changed')
    need(PLIST_REL not in before, 'base already has the accessibility plist')
    shutil.rmtree(out, ignore_errors=True)
    root = out / 'root'
    shutil.copytree(base / 'root', root, symlinks=True)

    p = root / PLIST_REL
    p.write_bytes(plist_bytes())
    os.chmod(p, 0o644)
    skel = root / 'etc/var.skel'
    text = skel.read_text()
    need(text.count(SKEL_AFTER) == 1 and SKEL_LINE not in text, 'var.skel anchor')
    mode = skel.stat().st_mode & 0o7777
    skel.write_text(text.replace(SKEL_AFTER, SKEL_AFTER + SKEL_LINE))
    os.chmod(skel, mode)

    after = tree(root)
    added, removed, changed = tree_diff(before, after)
    need(added == [PLIST_REL], 'unexpected additions: %s' % (added,))
    need(not removed, 'unexpected removals: %s' % (removed,))
    need(changed == ['etc/var.skel'], 'unexpected modifications: %s' % (changed,))

    img = out / 'root.apfs'
    r = run([sys.executable, '-I', str(mkapfs), '-z', '--plain', 'fw', '-o', str(img), 'redwood=' + str(root)])
    need(r.returncode == 0, 'mkapfs.py failed: ' + r.stderr[-600:])
    need(img.stat().st_size == MD0_BYTES, 'root.apfs size %d' % img.stat().st_size)
    r2 = run([sys.executable, '-I', str(verify), 'content', str(img), str(root), '--all'])
    need(r2.returncode == 0, 'verify.py content failed: ' + (r2.stdout + r2.stderr)[-600:])
    kernel = dict(entries=0, files_compared=0, mismatches=[])
    for line in run([str(tool), 'census', str(img)]).stdout.splitlines():
        parts = line.split('\t')
        if len(parts) != 7 or not parts[0].startswith('/'):
            continue
        kernel['entries'] += 1
        path, kind, fmode = parts[0], parts[1], parts[2]
        local = root / path.lstrip('/')
        if kind == '8':
            got = subprocess.run([str(tool), 'cat', str(img), path], capture_output=True, timeout=60).stdout
            kernel['files_compared'] += 1
            if got != local.read_bytes():
                kernel['mismatches'].append(path)
            if int(fmode, 8) & 0o7777 != local.stat().st_mode & 0o7777:
                kernel['mismatches'].append(path + ' (mode)')
    files = sum(1 for v in after.values() if v[0] == 'file')
    need(not kernel['mismatches'] and kernel['files_compared'] == files, 'kernel apfs_lib readback mismatch: %s' % kernel)
    rec = dict(kind='host build record, nothing ran on a phone', base=dict(root_apfs_sha256=BASE_SHA256, files=BASE_FILES),
               added=added, changed=changed, prefs=PREFS, plist_sha256=sha256_file(p), skel_line=SKEL_LINE.rstrip('\n'),
               root_apfs=dict(bytes=img.stat().st_size, sha256=sha256_file(img)),
               verify_content=dict(exit=r2.returncode, tail=(r2.stdout + r2.stderr).strip()[-300:]),
               kernel_apfs_lib_readback=kernel, files=files, script_sha256=sha256_file(Path(__file__)))
    (out / 'build.json').write_text(json.dumps(rec, indent=1, sort_keys=True) + '\n')
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', type=Path, default=ROOT / 'artifacts/nat-187/pid1-sc2-hb-ax')
    a = ap.parse_args(argv)
    rec = build(a.out)
    print(json.dumps(dict(root_apfs=rec['root_apfs'], files=rec['files'], readback_ok=not rec['kernel_apfs_lib_readback']['mismatches'])))


if __name__ == '__main__':
    main()
