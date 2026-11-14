#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scV: scU (NAT-183, ran in NAT-184: K2, driver 2.16 ms) with a read-only per-process CPU-time sampler in bsd/e1s_display.o
(e1s_display.patch = NAT-176's display snapshot plus the sampler: recount_task_times over proc_iterate every 5 s from 200 to 380 s).
The kernel (artifacts/nat-185/kernel-001) is NAT-183's with that object rebuilt from the new patch; the command line is scU's with the
tag changed. Host build only.

  python3 -B docs/procedures/nat-185/build.py --out artifacts/nat-185/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scV-md1'
TAG = 'nat_attempt=NAT185-scV'
KERNEL_DIR = ROOT / 'artifacts/nat-185/kernel-001'
PATCH = 'docs/procedures/nat-185/e1s_display.patch'
TOP_STRING = 'e1s-top: %u s span %llu us busy %llu us kernel %llu us idle0 %llu us procs %u lost %u'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b183 = _load('nat185_build183', HERE.parent / 'nat-183/build.py')


def check_kernel():
    """NAT-183's kernel record with only bsd/e1s_display.o's patch replaced by PATCH, and one expect-string more."""
    a = json.loads((ROOT / 'artifacts/nat-183/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(old) == set(new), (old, new)
    assert {k: v for k, v in new.items() if v != old[k]} == {'bsd/e1s_display.o': PATCH}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'] == dict(a['expect_strings'], **{TOP_STRING: 1}), r['expect_strings']
    assert r['undefined_symbols'] == 0
    return r


def main():
    assert len(NAME) == len(b183.NAME) and len(TAG) == len(b183.TAG)
    rec = check_kernel()
    saved = (b183.NAME, b183.TAG, b183.KERNEL_DIR, b183.check_kernel)
    b183.NAME, b183.TAG, b183.KERNEL_DIR, b183.check_kernel = NAME, TAG, KERNEL_DIR, lambda: rec
    args = list(sys.argv)
    try:
        b183.main()
    finally:
        sys.argv = args
        b183.NAME, b183.TAG, b183.KERNEL_DIR, b183.check_kernel = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat183_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat183_changes']['note'] = 'NAT-185 build: kernel and tag replaced (see nat185_changes); the run table is kept'
    report['nat185_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_display_patch=PATCH,
                                    tag=TAG, purpose='read-only per-process CPU-time sampler (e1s-top) beside the display snapshot')
    report['nat185_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in (
        'build.py', 'e1s_display.patch', 'rebuild-args.json', 'host/shim185.h', 'host/fake185.c', 'test_nat185.py', 'top186.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
