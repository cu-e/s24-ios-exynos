#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-192 session driver (native run of scY) from NAT-177's (docs/procedures/nat-176/session_nat177.py);
no device access. Changes: the image (scS -> scY) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-177, NAT-180..NAT-189 and NAT-191 added). Time bounds and the execution body are unchanged.

  python3 -B docs/procedures/nat-191/derive192.py          # writes session_nat192.py, prints its sha256
  python3 -B docs/procedures/nat-191/derive192.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-176/session_nat177.py'
SOURCE_SHA = '93ed6dad53946973d850cc52ccfb2761d2b560285b5d760d195371ba230e96bb'
OUTPUT = HERE / 'session_nat192.py'
OLD, NEW = 'loader-diag-xnu-scS-md1', 'loader-diag-xnu-scY-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-177 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-191/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-176/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-177 session driver for the NAT-176 image (decisions 0019/0044/0061; loader-diag-xnu-scS-md1: scR with',
         'NAT-192 session driver for the NAT-191 image (decisions 0019/0044/0061; loader-diag-xnu-scY-md1: scX with the sampler self time read without the interrupts-off KPI that panicked NAT-190 (NAT-191 kernel); scX was scV with a read-only user-pc sampler for backboardd threads and without the e1s-dpp register snapshot (NAT-189 kernel); scV was scU with a read-only per-process CPU-time sampler (NAT-185 kernel); scU was scS with the framebuffer '
         "driver's nearest-neighbour scaling copying a per-layer run table of consecutive picture columns with memcpy (NAT-183 kernel); scS was scR with", 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-176/package-001'", "PACKAGE=ROOT/'artifacts/nat-191/package-001'", 1),
        ('*-nat177-%s-single-run-*.md', '*-nat192-%s-single-run-*.md', 1),
        ('artifacts/nat-177/native-attempt-%s-used.json', 'artifacts/nat-192/native-attempt-%s-used.json', 1),
        ("'NAT-175','NAT-176')", "'NAT-175','NAT-176','NAT-177','NAT-180','NAT-181','NAT-182','NAT-183','NAT-184','NAT-185','NAT-186','NAT-187','NAT-188','NAT-189','NAT-191')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-176/package' not in text and 'nat-177/native-attempt' not in text and "'%s'" % OLD not in text
    return text


def main():
    text = build()
    if '--check' in sys.argv:
        assert OUTPUT.read_text() == text, 'session drift'
        print('pass: counted session derivation')
    else:
        OUTPUT.write_text(text)
        print(hashlib.sha256(text.encode()).hexdigest())


if __name__ == '__main__':
    main()
