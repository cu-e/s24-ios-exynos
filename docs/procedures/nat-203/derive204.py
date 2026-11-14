#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-204 session driver (native run of e2m) from NAT-202's (docs/procedures/nat-201/session_nat202.py);
no device access. Changes: the image (e2s -> e2m) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-202 and the image task NAT-203 added). Time bounds, the delivered big root and the execution body are unchanged.

  python3 -B docs/procedures/nat-203/derive204.py          # writes session_nat204.py, prints its sha256
  python3 -B docs/procedures/nat-203/derive204.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-201/session_nat202.py'
SOURCE_SHA = '4e565de9256aba8bd51e9b2a543f3e2b40d2f2b97ee2fd8a12a18686aa8e673b'
OUTPUT = HERE / 'session_nat204.py'
OLD, NEW = 'loader-diag-xnu-e2s-md1', 'loader-diag-xnu-e2m-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-202 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-203/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-201/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-202 session driver for the NAT-201 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e2s-md1: e2r with',
         'NAT-204 session driver for the NAT-203 image (decisions 0019/0044/0061/0079; loader-diag-xnu-e2m-md1: e2s with the md0 root '
         "pid1-sc2-hbm, the donor's libhakios.media.dylib inserted into mediaserverd (NAT-203); e2s was e2r with", 1),
        ('e2s was e2r with boot-arg systrace=1 in place of touch_lat=1, the user-exception trace on (NAT-199 kernel unchanged)',
         'e2s was e2r with the user-exception trace on by default (NAT-201 kernel: user_exception_trace_enabled 1, no boot-arg; '
         'session_nat202.py said "boot-arg systrace=1" in error)', 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-201/package-001'", "PACKAGE=ROOT/'artifacts/nat-203/package-001'", 1),
        ('*-nat202-%s-single-run-*.md', '*-nat204-%s-single-run-*.md', 1),
        ('artifacts/nat-202/native-attempt-%s-used.json', 'artifacts/nat-204/native-attempt-%s-used.json', 1),
        ("'NAT-199','NAT-200','NAT-201')", "'NAT-199','NAT-200','NAT-201','NAT-202','NAT-203')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-201/package' not in text and 'nat-202/native-attempt' not in text and "'%s'" % OLD not in text
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
