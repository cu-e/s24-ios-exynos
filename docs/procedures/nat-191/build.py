#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scY: scX (NAT-189; NAT-190 panicked at its first sampler tick on recount_current_thread_time_mach's interrupts-off assertion) with the
self time read by recount_thread_time_mach(current_thread()). Like scX, it is scV (NAT-185, ran in NAT-186: backboardd 76 % of the only core) with a read-only user-pc sampler for backboardd's threads in
bsd/e1s_display.o (e1s_display.patch = NAT-185's patch without NAT-176's e1s-dpp snapshot, plus the sampler: every 1 ms from 200 to 375 s, the saved user pc/lr of each
backboardd thread that ran since the last tick, in four windows, printed as shared-cache offsets). The kernel
(artifacts/nat-191/kernel-001) is NAT-185's with that object rebuilt; the md0 root (NAT-110's) and the command line are scV's with the
tag changed. Host build only.

  python3 -B docs/procedures/nat-191/build.py --out artifacts/nat-191/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scY-md1'
TAG = 'nat_attempt=NAT191-scY'
KERNEL_DIR = ROOT / 'artifacts/nat-191/kernel-001'
PATCH = 'docs/procedures/nat-191/e1s_display.patch'
DPP_STRING = 'e1s-dpp: %s pmu dpub %#x dpuf0 %#x dpuf1 %#x'
PC_STRING = 'e1s-pc: %u window %u-%u s ticks %u busy %u samples %u tlost %u self %llu us pid %d start %#llx'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b185 = _load('nat191_build185', HERE.parent / 'nat-185/build.py')


def check_kernel():
    """NAT-185's kernel record with only bsd/e1s_display.o's patch replaced by PATCH, and one expect-string more."""
    a = json.loads((ROOT / 'artifacts/nat-185/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(old) == set(new), (old, new)
    assert {k: v for k, v in new.items() if v != old[k]} == {'bsd/e1s_display.o': PATCH}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    want = dict(a['expect_strings'], **{PC_STRING: 1})
    del want[DPP_STRING]                      # NAT-176's snapshot is left out of this object (no room, see the patch)
    assert r['expect_strings'] == want, r['expect_strings']
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
    report['nat185_changes']['note'] = 'NAT-191 build: kernel and tag replaced (see nat191_changes); e1s-top kept'
    report['nat191_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_display_patch=PATCH,
                                    tag=TAG, purpose='read-only user-pc sampler for backboardd threads (e1s-pc) beside e1s-top; self time without the interrupts-off KPI (NAT-190)')
    report['nat191_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in (
        'build.py', 'e1s_display.patch', 'rebuild-args.json', 'host/shim191.h', 'host/fake191.c', 'test_nat191.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
