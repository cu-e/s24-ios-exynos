#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-175 session driver (native run of scR) from NAT-173's (docs/procedures/nat-172/session_nat173.py);
no device access. Changes: the image (scQ -> scR) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-173 and NAT-174 added). Time bounds (loader deadline 595 s, watcher/collector 720 s) and the execution body
are unchanged.

  python3 -B docs/procedures/nat-174/derive175.py          # writes session_nat175.py, prints its sha256
  python3 -B docs/procedures/nat-174/derive175.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-172/session_nat173.py'
SOURCE_SHA = '09154b464c567e0963a75eaee52cc59bcb1daa960d49cec94c4f900bd217861c'
OUTPUT = HERE / 'session_nat175.py'
OLD, NEW = 'loader-diag-xnu-scQ-md1', 'loader-diag-xnu-scR-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-173 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-174/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-172/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-173 session driver for the NAT-172 image (decisions 0019/0044/0061; loader-diag-xnu-scQ-md1: scO with',
         'NAT-175 session driver for the NAT-174 image (decisions 0019/0044/0061; loader-diag-xnu-scR-md1: scQ with a synthetic '
         'home-screen swipe thread 215-375 s (finger 9, NAT-174 kernel) and touch_lat=1 in place of cpuload=1000; scQ was scO with', 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-172/package-001'", "PACKAGE=ROOT/'artifacts/nat-174/package-001'", 1),
        ('*-nat173-%s-single-run-*.md', '*-nat175-%s-single-run-*.md', 1),
        ('artifacts/nat-173/native-attempt-%s-used.json', 'artifacts/nat-175/native-attempt-%s-used.json', 1),
        ("'NAT-171','NAT-172')", "'NAT-171','NAT-172','NAT-173','NAT-174')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-172/package' not in text and 'nat-173/native-attempt' not in text and "'%s'" % OLD not in text
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
