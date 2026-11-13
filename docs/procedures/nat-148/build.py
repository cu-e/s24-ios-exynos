#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""scF: scE (NAT-145) with cpu1..cpu9 `state` = "waiting" (make_adt148.add_cpus), so XNU's ml_parse_cpu_topology() sees one boot
CPU. NAT-146 showed scE stopping there. Every other byte source is scE's: kernel, loader, root, md0, tokens except the attempt tag.
Host build only.

  python3 -B docs/procedures/nat-148/build.py --out artifacts/nat-148/build-NNN --loader-source artifacts/nat-020/build-003/source \
          --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = 'loader-diag-xnu-scF-md1'
TAG = 'nat_attempt=NAT148-scF'


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b145 = _load('nat148_build145', HERE.parent / 'nat-145/build.py')
m148 = _load('nat148_make_adt148', HERE / 'make_adt148.py')
CALLS = []
BLOBS = []


def cpu_states(padt):
    """`state` of each /cpus child in the payload's (padded) ADT."""
    adt = b145.m145._adt()
    root, _ = adt.parse(padt)
    cpus = [c for c in root.children if c.name == 'cpus'][0]
    return [c.prop('state').rstrip(b'\0').decode() for c in cpus.children]


def main():
    assert len(NAME) == len(b145.NAME) and len(TAG) == len(b145.TAG)
    orig = b145.m145.add_cpus

    def add_cpus148(blob, adt=None):
        out, rec = orig(blob, adt)
        out, changed = m148.fix_states(out)
        CALLS.append(changed)
        BLOBS.append(out)
        return out, dict(rec, nat148_waiting=changed, output_sha256=hashlib.sha256(out).hexdigest(), output_bytes=len(out))

    saved = (b145.NAME, b145.TAG, b145.m145.add_cpus)
    b145.NAME, b145.TAG, b145.m145.add_cpus = NAME, TAG, add_cpus148
    args = list(sys.argv)
    try:
        b145.main()
    finally:
        sys.argv = args
        b145.NAME, b145.TAG, b145.m145.add_cpus = saved
    if '--check-only' in args or '--out' not in args:
        return
    if CALLS != [['cpu%d' % i for i in range(1, 10)]]:
        raise SystemExit('state fix applied %r (need cpu1..cpu9 once)' % CALLS)
    out = Path(args[args.index('--out') + 1])
    report = json.loads((out / 'build.json').read_text())
    adt = (out / NAME / 'payload.adt8.bin').read_bytes()
    blob = BLOBS[0]
    assert blob.count(b'running\0') == 1 and blob.count(b'waiting\0') == 9, 'ADT states'
    pay = _load('nat148_analyze_payload', HERE.parent / 'nat-029/analyze_payload.py').Payload(str(out / NAME / 'payload.adt8.bin'))
    padt = pay.b[pay.adt_off:pay.adt_off + pay.adt_size]
    states = cpu_states(padt)
    if states != ['running'] + ['waiting'] * 9:
        raise SystemExit('payload ADT /cpus states %r' % states)
    report['nat148_changes'] = dict(waiting=CALLS[0], payload_cpu_states=states, adt_sha256=hashlib.sha256(blob).hexdigest(), adt_bytes=len(blob), payload_adt_sha256=hashlib.sha256(adt).hexdigest(),
                                    purpose='one boot CPU in /cpus (NAT-146 stopped at the second-boot-CPU assertion)')
    report['nat148_sources'] = {n: hashlib.sha256((HERE / n).read_bytes()).hexdigest() for n in ('build.py', 'make_adt148.py')}
    (out / 'build.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
