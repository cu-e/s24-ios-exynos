#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scW: scV (NAT-185, ran in NAT-186: backboardd 76 % of the only core) with the md0 root of build_ax_root.py (NAT-110's plus
com.apple.Accessibility.plist: Reduce Transparency and Reduce Motion). Same kernel (artifacts/nat-185/kernel-001) and command line
(tag changed); only the small root and its pinned hash differ. Host build only.

  python3 -B docs/procedures/nat-187/build.py --out artifacts/nat-187/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-187/pid1-sc2-hb-ax/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scW-md1'
TAG = 'nat_attempt=NAT187-scW'
MD0 = ROOT / 'artifacts/nat-187/pid1-sc2-hb-ax/root.apfs'
PIN_MODULE = 'nat115_nat113_build'          # nat-113/build.py as the chain loads it: its MD0_SHA256 is the pinned small root


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b185 = _load('nat187_build185', HERE.parent / 'nat-185/build.py')


def md0_sha():
    rec = json.loads((MD0.parent / 'build.json').read_text())
    sha = hashlib.sha256(MD0.read_bytes()).hexdigest()
    assert rec['root_apfs']['sha256'] == sha and not rec['kernel_apfs_lib_readback']['mismatches'], 'md0 build record'
    return sha


def main():
    assert len(NAME) == len(b185.NAME) and len(TAG) == len(b185.TAG)
    args = list(sys.argv)
    assert '--ramdisk' in args and Path(args[args.index('--ramdisk') + 1]).resolve() == MD0.resolve(), 'pass --ramdisk ' + str(MD0)
    sha = md0_sha()
    pin = sys.modules[PIN_MODULE]
    i = pin.FIELDS.index('MD0_SHA256')
    old_pin = (pin.MD0_SHA256, pin.VALUES)
    assert pin.VALUES[i] == '6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c'
    saved = (b185.NAME, b185.TAG)
    b185.NAME, b185.TAG = NAME, TAG
    pin.MD0_SHA256, pin.VALUES = sha, pin.VALUES[:i] + (sha,) + pin.VALUES[i + 1:]
    try:
        b185.main()
    finally:
        sys.argv = args
        b185.NAME, b185.TAG = saved
        pin.MD0_SHA256, pin.VALUES = old_pin
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat185_changes']['note'] = 'NAT-187 build: md0 root and tag replaced (see nat187_changes); kernel unchanged'
    report['nat187_changes'] = dict(md0=str(MD0.relative_to(ROOT)), md0_sha256=sha, tag=TAG, kernel=report['nat185_changes']['kernel'],
                                    purpose='Reduce Transparency + Reduce Motion preferences in the delivered small root')
    report['nat187_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'build_ax_root.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
