#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-200 session driver (native run of e2r) from NAT-198's (docs/procedures/nat-197/session_nat200.py);
no device access. Changes: the image (e2p -> e21) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-198 and the image task NAT-199 added). Time bounds and the execution body are unchanged.

  python3 -B docs/procedures/nat-199/derive200.py          # writes session_nat200.py, prints its sha256
  python3 -B docs/procedures/nat-199/derive200.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-197/session_nat198.py'
SOURCE_SHA = '9b88664e0b1234342950577391145cf0bc3b3e60bc6ef48aa749536019d143e0'
OUTPUT = HERE / 'session_nat200.py'
OLD, NEW = 'loader-diag-xnu-e21-md1', 'loader-diag-xnu-e2r-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-198 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-199/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-197/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-198 session driver for the NAT-197 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e21-md1: e2p with',
         'NAT-200 session driver for the NAT-199 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e2r-md1: e21 with the '
         "uncaught-exception reason copied from the loader log into the kernel message buffer 2 s after a user abort (NAT-199 kernel); e21 was e2p with", 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-197/package-001'", "PACKAGE=ROOT/'artifacts/nat-199/package-001'", 1),
        ('*-nat198-%s-single-run-*.md', '*-nat200-%s-single-run-*.md', 1),
        ('artifacts/nat-198/native-attempt-%s-used.json', 'artifacts/nat-200/native-attempt-%s-used.json', 1),
        ("'NAT-195','NAT-196','NAT-197')", "'NAT-195','NAT-196','NAT-197','NAT-198','NAT-199')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-197/package' not in text and 'nat-198/native-attempt' not in text and "'%s'" % OLD not in text
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
