#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scN: scM (NAT-165, ran in NAT-166) with the touch driver's SPI half-bit default cut from 400 to 8 loops. NAT-166 found cpu0 busy in
every second, and the touch event thread spending ~9.3 ms of busy bit-banging per 10 ms poll. The kernel (artifacts/nat-167/kernel-001)
is NAT-165's with one change, bsd/e1s_touch.o built from e1s_touch_combined.patch = NAT-143's patch plus the new default line.
Command line: scM's (cpuload=1000 kept, to measure the effect) with the tag changed. Host build only.

  python3 -B docs/procedures/nat-167/build.py --out artifacts/nat-167/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scN-md1'
TAG = 'nat_attempt=NAT167-scN'
KERNEL_DIR = ROOT / 'artifacts/nat-167/kernel-001'
PATCH = 'docs/procedures/nat-167/e1s_touch_combined.patch'
OLD_PATCH = 'docs/procedures/nat-143/e1s_touch_combined.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b165 = _load('nat167_build165', HERE.parent / 'nat-165/build.py')
b152 = b165.b152


def patch_delta():
    """The new patch adds/removes exactly NAT-143's lines plus the half-bit default (and its comment)."""
    pm = lambda t: [l for l in t.splitlines() if l[:1] in '+-' and l[:3] not in ('+++', '---')]
    a, b = pm((ROOT / OLD_PATCH).read_text()), pm((ROOT / PATCH).read_text())
    extra = [l for l in b if l not in a]
    assert all(l in b for l in a), 'NAT-143 lines missing'
    code = [l for l in extra if not l[1:].strip().startswith(('/*', '*'))]
    assert code == ['-static uint32_t e1s_halfbit = 400;', '+static uint32_t e1s_halfbit = 8;'], code
    return extra


def check_kernel():
    """NAT-165's kernel record with exactly one change: bsd/e1s_touch.o built from PATCH."""
    a = json.loads((ROOT / 'artifacts/nat-165/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(old) == set(new)
    assert {k: v for k, v in new.items() if v != old[k]} == {'bsd/e1s_touch.o': PATCH}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'] == a['expect_strings'] and r['undefined_symbols'] == 0
    return r


def main():
    assert len(NAME) == len(b165.NAME) and len(TAG) == len(b165.TAG)
    patch_delta()
    rec = check_kernel()
    saved = (b165.NAME, b165.TAG, b165.KERNEL_DIR, b165.check_kernel)
    b165.NAME, b165.TAG, b165.KERNEL_DIR, b165.check_kernel = NAME, TAG, KERNEL_DIR, lambda: rec
    args = list(sys.argv)
    try:
        b165.main()
    finally:
        sys.argv = args
        b165.NAME, b165.TAG, b165.KERNEL_DIR, b165.check_kernel = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat165_changes']['kernel'] == rec['no_storage_sha256'] and report['nat152_changes']['kernel'] == rec['no_storage_sha256']
    report['nat167_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_touch_patch=PATCH,
                                    tag=TAG, purpose='touch SPI half-bit default 400 -> 8: the poll thread off most of cpu0')
    report['nat167_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'e1s_touch_combined.patch')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
