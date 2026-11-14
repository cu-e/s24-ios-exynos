#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-202 session driver (native run of e2s) from NAT-200's (docs/procedures/nat-199/session_nat200.py);
no device access. Changes: the image (e2r -> e2s) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-200 and the image task NAT-201 added). Time bounds and the execution body are unchanged.

  python3 -B docs/procedures/nat-201/derive202.py          # writes session_nat202.py, prints its sha256
  python3 -B docs/procedures/nat-201/derive202.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-199/session_nat200.py'
SOURCE_SHA = 'eccf26acda1e7a885d713d5309009021817cc1ef7e464fe2f6ce1470dedd306b'
OUTPUT = HERE / 'session_nat202.py'
OLD, NEW = 'loader-diag-xnu-e2r-md1', 'loader-diag-xnu-e2s-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-200 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-201/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-199/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-200 session driver for the NAT-199 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e2r-md1: e21 with',
         'NAT-202 session driver for the NAT-201 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e2s-md1: e2r with boot-arg '
         'systrace=1 in place of touch_lat=1, the user-exception trace on (NAT-199 kernel unchanged); e2r was e21 with', 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-199/package-001'", "PACKAGE=ROOT/'artifacts/nat-201/package-001'", 1),
        ('*-nat200-%s-single-run-*.md', '*-nat202-%s-single-run-*.md', 1),
        ('artifacts/nat-200/native-attempt-%s-used.json', 'artifacts/nat-202/native-attempt-%s-used.json', 1),
        ("'NAT-197','NAT-198','NAT-199')", "'NAT-197','NAT-198','NAT-199','NAT-200','NAT-201')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-199/package' not in text and 'nat-200/native-attempt' not in text and "'%s'" % OLD not in text
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
