#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""pk1 = us1 (docs/procedures/nat-130/build.py = sc9 + NAT-130 engine) with ONE difference: the loader's USB engine is the NAT-134
engine (docs/procedures/nat-134/engine = NAT-130's plus the read-only PEEK request over a fixed table). Kernel, ADT, cmdline
tokens, md0/md1 and every bound are sc9's. Host build only.

  python3 docs/procedures/nat-134/build.py --out artifacts/nat-134/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE134 = HERE / 'engine'
NAME = 'loader-diag-xnu-pk1-md1'
TAG = 'nat_attempt=NAT134-pk1'          # same length as NAT-130's tag
spec = importlib.util.spec_from_file_location('nat134_build130', HERE.parent / 'nat-130/build.py')
b130 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b130)
b126 = b130.b126


def main():
    assert len(TAG) == len(b130.TAG)
    b79 = b130.chain_b79(b126)
    saved = (b79.ENGINE76, b126.NAME, b126.TAG)
    b79.ENGINE76 = ENGINE134
    b126.NAME, b126.TAG = NAME, TAG
    args = list(sys.argv)
    try:
        b126.main()
    finally:
        b79.ENGINE76, b126.NAME, b126.TAG = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    eng = report.get('nat079_engine', {})
    want = {f: hashlib.sha256((ENGINE134 / f).read_bytes()).hexdigest() for f in eng}
    assert eng and eng == want, 'the build did not use the NAT-134 engine: %s' % eng
    cmd = report['payload_fixes'][NAME]['cmdline']
    assert TAG in cmd.split() and 'e1spmic=0' in cmd.split()
    report['nat134_changes'] = dict(engine_dir=str(ENGINE134.relative_to(HERE.parents[2])), engine=want, base_image='loader-diag-xnu-us1-md1',
                                    purpose='read-only SuperSpeed prerequisite probe (PEEK over a fixed table, NAT-131 section 5); nothing else differs from us1')
    report['nat134_sources'] = {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in ('build.py', 'peek134.py', 'deliver134.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
