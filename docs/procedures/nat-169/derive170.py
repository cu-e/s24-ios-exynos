#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-170 session driver (native run of scO) from NAT-159's (docs/procedures/nat-158/session_nat159.py);
no device access. Changes: the image (scJ) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-159, NAT-166, NAT-167, NAT-168 and NAT-169 added). Time bounds (loader deadline 595 s, watcher/collector 720 s) and
the execution body are unchanged.

  python3 -B docs/procedures/nat-169/derive170.py          # writes session_nat168.py, prints its sha256
  python3 -B docs/procedures/nat-169/derive170.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-158/session_nat159.py'
SOURCE_SHA = '0fa7d22ef5d97f66dd08ad8fa85baf7d781c312179b1bd70c64bacb4188de2ae'
OUTPUT = HERE / 'session_nat170.py'
OLD, NEW = 'loader-diag-xnu-scJ-md1', 'loader-diag-xnu-scO-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-159 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-169/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-158/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-159 session driver for the NAT-158 image (decisions 0019/0044/0061; loader-diag-xnu-scJ-md1: scH with',
         'NAT-170 session driver for the NAT-169 image (decisions 0019/0044/0061; loader-diag-xnu-scO-md1: scN with the touch GPP9 '
         'DAT shadowed and the poll gated on gpa1-2 (NAT-169 kernel); scN was scM with the touch SPI half-bit 8; scM was scJ with '
         'cpuload=1000 and the NAT-165 kernel; scJ was scH with', 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-158/package-001'", "PACKAGE=ROOT/'artifacts/nat-169/package-001'", 1),
        ('*-nat159-%s-single-run-*.md', '*-nat170-%s-single-run-*.md', 1),
        ('artifacts/nat-159/native-attempt-%s-used.json', 'artifacts/nat-170/native-attempt-%s-used.json', 1),
        ("'NAT-157','NAT-158')", "'NAT-157','NAT-158','NAT-159','NAT-166','NAT-167','NAT-168','NAT-169')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-158/package' not in text and 'nat-159/native-attempt' not in text and "'%s'" % OLD not in text
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
