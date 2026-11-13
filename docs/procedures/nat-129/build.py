#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scA: the NAT-128 polling-only touch ID kernel with the two touch rails enabled (e1spmic=2: LDO18 0x3d=0xd8 1.8 V, LDO9
0x34=0xf0 3.0 V, NAT-123's allowlist and exact readbacks) and the key thread disabled (e1skeys=0: no recurring PMIC power-key
reads), on the us1 loader (NAT-130 USB engine, 37 MB/s in NAT-132). Host build only.

Relative to sc9 (NAT-126) / us1 (NAT-130):
  kernel   artifacts/nat-128/kernel-001 (NAT-128: three bounded ID read attempts, no IRQ, no event thread)
  tokens   e1spmic=0 -> e1spmic=2, + e1skeys=0
  base     e1sufs_probe=0 dropped (cmdline bound 255 bytes): its only reader, e1s_ufs_probe(), returns on e1sufs=0 first,
           and e1sufs=0 stays
  engine   NAT-130's (as us1)

  python3 docs/procedures/nat-129/build.py --out artifacts/nat-129/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scA-md1'
TAG = 'nat_attempt=NAT129-scA'
KERNEL_DIR = ROOT / 'artifacts/nat-128/kernel-001'
TOKENS = ('e1s_wdt_pet=1', 'e1s_decon_hw=1', 'e1spmic=2', 'e1skeys=0')
EXTRA_DROP = ('e1sufs_probe=0',)
ENGINE = HERE.parent / 'nat-130' / 'engine'
spec = importlib.util.spec_from_file_location('nat129_build123', HERE.parent / 'nat-123/build.py')
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
    for t in TOKENS + (TAG, 'e1sufs=0', 'ufs_write=0', 'e1sbattery=0', 'rd=md1', 'xrd=md0'):
        assert tokens.count(t) == 1, t
    for t in EXTRA_DROP + ('e1spmic=0', 'e1stouch=0', 'e1spmic=3'):
        assert t not in tokens, t
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    rec = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    eng = report.get('nat079_engine', {})
    want = {f: hashlib.sha256((ENGINE / f).read_bytes()).hexdigest() for f in eng}
    assert eng and eng == want, 'the build did not use the NAT-130 engine'
    report['nat129_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), tokens=list(TOKENS),
                                    dropped_base=list(EXTRA_DROP), engine_dir=str(ENGINE.relative_to(ROOT)), engine=want,
                                    cmdline_bytes=len(cmd.encode()),
                                    purpose='bounded polling touch ID read with both touch rails on and the key thread off')
    report['nat129_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
