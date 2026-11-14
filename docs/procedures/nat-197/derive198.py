#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-198 session driver (native run of e21) from NAT-196's (docs/procedures/nat-195/session_nat196.py);
no device access. Changes: the image (e2p -> e21) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-196 and the image task NAT-197 added). Time bounds and the execution body are unchanged.

  python3 -B docs/procedures/nat-197/derive198.py          # writes session_nat198.py, prints its sha256
  python3 -B docs/procedures/nat-197/derive198.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-195/session_nat196.py'
SOURCE_SHA = '3655d16814dd10e398e6f12f18041207b5a25607825478c161208ddcda556fce'
OUTPUT = HERE / 'session_nat198.py'
OLD, NEW = 'loader-diag-xnu-e2p-md1', 'loader-diag-xnu-e21-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-196 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-197/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-195/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-196 session driver for the NAT-195 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e2p-md1: scV with',
         'NAT-198 session driver for the NAT-197 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e21-md1: e2p with the secondary '
         "EL2->EL1 drop at reset_vector using the boot loader's own from_el2 values (NAT-197 kernel); e2p was scV with", 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-195/package-001'", "PACKAGE=ROOT/'artifacts/nat-197/package-001'", 1),
        ('*-nat196-%s-single-run-*.md', '*-nat198-%s-single-run-*.md', 1),
        ('artifacts/nat-196/native-attempt-%s-used.json', 'artifacts/nat-198/native-attempt-%s-used.json', 1),
        ("'GPU-019','NAT-195')", "'GPU-019','NAT-195','NAT-196','NAT-197')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-195/package' not in text and 'nat-196/native-attempt' not in text and "'%s'" % OLD not in text
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
