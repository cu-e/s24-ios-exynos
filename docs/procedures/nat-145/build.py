#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scE: scD (NAT-143) with all ten e1s CPUs: the ADT gets cpu1..cpu9 (make_adt145.add_cpus, the donor mkadt smp table checked against
the pinned Samsung DT) and the command line loses `cpus=1`, so XNU starts the other cores through PSCI CPU_ON (osfmk/arm64/psci_smp.c,
compiled in for E1S: GENERIC_PSCI_SMP) and stops them with CPU_OFF before its return to the loader (psci_smp_stop_others()).

Kernel, loader, engine, root, md0 and every other token are scD's. Host build only.

  python3 docs/procedures/nat-145/build.py --out artifacts/nat-145/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = 'loader-diag-xnu-scE-md1'
TAG = 'nat_attempt=NAT145-scE'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b143 = _load('nat145_build143', HERE.parent / 'nat-143/build.py')
m145 = _load('nat145_make_adt145', HERE / 'make_adt145.py')
b141 = b143.b141
b119 = b141.b123.b119
b117 = b119.b117
b115 = b143.b115
STATE = {'adt_calls': 0, 'record': None}


def check_cmdline145(cmdline):
    """b115.check_cmdline's rules without `cpus=1`, which this image must not have."""
    tokens = cmdline.split()
    need = [b115.NEW_TAG, 'loader_return_after=%d' % b115.RETURN_AFTER_NEW, 'rd=md1', 'xrd=md0'] + list(b115.REC_TOKENS + b115.NEW_TOKENS)
    for t in need:
        if tokens.count(t) != 1:
            raise SystemExit('cmdline must contain %s exactly once: %r' % (t, cmdline))
    for t in b115.DROP_BASE_TOKENS + ('fb_diff=1',):
        if t in tokens:
            raise SystemExit('cmdline must not contain %s: %r' % (t, cmdline))
    if any(t.startswith('cpus=') or t.startswith('cpumask=') for t in tokens):
        raise SystemExit('cmdline limits the CPUs: %r' % cmdline)
    if len(cmdline.encode()) >= 256:
        raise SystemExit('cmdline exceeds 255 bytes')


def main():
    assert len(NAME) == len(b143.NAME) and len(TAG) == len(b143.TAG)
    orig_derive = b117.m117.derive

    def derive145(pinned_bytes, im4p_bytes, adt=None):
        out, rec = orig_derive(pinned_bytes, im4p_bytes) if adt is None else orig_derive(pinned_bytes, im4p_bytes, adt)
        smp, srec = m145.add_cpus(out)
        STATE['adt_calls'] += 1
        STATE['record'] = srec
        rec = dict(rec, nat145=srec, output_sha256=srec['output_sha256'], output_bytes=srec['output_bytes'])
        return smp, rec

    saved = (b143.NAME, b143.TAG, b117.m117.derive, b115.DROP_BASE_TOKENS, b115.check_cmdline)
    b143.NAME, b143.TAG = NAME, TAG
    b117.m117.derive = derive145
    b115.DROP_BASE_TOKENS = tuple(b115.DROP_BASE_TOKENS) + ('cpus=1',)
    b115.check_cmdline = check_cmdline145
    args = list(sys.argv)
    try:
        b143.main()
    finally:
        sys.argv = args
        b143.NAME, b143.TAG, b117.m117.derive, b115.DROP_BASE_TOKENS, b115.check_cmdline = saved
    if '--check-only' in args or '--out' not in args:
        return
    if STATE['adt_calls'] != 1:
        raise SystemExit('the SMP ADT was made %d times (need exactly 1)' % STATE['adt_calls'])
    path = Path(args[args.index('--out') + 1]) / 'build.json'
    report = json.loads(path.read_text())
    cmd = report['payload_fixes'][NAME]['cmdline']
    tokens = cmd.split()
    assert TAG in tokens and not any(t.startswith('cpus=') for t in tokens), cmd
    assert 'loader_return_after=270' in tokens and 'rec_secs=270' in tokens
    adt = (Path(args[args.index('--out') + 1]) / NAME / 'payload.adt8.bin').read_bytes()
    report['nat145_changes'] = dict(adt=STATE['record'], cmdline_bytes=len(cmd.encode()), dropped_base=['cpus=1'],
                                    payload_adt_sha256=hashlib.sha256(adt).hexdigest(),
                                    purpose='all ten e1s CPUs via PSCI CPU_ON: frame rate of the software path')
    report['nat145_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'make_adt145.py')}
    path.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
