#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scR: scQ (NAT-172, ran in NAT-173: cpu0 at 1958 MHz) with a synthetic swipe thread in bsd/e1s_touch.o (patch = NAT-169's plus
e1s_swipe_thread: finger 9, home-screen page swipes from 215 s to 375 s uptime every 3 s) and the command line's cpuload=1000
replaced by touch_lat=1, so swaps (tl: s), frames (tl: v) and every posted sample (tl: p) carry kernel timestamps. The kernel
(artifacts/nat-174/kernel-001) is NAT-172's with only that object changed. Host build only.

  python3 -B docs/procedures/nat-174/build.py --out artifacts/nat-174/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scR-md1'
TAG = 'nat_attempt=NAT174-scR'
NEW = ('fb_filter=0', 'touch_lat=1')
KERNEL_DIR = ROOT / 'artifacts/nat-174/kernel-001'
PATCH = 'docs/procedures/nat-174/e1s_touch_combined.patch'
OLD_PATCH = 'docs/procedures/nat-169/e1s_touch_combined.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b172 = _load('nat174_build172', HERE.parent / 'nat-172/build.py')
b169 = b172.b169
b165 = b172.b165


def patch_delta():
    """Against NAT-169's touch patch: only file-scope lines (the swipe constants and switch), two new functions and the thread
    start at the end of e1s_touch_init()."""
    b169.PATCH, b169.OLD_PATCH = PATCH, OLD_PATCH
    try:
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
    finally:
        pass

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
    assert changed == ['None', 'e1s_swipe_thread', 'e1s_touch_ev_thread', 'e1s_touch_init', 'e1s_uptime_us'], changed
    # The splitter files a function's return-type line under the function before it: e1s_touch_ev_thread only gains the
    # return-type line that follows it: 'void' (of e1s_touch_init) before, 'static uint64_t' (of e1s_uptime_us) now; body unchanged.
    ev_a, ev_b = a['e1s_touch_ev_thread'], b['e1s_touch_ev_thread']
    assert ev_a[:-1] == ev_b[:-1] and (ev_a[-1], ev_b[-1]) == ('void', 'static uint64_t'), (ev_a[-1:], ev_b[-1:])
    assert b['e1s_swipe_thread'][-1] == 'void', b['e1s_swipe_thread'][-1:]
    added = [l for l in b['e1s_touch_init'] if l not in a['e1s_touch_init']]
    removed = [l for l in a['e1s_touch_init'] if l not in b['e1s_touch_init']]
    assert removed == [] and [l.strip() for l in added] == [
        'PE_parse_boot_argn("e1stouch_swipe", &e1s_swipe, sizeof(e1s_swipe));',
        'if (e1s_swipe != 0 && kernel_thread_start(e1s_swipe_thread, NULL, &thread) == KERN_SUCCESS) {',
        'printf("e1s-touch: swipe thread started (from %u s)\\n", E1S_SWIPE_FROM_S);'], added  # its '}' exists already
    return changed


def check_kernel():
    """NAT-172's kernel record with exactly one change: bsd/e1s_touch.o built from PATCH."""
    a = json.loads((ROOT / 'artifacts/nat-172/kernel-001/rebuild.json').read_text())
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
    assert len(NAME) == len(b172.NAME) and len(TAG) == len(b172.TAG)
    patch_delta()
    rec = check_kernel()
    old_expected = b165.expected_cmdline

    def expected():
        c = old_expected()
        assert c.count(' cpuload=1000 ') == 1
        return c.replace(' cpuload=1000 ', ' touch_lat=1 ')
    saved = (b165.NAME, b165.TAG, b165.NEW, b165.KERNEL_DIR, b165.check_kernel, b165.expected_cmdline)
    b165.NAME, b165.TAG, b165.NEW, b165.KERNEL_DIR, b165.check_kernel, b165.expected_cmdline = NAME, TAG, NEW, KERNEL_DIR, lambda: rec, expected
    args = list(sys.argv)
    try:
        b165.main()
    finally:
        sys.argv = args
        b165.NAME, b165.TAG, b165.NEW, b165.KERNEL_DIR, b165.check_kernel, b165.expected_cmdline = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat152_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat165_changes']['added'] = 'touch_lat=1 (NAT-174: in place of cpuload=1000)'
    report['nat174_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_touch_patch=PATCH,
                                    tag=TAG, cmdline_token='touch_lat=1 in place of cpuload=1000',
                                    purpose='synthetic home-screen swipes 215-375 s for a frame-capacity measurement')
    report['nat174_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'e1s_touch_combined.patch',
                                                                                                  'host/clock174.c', 'test_nat174.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
