#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scU: scS (NAT-176, ran in NAT-177: R-ok, F30 again) with the framebuffer driver's nearest-neighbour scaling copying a run table of
consecutive picture columns built once per layer in drawLayer() (MiniIOMobileFramebuffer.patch, NAT-182: 2.3 vs 7.4 ms; same pixels,
test_nat183.py). Software only: no display register is touched by the change. The kernel (artifacts/nat-183/kernel-001) is NAT-176's
with iokit/MiniIOMobileFramebuffer.cpo added; the command line is scS's with the tag changed. Host build only.

  python3 -B docs/procedures/nat-183/build.py --out artifacts/nat-183/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scU-md1'
TAG = 'nat_attempt=NAT183-scU'
KERNEL_DIR = ROOT / 'artifacts/nat-183/kernel-001'
PATCH = 'docs/procedures/nat-183/MiniIOMobileFramebuffer.patch'
OBJECT = 'iokit/MiniIOMobileFramebuffer.cpo'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b176 = _load('nat183_build176', HERE.parent / 'nat-176/build.py')


def check_kernel():
    """NAT-176's kernel record plus exactly one extra object, the framebuffer driver from PATCH; same expect-strings."""
    a = json.loads((ROOT / 'artifacts/nat-176/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert {k: v for k, v in new.items() if k not in old} == {OBJECT: PATCH}, new
    assert {k: v for k, v in new.items() if k in old} == old
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'] == a['expect_strings'], r['expect_strings']
    assert r['undefined_symbols'] == 0
    return r


class _Json123(b176._Json123):
    """NAT-176's view for nat-123/build.py's four-object check, also without the framebuffer object (check_kernel() verified it)."""

    def loads(self, s, *a, **kw):
        r = super().loads(s, *a, **kw)
        if isinstance(r, dict) and r.get('schema') == 'krn044-rebuild-v1' and r.get('no_storage_sha256') == self.sha:
            r = dict(r, extra_objects=[e for e in r['extra_objects'] if e['object'] != OBJECT])
        return r


def main():
    assert len(NAME) == len(b176.NAME) and len(TAG) == len(b176.TAG)
    rec = check_kernel()
    saved = (b176.NAME, b176.TAG, b176.KERNEL_DIR, b176.check_kernel, b176._Json123)
    b176.NAME, b176.TAG, b176.KERNEL_DIR, b176.check_kernel, b176._Json123 = NAME, TAG, KERNEL_DIR, lambda: rec, _Json123
    args = list(sys.argv)
    try:
        b176.main()
    finally:
        sys.argv = args
        b176.NAME, b176.TAG, b176.KERNEL_DIR, b176.check_kernel, b176._Json123 = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat176_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat176_changes']['note'] = 'NAT-183 build: kernel and tag replaced (see nat183_changes); the display snapshot is kept'
    report['nat183_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), framebuffer_patch=PATCH,
                                    tag=TAG, purpose='nearest-neighbour scaling copies a per-layer run table of consecutive picture columns with memcpy')
    report['nat183_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in (
        'build.py', 'MiniIOMobileFramebuffer.patch', 'rebuild-args.json', 'test_nat183.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
