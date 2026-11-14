#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scO: scN (NAT-167, ran in NAT-168) with fewer touch GPIO accesses. NAT-168 showed that the half-bit delay is not the poll cost;
the GPIO MMIO is (~8.5 us per access, ~1008 per event read). The kernel (artifacts/nat-169/kernel-001) is NAT-167's with one change,
bsd/e1s_touch.o built from e1s_touch_combined.patch: e1s_spi_transfer() shadows GPP9 DAT per transfer (same written values and order),
and the event thread reads the STM only on a low gpa1-2 or every 25th poll (boot-arg e1stouch_full). Command line: scN's with the tag
changed. Host build only.

  python3 -B docs/procedures/nat-169/build.py --out artifacts/nat-169/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scO-md1'
TAG = 'nat_attempt=NAT169-scO'
KERNEL_DIR = ROOT / 'artifacts/nat-169/kernel-001'
PATCH = 'docs/procedures/nat-169/e1s_touch_combined.patch'
OLD_PATCH = 'docs/procedures/nat-167/e1s_touch_combined.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b167 = _load('nat169_build167', HERE.parent / 'nat-167/build.py')
b165 = b167.b165
b152 = b165.b152


def patch_delta():
    """Against NAT-167's patch the new one changes only e1s_spi_transfer(), the event thread's poll loop and its two log lines, and
    adds e1s_full_every with its boot-arg; checked on the patched sources (the hunks themselves move)."""
    import re
    import subprocess
    import tempfile
    orig = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_touch.c'
    texts = []
    with tempfile.TemporaryDirectory(dir=__import__('os').environ.get('TMPDIR')) as tmp:
        for p in (OLD_PATCH, PATCH):
            t = Path(tmp) / 't.c'
            t.write_text(orig.read_text())
            subprocess.run(['patch', '-s', '--no-backup-if-mismatch', str(t), str(ROOT / p)], check=True)
            texts.append(t.read_text())

    def funcs(text):
        out, name = {}, None
        for line in text.splitlines():
            m = re.match(r'^([a-z_0-9]+)\(', line)
            if m:
                name = m.group(1)
            out.setdefault(name, []).append(line)
        return out
    a, b = funcs(texts[0]), funcs(texts[1])
    changed = sorted(str(k) for k in set(a) | set(b) if a.get(k) != b.get(k))
    assert changed == ['None', 'e1s_spi_transfer', 'e1s_touch_ev_thread', 'e1s_touch_init'], changed     # None: file-scope lines
    top = [l for l in b[None] if l not in a[None]]
    assert [l for l in top if not l.lstrip().startswith(('/*', '*'))] == ['static uint32_t e1s_full_every = 25;'], top
    init = [l for l in b['e1s_touch_init'] if l not in a['e1s_touch_init']]
    assert [l.strip() for l in init] == ['PE_parse_boot_argn("e1stouch_full", &e1s_full_every, sizeof(e1s_full_every));'], init
    return changed


def check_kernel():
    """NAT-167's kernel record with exactly one change: bsd/e1s_touch.o built from PATCH."""
    a = json.loads((ROOT / 'artifacts/nat-167/kernel-001/rebuild.json').read_text())
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
    assert len(NAME) == len(b167.NAME) and len(TAG) == len(b167.TAG)
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
    report['nat169_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_touch_patch=PATCH,
                                    tag=TAG, purpose='touch: GPP9 DAT shadowed per transfer, poll gated on gpa1-2 (full read every 25th)')
    report['nat169_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'e1s_touch_combined.patch',
                                                                                                  'host/peer169.c', 'test_nat169.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
