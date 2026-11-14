#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scQ: scO (NAT-169, ran in NAT-170) with a cpu0 clock probe and one stock DVFS request in bsd/e1s_acpm.o (patch = NAT-123's
plus NAT-172's changes): the transport takes a channel, the probe also validates APM channel 0 (DVFS, must be AP-polled), and after
"PMIC channel ready" e1s_cpuclk_raise() logs PLL_CPUCL0 CON3 and a timed dependent-add rate, sends FREQ_REQ {2, 1959000, 0, 0} on
channel 0 only if the PLL decode is valid and more than 1% below the target, and logs the reply and both readbacks again. The
kernel (artifacts/nat-172/kernel-001) is NAT-169's with only that object changed. Command line: scO's with the tag changed.
Host build only.

  python3 -B docs/procedures/nat-172/build.py --out artifacts/nat-172/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scQ-md1'
TAG = 'nat_attempt=NAT172-scQ'
KERNEL_DIR = ROOT / 'artifacts/nat-172/kernel-001'
PATCH = 'docs/procedures/nat-172/e1s_acpm.patch'
OLD_PATCH = 'docs/procedures/nat-123/e1s_acpm.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b169 = _load('nat172_build169', HERE.parent / 'nat-169/build.py')
b165 = b169.b165


def patch_delta():
    """On the patched sources, only the transport, the probe and the new clock functions differ from NAT-123's e1s_acpm.c."""
    import re
    import subprocess
    import tempfile
    orig = ROOT / 'worktrees/str-014-e1s-native-source-ports-20261106/artifacts/e1s-native-source-ports/derive-001/xnu/bsd/dev/e1s_acpm.c'
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
    want = ['None', 'e1s_acpm_clear_irq', 'e1s_acpm_probe', 'e1s_acpm_send', 'e1s_acpm_send_ch',
            'e1s_acpm_send_locked', 'e1s_acpm_take_response', 'e1s_acpm_wait_irq', 'e1s_add_rate', 'e1s_cpuclk_raise', 'e1s_pll_khz']
    assert changed == want, changed
    # MFD functions (the PMIC writes and their whitelist) are untouched
    for k in a:
        if k and k.startswith('e1s_acpm_mfd'):
            assert a[k] == b[k], k
    return changed


def check_kernel():
    """NAT-169's kernel record with exactly one change: bsd/e1s_acpm.o built from PATCH."""
    a = json.loads((ROOT / 'artifacts/nat-169/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(old) == set(new)
    assert {k: v for k, v in new.items() if v != old[k]} == {'bsd/e1s_acpm.o': PATCH}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    assert r['expect_strings'] == a['expect_strings'] and r['undefined_symbols'] == 0
    return r


def main():
    assert len(NAME) == len(b169.NAME) and len(TAG) == len(b169.TAG)
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
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat172_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), e1s_acpm_patch=PATCH,
                                    tag=TAG, purpose='cpu0 clock probe + one stock FREQ_REQ 1959000 kHz on APM channel 0')
    report['nat172_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'e1s_acpm.patch',
                                                                                                  'host/fakeapm.c', 'test_nat172.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
