#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""e2s: e2r (NAT-199, ran in NAT-200: ten CPUs, SpringBoard's routingContextUID abort) with the user-exception trace on. The kernel is
NAT-199's with osfmk/user_exception_trace.o rebuilt from docs/procedures/nat-201/user_exception_trace.patch, which is NAT-199's patch
plus one changed line: the default of user_exception_trace_enabled (boot-arg "systrace") is 1 instead of 0.

Why the default and not the boot-arg: "systrace" is also read by bsd/dev/arm/systemcalls.c (level 1 logs every failing system call
of every process, "megabytes a minute") and bsd/kern/kern_exec.c, and the kernel's BOOT_LINE_LENGTH (256) leaves no room for
systrace_name=. With the default changed, only the exception trace runs: for every EXC_BAD_ACCESS / EXC_BAD_INSTRUCTION /
EXC_ARITHMETIC / EXC_BREAKPOINT of a user thread, exception_triage_thread() prints a `usertrap:` line (process, pid, codes, pc, lr,
sp, shared cache slide), any printable text x0-x3/x8/x16 point at, and up to ten frame-pointer return addresses, before the exception
is delivered. The target is mediaserverd's SIGSEGV loop (every run since NAT-118), the candidate source of SpringBoard's missing
route context. The command line is e2r's with the tag changed. Host build only.

  python3 -B docs/procedures/nat-201/build.py --out artifacts/nat-201/build-NNN --loader-source artifacts/nat-020/build-003/source \\
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-e2s-md1'
TAG = 'nat_attempt=NAT201-e2s'
KERNEL_DIR = ROOT / 'artifacts/nat-201/kernel-001'
UET = 'docs/procedures/nat-201/user_exception_trace.patch'
OLD_LINE = '-static TUNABLE(uint32_t, user_exception_trace_enabled, "systrace", 0);'
NEW_LINE = ('+static TUNABLE(uint32_t, user_exception_trace_enabled, "systrace", 1);\t'
            '/* NAT-201: on without the boot-arg, so failed system calls stay unlogged */')


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b199 = _load('nat201_build199', HERE.parent / 'nat-199/build.py')


def patch_delta():
    """NAT-201's patch is NAT-199's plus exactly one hunk that swaps the tunable's default."""
    a = (ROOT / b199.UET).read_text().splitlines()
    b = (ROOT / UET).read_text().splitlines()
    extra = [l for l in b if l not in a]
    assert all(l in b for l in a), 'NAT-199 lines missing'
    assert [l for l in extra if l[:1] in '+-'] == [OLD_LINE, NEW_LINE], extra
    return extra


def main():
    assert len(NAME) == len(b199.NAME) and len(TAG) == len(b199.TAG)
    patch_delta()
    saved = (b199.NAME, b199.TAG, b199.KERNEL_DIR, b199.UET)
    b199.NAME, b199.TAG, b199.KERNEL_DIR, b199.UET = NAME, TAG, KERNEL_DIR, UET
    args = list(sys.argv)
    try:
        b199.main()
    finally:
        sys.argv = args
        b199.NAME, b199.TAG, b199.KERNEL_DIR, b199.UET = saved
    if '--check-only' in args or '--out' not in args:
        return
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    rec = json.loads((KERNEL_DIR / 'rebuild.json').read_text())
    assert report['nat199_changes']['kernel'] == rec['no_storage_sha256']
    assert report['nat152_changes']['loader_sites_check'] == dict(rc=0, verdict='ok', bad=0)
    report['nat199_changes']['note'] = 'NAT-201 build: kernel (user_exception_trace.o default) and tag replaced (see nat201_changes)'
    report['nat201_changes'] = dict(kernel=rec['no_storage_sha256'], kernel_dir=str(KERNEL_DIR.relative_to(ROOT)), uet_patch=UET, tag=TAG,
                                    changed='user_exception_trace_enabled default 0 -> 1 (boot-arg systrace not set)',
                                    purpose="e2r with the user-exception trace on: mediaserverd's SIGSEGV pc/lr/registers/frames")
    report['nat201_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'user_exception_trace.patch', 'rebuild-args.json')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
