#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scB: scA (NAT-129) with the NAT-139 touch kernel (USI SPI9 pad order CLK gpp9-0 / MOSI 1 / MISO 2 / CS 3 and a read-only
MISO level check before the same three bounded ID polls) and msgbuf=1048576, so the kernel's PMIC rail readback lines are not
overwritten by the lsd CPU-monitor flood in the 128 KiB default ring (NAT-137). Host build only.

Relative to scA (NAT-129):
  kernel   artifacts/nat-139/kernel-001 (only e1s_touch.o differs from NAT-128's kernel after path normalisation)
  tokens   + msgbuf=1048576 (XNU subr_log.c oslog_init_msgbuf, MAX_MSG_BSIZE 1 MiB)
  base     ufs_write=0 dropped as well (cmdline bound 255 bytes): its only reader (redwood_ufs.c) enables writes on == 1
           alone, so the token is the same as its absence; e1sufs=0 stays and the kernel is the no-storage build
  engine   NAT-130's (as us1/scA)

  python3 docs/procedures/nat-139/build.py --out artifacts/nat-139/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scB-md1'
TAG = 'nat_attempt=NAT139-scB'
KERNEL_DIR = ROOT / 'artifacts/nat-139/kernel-001'
TOKENS = ('e1s_wdt_pet=1', 'e1s_decon_hw=1', 'e1spmic=2', 'e1skeys=0', 'msgbuf=1048576')
EXTRA_DROP = ('e1sufs_probe=0', 'ufs_write=0')
ENGINE = HERE.parent / 'nat-130' / 'engine'
spec = importlib.util.spec_from_file_location('nat139_build123', HERE.parent / 'nat-123/build.py')
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
    report['nat139_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), tokens=list(TOKENS),
                                    dropped_base=list(EXTRA_DROP), engine_dir=str(ENGINE.relative_to(ROOT)), engine=want,
                                    cmdline_bytes=len(cmd.encode()),
                                    purpose='USI pin map touch ID read with rails on, keys off, 1 MiB kernel log ring')
    report['nat139_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
