#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""e2p: scV (NAT-185, the native-resolution reference) with osfmk/start.o rebuilt from docs/procedures/nat-197/start.patch, which is
NAT-152's start.patch plus a read-only EL2 probe in the out-of-line mark-4 block: a PSCI-started core that finds CurrentEL == 2 stores
HCR/SCTLR/MDCR/VBAR/CNTHCTL/CNTVOFF/CPTR/ICC_SRE _EL2 into its early-mark slots 3-6, sets the stage word to 0x5EC000E2 and parks in
wfe. No EL2 register is written. Kernel artifacts/nat-197/kernel-001; command line scV's with the tag changed. Host build only.

  python3 -B docs/procedures/nat-197/build.py --out artifacts/nat-197/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-e21-md1'
TAG = 'nat_attempt=NAT197-e21'
KERNEL_DIR = ROOT / 'artifacts/nat-197/kernel-001'
PATCH = 'docs/procedures/nat-197/start.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b185 = _load('nat197_build185', HERE.parent / 'nat-185/build.py')


def check_kernel():
    """NAT-185's kernel record with only osfmk/start.o's patch replaced by PATCH; same expect-strings; 0 undefined."""
    a = json.loads((ROOT / 'artifacts/nat-185/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(old) == set(new), (old, new)
    assert {k: v for k, v in new.items() if v != old[k]} == {'osfmk/start.o': PATCH}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'] == a['expect_strings'], r['expect_strings']
    assert r['undefined_symbols'] == 0
    return r


def main():
    assert len(NAME) == len(b185.NAME) and len(TAG) == len(b185.TAG)
    rec = check_kernel()
    saved = (b185.NAME, b185.TAG, b185.KERNEL_DIR, b185.check_kernel)
    b185.NAME, b185.TAG, b185.KERNEL_DIR, b185.check_kernel = NAME, TAG, KERNEL_DIR, lambda: rec
    args = list(sys.argv)
    try:
        b185.main()
    finally:
        sys.argv = args
        b185.NAME, b185.TAG, b185.KERNEL_DIR, b185.check_kernel = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat185_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat185_changes']['note'] = 'NAT-197 build: kernel (start.o) and tag replaced (see nat197_changes)'
    report['nat197_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), start_patch=PATCH, tag=TAG,
                                    purpose='secondary EL2->EL1 drop with the loader from_el2 values; NAT-195 probe as the fallback')
    report['nat197_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'start.patch', 'rebuild-args.json')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
