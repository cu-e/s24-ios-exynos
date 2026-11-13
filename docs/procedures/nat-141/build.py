#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scC: scB (NAT-139) with the NAT-141 touch kernel: after the three ID polls, a controller that answered gets Samsung's
screen-on start sequence (system reset FA 20 00 00 24 81 + READY wait, CLEAR_ALL_EVENT, scan mode A0 00 01 + echo, SENSE_ON)
and a polled 0x87 event thread that posts coordinates to /dev/hakios-touch (no IRQ, no calibration, no flash write); gpa1-2 pull
set to NONE as Android's tsp_int_active. Cmdline, engine and root as scB. Host build only.

  python3 docs/procedures/nat-141/build.py --out artifacts/nat-141/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scC-md1'
TAG = 'nat_attempt=NAT141-scC'
KERNEL_DIR = ROOT / 'artifacts/nat-141/kernel-001'
TOKENS = ('e1s_wdt_pet=1', 'e1s_decon_hw=1', 'e1spmic=2', 'e1skeys=0', 'msgbuf=1048576')
EXTRA_DROP = ('e1sufs_probe=0', 'ufs_write=0')
ENGINE = HERE.parent / 'nat-130' / 'engine'
spec = importlib.util.spec_from_file_location('nat141_build123', HERE.parent / 'nat-123/build.py')
b123 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b123)


def chain(b, attrs):
    for a in attrs:
        b = getattr(b, a)
    return b


def main():
    b119 = b123.b119
    b115 = chain(b119, ('b117', 'b115'))
    b79 = chain(b115, ('b113', 'b106', 'b104', 'b102', 'b87', 'b85', 'b83', 'b79'))
    assert Path(b79.__file__).parent.name == 'nat-079' and Path(b115.__file__).parent.name == 'nat-115'
    assert len(NAME) == len(b115.NAME) and len(TAG) == len(b115.NEW_TAG)
    saved = (b123.NAME, b123.TAG, b123.KERNEL_DIR, b123.TOKENS, b115.DROP_BASE_TOKENS, b79.ENGINE76)
    b123.NAME, b123.TAG, b123.KERNEL_DIR, b123.TOKENS = NAME, TAG, KERNEL_DIR, TOKENS
    b115.DROP_BASE_TOKENS = tuple(b115.DROP_BASE_TOKENS) + EXTRA_DROP
    b79.ENGINE76 = ENGINE
    args = list(sys.argv)
    try:
        b123.main()
    finally:
        sys.argv = args
        b123.NAME, b123.TAG, b123.KERNEL_DIR, b123.TOKENS, b115.DROP_BASE_TOKENS, b79.ENGINE76 = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    tokens = cmd.split()
    for t in TOKENS + (TAG, 'e1sufs=0', 'e1sbattery=0', 'rd=md1', 'xrd=md0'):
        assert tokens.count(t) == 1, t
    for t in EXTRA_DROP + ('e1spmic=0', 'e1stouch=0', 'e1spmic=3', 'ufs_write=1'):
        assert t not in tokens, t
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    rec = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    eng = report.get('nat079_engine', {})
    want = {f: hashlib.sha256((ENGINE / f).read_bytes()).hexdigest() for f in eng}
    assert eng and eng == want, 'the build did not use the NAT-130 engine'
    report['nat141_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), tokens=list(TOKENS),
                                    dropped_base=list(EXTRA_DROP), engine_dir=str(ENGINE.relative_to(ROOT)), engine=want,
                                    cmdline_bytes=len(cmd.encode()),
                                    purpose='STM screen-on start sequence and polled event thread on the verified pins')
    report['nat141_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
