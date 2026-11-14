#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scS: scR (NAT-174, ran in NAT-175: F30 under synthetic swipes) with a read-only display-layer snapshot in bsd/e1s_display.o
(e1s_display.patch: PMU DPUB/DPUF0/DPUF1 status gates loads of DECON, windows 2/3, DMA/DPP/SRAMC L0/L1 and SysMMU, at probe and at
300 s uptime). The kernel (artifacts/nat-176/kernel-001) is NAT-174's with that one object added; the command line is scR's with the
tag changed. Host build only.

  python3 -B docs/procedures/nat-176/build.py --out artifacts/nat-176/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scS-md1'
TAG = 'nat_attempt=NAT176-scS'
KERNEL_DIR = ROOT / 'artifacts/nat-176/kernel-001'
PATCH = 'docs/procedures/nat-176/e1s_display.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b174 = _load('nat176_build174', HERE.parent / 'nat-174/build.py')


def check_kernel():
    """NAT-174's kernel record plus exactly one extra object, bsd/e1s_display.o from PATCH, and its expect-string."""
    a = json.loads((ROOT / 'artifacts/nat-174/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert {k: v for k, v in new.items() if k not in old} == {'bsd/e1s_display.o': PATCH}, new
    assert {k: v for k, v in new.items() if k in old} == old
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'] == dict(a['expect_strings'], **{'e1s-dpp: %s pmu dpub %#x dpuf0 %#x dpuf1 %#x': 1}), r['expect_strings']
    assert r['undefined_symbols'] == 0
    return r


b152 = b174.b165.b152


class _Json123(b152._Json123):
    """NAT-152's view for nat-123/build.py's four-object check, also without bsd/e1s_display.o (check_kernel() verified it)."""

    def loads(self, s, *a, **kw):
        r = super().loads(s, *a, **kw)
        if isinstance(r, dict) and r.get('schema') == 'krn044-rebuild-v1' and r.get('no_storage_sha256') == self.sha:
            r = dict(r, extra_objects=[e for e in r['extra_objects'] if e['object'] != 'bsd/e1s_display.o'])
        return r


def main():
    assert len(NAME) == len(b174.NAME) and len(TAG) == len(b174.TAG)
    rec = check_kernel()
    saved = (b174.NAME, b174.TAG, b174.KERNEL_DIR, b174.check_kernel, b152._Json123)
    b174.NAME, b174.TAG, b174.KERNEL_DIR, b174.check_kernel = NAME, TAG, KERNEL_DIR, lambda: rec
    b152._Json123 = _Json123
    args = list(sys.argv)
    try:
        b174.main()
    finally:
        sys.argv = args
        b174.NAME, b174.TAG, b174.KERNEL_DIR, b174.check_kernel, b152._Json123 = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat152_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat174_changes']['note'] = 'NAT-176 build: kernel and tag replaced (see nat176_changes); the swipe thread and touch_lat=1 are kept'
    report['nat176_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_display_patch=PATCH,
                                    tag=TAG, purpose='read-only display-layer snapshot (NAT-162 table) gated on PMU DPUB/DPUF0/DPUF1 status')
    report['nat176_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in (
        'build.py', 'e1s_display.patch', 'rebuild-args.json', 'host/fakemmio176.c', 'host/shim176.h', 'test_nat176.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
