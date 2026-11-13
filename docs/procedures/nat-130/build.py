#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""us1 = sc9 (docs/procedures/nat-126/build.py, unchanged) with ONE difference: the loader's USB engine is the NAT-130 engine
(docs/procedures/nat-130/engine: checksum modes, SUM, GET_RXT) instead of NAT-076's. Kernel, ADT, cmdline tokens, md0/md1 and
every bound are sc9's. Host build only.

  python3 docs/procedures/nat-130/build.py --out artifacts/nat-130/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE130 = HERE / 'engine'
NAME = 'loader-diag-xnu-us1-md1'
TAG = 'nat_attempt=NAT130-us1'
spec = importlib.util.spec_from_file_location('nat130_build126', HERE.parent / 'nat-126/build.py')
b126 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b126)


def chain_b79(b):
    """The NAT-079 build module that b126 reaches (it sets the loader's engine directory from its ENGINE76)."""
    for attr in ('b123', 'b119', 'b117', 'b115', 'b113', 'b106', 'b104', 'b102', 'b87', 'b85', 'b83', 'b79'):
        b = getattr(b, attr)
    assert Path(b.__file__).parent.name == 'nat-079', b.__file__
    return b


def main():
    b79 = chain_b79(b126)
    saved = (b79.ENGINE76, b126.NAME, b126.TAG)
    b79.ENGINE76 = ENGINE130
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
    want = {f: hashlib.sha256((ENGINE130 / f).read_bytes()).hexdigest() for f in eng}
    assert eng and eng == want, 'the build did not use the NAT-130 engine: %s' % eng
    cmd = report['payload_fixes'][NAME]['cmdline']
    assert TAG in cmd.split() and 'e1spmic=0' in cmd.split()
    report['nat130_changes'] = dict(engine_dir=str(ENGINE130.relative_to(HERE.parents[2])), engine=want, base_image='loader-diag-xnu-sc9-md1',
                                    purpose='USB 2.0 delivery speed: checksum modes, SUM post-verify, GET_RXT phase ticks; nothing else differs from sc9')
    report['nat130_sources'] = {f: hashlib.sha256((HERE / f).read_bytes()).hexdigest() for f in ('build.py', 'root_send130.py', 'deliver130.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
