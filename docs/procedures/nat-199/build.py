#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""e2r: e21 (NAT-197: scV + the secondary EL2->EL1 drop, ten CPUs in NAT-198) with osfmk/user_exception_trace.o rebuilt from
docs/procedures/nat-199/user_exception_trace.patch: 2 s after a user abort, a thread call searches the loader log (kernel memory, read
only) for "Terminating app due to uncaught exception" lines and prints each distinct one, with the first-throw stack line after it,
into the kernel message buffer, which reaches the host whole. Kernel artifacts/nat-199/kernel-001; command line e21's with the tag
changed. Host build only.

  python3 -B docs/procedures/nat-199/build.py --out artifacts/nat-199/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-e2r-md1'
TAG = 'nat_attempt=NAT199-e2r'
KERNEL_DIR = ROOT / 'artifacts/nat-199/kernel-001'
PATCH = 'docs/procedures/nat-197/start.patch'
UET = 'docs/procedures/nat-199/user_exception_trace.patch'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b185 = _load('nat199_build185', HERE.parent / 'nat-185/build.py')


def check_kernel():
    """NAT-185's kernel record with osfmk/start.o's patch replaced by NAT-197's and osfmk/user_exception_trace.o added; NAT-185's
    expect-strings plus the reason-scan line; 0 undefined."""
    a = json.loads((ROOT / 'artifacts/nat-185/kernel-001/rebuild.json').read_text())
    r = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert (r['object'], r['patch']) == (a['object'], a['patch'])
    old = {e['object']: e['patch'] for e in a['extra_objects']}
    new = {e['object']: e['patch'] for e in r['extra_objects']}
    assert set(new) == set(old) | {'osfmk/user_exception_trace.o'}, (old, new)
    assert {k: v for k, v in new.items() if old.get(k) != v} == {'osfmk/start.o': PATCH, 'osfmk/user_exception_trace.o': UET}, new
    for e in r['extra_objects']:
        assert e['patch_sha256'] == hashlib.sha256((ROOT / e['patch']).read_bytes()).hexdigest(), e['object']
    extra = {k: v for k, v in r['expect_strings'].items() if k not in a['expect_strings']}
    assert {k: r['expect_strings'].get(k) for k in a['expect_strings']} == a['expect_strings'], r['expect_strings']
    assert extra == {'userabort: reason scan: %u line(s) in %u bytes of the loader log, %u distinct said': 1}, extra
    assert r['undefined_symbols'] == 0
    return r


b183 = b185.b183


class _Json123(b183._Json123):
    """NAT-183's view for nat-123/build.py's four-object check, also without osfmk/user_exception_trace.o (check_kernel() verified it)."""

    def loads(self, s, *a, **kw):
        r = super().loads(s, *a, **kw)
        if isinstance(r, dict) and r.get('schema') == 'krn044-rebuild-v1' and r.get('no_storage_sha256') == self.sha:
            r = dict(r, extra_objects=[e for e in r['extra_objects'] if e['object'] != 'osfmk/user_exception_trace.o'])
        return r


def main():
    assert len(NAME) == len(b185.NAME) and len(TAG) == len(b185.TAG)
    rec = check_kernel()
    saved = (b185.NAME, b185.TAG, b185.KERNEL_DIR, b185.check_kernel, b183._Json123)
    b185.NAME, b185.TAG, b185.KERNEL_DIR, b185.check_kernel = NAME, TAG, KERNEL_DIR, lambda: rec
    b183._Json123 = _Json123
    args = list(sys.argv)
    try:
        b185.main()
    finally:
        sys.argv = args
        b185.NAME, b185.TAG, b185.KERNEL_DIR, b185.check_kernel, b183._Json123 = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    assert report['nat185_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat185_changes']['note'] = 'NAT-199 build: kernel (start.o, user_exception_trace.o) and tag replaced (see nat199_changes)'
    report['nat199_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), start_patch=PATCH, uet_patch=UET, tag=TAG,
                                    purpose='e21 plus the uncaught-exception reason copied from the loader log into the message buffer after a user abort')
    report['nat199_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'user_exception_trace.patch', 'rebuild-args.json')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
