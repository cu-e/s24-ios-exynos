#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scM: scJ (NAT-158, ran in NAT-159) with boot-arg cpuload=1000 and a kernel that can honour it. On E1S, redwood_input_init() skips
redwood_cpufreq_init() (references/s24-port 0002-e1s-input.patch: the redwood drivers are under #else), and that function is what
starts the cpuload thread (bsd/dev/redwood_cpufreq.c load_start()). The kernel here (artifacts/nat-165/kernel-001) is NAT-152's seven
objects with the same patches except bsd/redwood_input.o, whose patch is NAT-121's plus that one call in the E1S branch. With no
cpufreq= or ddr= boot-arg, redwood_cpufreq_init() starts the load thread and returns: ddr defaults to 2 and acts only with cpufreq,
and the frequency code returns without cpufreq. The load thread logs "tl: u at US CORE:PCT ..." every second through
loader_log_line, with kernel timestamps. Host build only.

  python3 -B docs/procedures/nat-165/build.py --out artifacts/nat-165/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scM-md1'
TAG = 'nat_attempt=NAT165-scM'
NEW = ('fb_filter=0', 'cpuload=1000')
KERNEL_DIR = ROOT / 'artifacts/nat-165/kernel-001'
PATCH = 'docs/procedures/nat-165/redwood_input.patch'
SCJ_BUILD = ROOT / 'artifacts/nat-158/build-001'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b158 = _load('nat165_build158', HERE.parent / 'nat-158/build.py')
b152 = b158.b152


def check_kernel():
    """NAT-152's kernel record with exactly one change: bsd/redwood_input.o built from PATCH (NAT-121's patch plus one call)."""
    a = json.loads((ROOT / 'artifacts/nat-152/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch']), 'main object'
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(old) == set(new), (sorted(old), sorted(new))
    assert {k: v for k, v in new.items() if v != old[k]} == {'bsd/redwood_input.o': PATCH}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'].get('tl: u at %llu') == 1 and r['expect_strings'].get('psci: cpu %d early marks: last 0x%llx') == 1
    assert r['undefined_symbols'] == 0
    return r


def nat121_hunks_kept():
    """Every line NAT-121's patch adds is added by PATCH too; PATCH adds only the NAT-165 call and its comment on top."""
    plus = lambda t: [l[1:] for l in t.splitlines() if l.startswith('+') and not l.startswith('+++')]
    a, b = plus((ROOT / 'docs/procedures/nat-121/redwood_input.patch').read_text()), plus((ROOT / PATCH).read_text())
    extra = [l for l in b if l not in a]
    assert all(l in b for l in a), 'NAT-121 lines missing'
    assert [l.strip() for l in extra if not l.strip().startswith(('/*', '*'))] == ['redwood_cpufreq_init();'], extra
    return extra


def expected_cmdline():
    old = json.loads((SCJ_BUILD / 'build.json').read_text())['payload_fixes'][b158.NAME]['cmdline']
    assert old.count(' fb_filter=0 ') == 1 and old.count(b158.TAG) == 1
    return old.replace(' fb_filter=0 ', ' fb_filter=0 cpuload=1000 ').replace(b158.TAG, TAG)


def main():
    assert len(NAME) == len(b158.NAME) and len(TAG) == len(b158.TAG) and b158.NEW == ('fb_filter=0',)
    nat121_hunks_kept()
    want = expected_cmdline()
    rec = check_kernel()
    saved = (b158.NAME, b158.TAG, b158.NEW, b152.KERNEL_DIR, b152.check_kernel)
    b158.NAME, b158.TAG, b158.NEW = NAME, TAG, NEW
    b152.KERNEL_DIR, b152.check_kernel = KERNEL_DIR, lambda: rec
    args = list(sys.argv)
    try:
        b158.main()
    finally:
        sys.argv = args
        b158.NAME, b158.TAG, b158.NEW, b152.KERNEL_DIR, b152.check_kernel = saved
    if '--check-only' in args or '--out' not in args:
        return
    out = Path(args[args.index('--out') + 1])
    path = out / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    if cmd != want:
        raise SystemExit('cmdline is not scJ\'s with cpuload=1000:\n %r\n %r' % (cmd, want))
    assert len(cmd.encode()) <= 255, len(cmd.encode())
    assert report['nat152_changes']['kernel'] == rec['no_storage_sha256'], 'kernel used'
    report['nat165_changes'] = dict(cmdline_bytes=len(cmd.encode()), added='cpuload=1000', tag=TAG, kernel=rec['no_storage_sha256'],
                                    kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), redwood_input_patch=PATCH,
                                    purpose='per-core busy share every second with kernel timestamps (tl: u)')
    report['nat165_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'redwood_input.patch')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
