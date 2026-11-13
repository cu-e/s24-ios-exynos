#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scG: scF (NAT-148) with the NAT-150 kernel. Only three objects change against the kernel scF ran in NAT-149 (artifacts/nat-143/kernel-001):
  osfmk/start.o            early marks of a PSCI-started core (start.patch): entry, cpu data found / not found, start_cpu, before
                           and after the MMU switch, by physical address, cleaned to PoC
  osfmk/psci_smp.o         the boot processor clears a core's marks before CPU_ON, reads them after the wait and prints them with
                           PSCI AFFINITY_INFO; the wait per core is 1 s instead of 5 (psci_smp.patch)
  osfmk/machine_routines.o the boot processor is never paired as a slower core's secondary (machine_routines.patch)
Every other byte source is scF's: the loader, root, md0, the ADT (one running cpu, nine waiting), every cmdline token except the
attempt tag. Host build only.

  python3 -B docs/procedures/nat-150/build.py --out artifacts/nat-150/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scG-md1'
TAG = 'nat_attempt=NAT150-scG'
KERNEL_DIR = ROOT / 'artifacts/nat-150/kernel-001'
PATCHES = {'osfmk/start.o': 'start.patch', 'osfmk/psci_smp.o': 'psci_smp.patch', 'osfmk/machine_routines.o': 'machine_routines.patch'}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b148 = _load('nat150_build148', HERE.parent / 'nat-148/build.py')
b143 = b148.b145.b143


def check_kernel():
    """The NAT-150 kernel: NAT-143's five patched objects with the same patches, plus exactly the three objects above."""
    a = json.loads((b143.KERNEL_DIR / 'rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch']), 'main object'
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    added = {k: v for k, v in new.items() if k not in old}
    assert {k: v for k, v in new.items() if k in old} == old, 'NAT-143 objects and patches'
    assert {k: Path(v).name for k, v in added.items()} == PATCHES, added
    for e in r['extra_objects']:
        if e['object'] in PATCHES:
            assert e['patch_sha256'] == hashlib.sha256((HERE / PATCHES[e['object']]).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'].get('psci: cpu %d early marks: last 0x%llx') == 1
    assert r['undefined_symbols'] == 0
    return r


class _Json123:
    """nat-123/build.py requires the kernel's extra objects to be exactly its four. For that one check, it is shown this kernel's
    record without the three NAT-150 objects (which check_kernel() has verified); everything else is the json module."""

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
    b123 = b143.b141.b123
    saved = (b148.NAME, b148.TAG, b143.KERNEL_DIR, b123.json)
    b148.NAME, b148.TAG, b143.KERNEL_DIR, b123.json = NAME, TAG, KERNEL_DIR, _Json123(rec['no_storage_sha256'])
    args = list(sys.argv)
    try:
        b148.main()
    finally:
        sys.argv = args
        b148.NAME, b148.TAG, b143.KERNEL_DIR, b123.json = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat143_changes']['kernel'] == rec['no_storage_sha256'], 'kernel used'
    cmd = report['payload_fixes'][NAME]['cmdline'].split()
    assert cmd.count(TAG) == 1 and 'nat_attempt=NAT148-scF' not in cmd
    report['nat150_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)),
                                    objects={k: dict(patch='docs/procedures/nat-150/' + v,
                                                     patch_sha256=hashlib.sha256((HERE / v).read_bytes()).hexdigest())
                                             for k, v in PATCHES.items()},
                                    purpose='where PSCI-started cores stop (early marks + AFFINITY_INFO); 1 s start wait; '
                                            'no boot-CPU slow pairing')
    report['nat150_sources'] = {'build.py': hashlib.sha256((HERE / 'build.py').read_bytes()).hexdigest()}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
