#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""e2m: e2s (NAT-201, ran in NAT-202: ten CPUs, mediaserverd's call through address 0 recorded) with the md0 root
artifacts/nat-203/pid1-sc2-hbm (build_hbm_root.py: NAT-110's tree + the donor's libhakios.media.dylib inserted into mediaserverd,
which empties the portrait-filter prewarm). Kernel, loader and command line are e2s's; only the tag and the ramdisk change. The
user-exception trace stays on, so the run shows whether mediaserverd still faults. Host build only.

  python3 -B docs/procedures/nat-203/build.py --out artifacts/nat-203/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-203/pid1-sc2-hbm/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-e2m-md1'
TAG = 'nat_attempt=NAT203-e2m'
RAMDISK_SHA256 = '9a1eaab6f0a3fa278dc99ff6656a38658de8b212391eecf8dca5ba7d41c4d43d'
PIN_MODULE = 'nat115_nat113_build'          # nat-113/build.py as the chain loads it (as NAT-187): its MD0_SHA256 pins the small root
OLD_MD0 = '6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b201 = _load('nat203_build201', HERE.parent / 'nat-201/build.py')


def main():
    assert len(NAME) == len(b201.NAME) and len(TAG) == len(b201.TAG)
    args = list(sys.argv)
    rd = Path(args[args.index('--ramdisk') + 1])
    assert hashlib.sha256(rd.read_bytes()).hexdigest() == RAMDISK_SHA256, 'ramdisk is not NAT-203 pid1-sc2-hbm'
    rec = json.loads((rd.parent / 'build.json').read_text())
    assert rec['root_apfs']['sha256'] == RAMDISK_SHA256 and all(rec['apfs_tool_readback'].values()), 'md0 build record'
    pin = sys.modules[PIN_MODULE]
    i = pin.FIELDS.index('MD0_SHA256')
    assert pin.VALUES[i] == OLD_MD0 and pin.MD0_SHA256 == OLD_MD0
    old_pin = (pin.MD0_SHA256, pin.VALUES)
    saved = (b201.NAME, b201.TAG)
    b201.NAME, b201.TAG = NAME, TAG
    pin.MD0_SHA256, pin.VALUES = RAMDISK_SHA256, pin.VALUES[:i] + (RAMDISK_SHA256,) + pin.VALUES[i + 1:]
    try:
        b201.main()
    finally:
        sys.argv = args
        b201.NAME, b201.TAG = saved
        pin.MD0_SHA256, pin.VALUES = old_pin
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat201_changes']['note'] = 'NAT-203 build: tag and ramdisk replaced (see nat203_changes)'
    report['nat203_changes'] = dict(kernel=report['nat201_changes']['kernel'], tag=TAG, ramdisk=str(rd), ramdisk_sha256=RAMDISK_SHA256,
                                    purpose="e2s with mediaserverd's portrait-filter prewarm emptied by the donor's libhakios.media.dylib")
    report['nat203_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'build_hbm_root.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
