#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scH: scF (NAT-148) with the NAT-152 kernel and boot-arg small_cores=0. NAT-150's diagnostics, without moving any kernel address the loader checks
(NAT-151 stopped in the loader because scG's start.patch moved them):
  osfmk/start.o     early marks of a PSCI-started core (start.patch): 1-3 in the reset vector as NAT-150; 4-6 out of line in the rest
                    of the reset vector page, reached through branches that take the place of existing ones (same size)
  osfmk/psci_smp.o  NAT-150's patch, unchanged: marks cleared before CPU_ON, read and printed with AFFINITY_INFO; 1 s start wait
  small_cores=0     the "small-core" ADT flag no longer makes a core a slower core's secondary (no pairing at all), in place of NAT-150's
                    machine_routines change, which moved _set_mmu_ttb
Gate: check_loader_sites.py (the loader's own nat036_check on the built payload) must return rc 0, and every loader constant must name
the same symbol+offset as in the NAT-143 kernel. Host build only.

  python3 -B docs/procedures/nat-152/build.py --out artifacts/nat-152/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scH-md1'
TAG = 'nat_attempt=NAT152-scH'
KERNEL_DIR = ROOT / 'artifacts/nat-152/kernel-001'
PATCHES = {'osfmk/start.o': 'start.patch', 'osfmk/psci_smp.o': 'psci_smp.patch'}
TOKEN = 'small_cores=0'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b148 = _load('nat152_build148', HERE.parent / 'nat-148/build.py')
b143 = b148.b145.b143
b141 = b143.b141
chk = _load('nat152_check_sites', HERE.parent / 'nat-150/check_loader_sites.py')


def check_kernel():
    """NAT-143's five patched objects with the same patches, plus exactly the two objects above."""
    a = json.loads((b143.KERNEL_DIR / 'rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch']), 'main object'
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert {k: v for k, v in new.items() if k in old} == old, 'NAT-143 objects and patches'
    added = {k: Path(v).name for k, v in new.items() if k not in old}
    assert added == PATCHES, added
    for e in r['extra_objects']:
        if e['object'] in PATCHES:
            assert e['patch_sha256'] == hashlib.sha256((HERE / PATCHES[e['object']]).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'].get('psci: cpu %d early marks: last 0x%llx') == 1 and r['undefined_symbols'] == 0
    return r


class _Json123:
    """nat-123/build.py requires the kernel's extra objects to be exactly its four; for that one check it is shown this kernel's record
    without the NAT-152 objects (check_kernel() has verified them). Everything else is the json module."""

    def __init__(self, sha):
        self.sha = sha

    def __getattr__(self, name):
        return getattr(json, name)

    def loads(self, s, *a, **kw):
        r = json.loads(s, *a, **kw)
        if isinstance(r, dict) and r.get('schema') == 'krn044-rebuild-v1' and r.get('no_storage_sha256') == self.sha:
            r = dict(r, extra_objects=[e for e in r['extra_objects'] if e['object'] not in PATCHES])
        return r


def main():
    assert len(NAME) == len(b148.NAME) and len(TAG) == len(b148.TAG)
    rec = check_kernel()
    b123 = b141.b123
    saved = (b148.NAME, b148.TAG, b143.KERNEL_DIR, b123.json, b141.TOKENS)
    b148.NAME, b148.TAG, b143.KERNEL_DIR, b123.json = NAME, TAG, KERNEL_DIR, _Json123(rec['no_storage_sha256'])
    b141.TOKENS = tuple(b141.TOKENS) + (TOKEN,)
    args = list(sys.argv)
    try:
        b148.main()
    finally:
        sys.argv = args
        b148.NAME, b148.TAG, b143.KERNEL_DIR, b123.json, b141.TOKENS = saved
    if '--check-only' in args or '--out' not in args:
        return
    out = Path(args[args.index('--out') + 1])
    path = out / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat143_changes']['kernel'] == rec['no_storage_sha256'], 'kernel used'
    cmd = report['payload_fixes'][NAME]['cmdline']
    tokens = cmd.split()
    assert tokens.count(TAG) == 1 and tokens.count(TOKEN) == 1 and 'nat_attempt=NAT148-scF' not in tokens
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    # the gate NAT-151 lacked: the loader's own checks on this payload, and every constant on the same symbol as before
    res, consts = chk.run(out, NAME)
    if res['rc'] != 0:
        raise SystemExit('loader checkpoint check on the built payload: %r' % res)
    now, before = chk.symbolize(KERNEL_DIR, consts), chk.symbolize(b143.KERNEL_DIR, consts)
    if now != before:
        raise SystemExit('loader constants name other code than in the NAT-143 kernel: %r' % {k: (before[k], now[k]) for k in now
                                                                                              if now[k] != before[k]})
    report['nat152_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), token=TOKEN,
                                    cmdline_bytes=len(cmd.encode()),
                                    objects={k: dict(patch='docs/procedures/nat-152/' + v,
                                                     patch_sha256=hashlib.sha256((HERE / v).read_bytes()).hexdigest())
                                             for k, v in PATCHES.items()},
                                    loader_sites_check=res, loader_constants=now,
                                    purpose='NAT-150 early marks + AFFINITY_INFO with the loader\'s kernel addresses in place; 1 s start wait; '
                                            'no slow-core pairing')
    report['nat152_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py',) + tuple(PATCHES.values())}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
