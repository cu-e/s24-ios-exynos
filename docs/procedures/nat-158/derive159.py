#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Counted host derivation of the NAT-159 session driver (native run of scJ) from NAT-153's (docs/procedures/nat-152/session_nat153.py);
no device access. Changes: the image (scJ) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-153, NAT-156, NAT-157 and NAT-158 added). Time bounds (loader deadline 595 s, watcher/collector 720 s) and
the execution body are unchanged.

  python3 -B docs/procedures/nat-158/derive159.py          # writes session_nat159.py, prints its sha256
  python3 -B docs/procedures/nat-158/derive159.py --check  # the file equals the derivation
"""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-152/session_nat153.py'
SOURCE_SHA = 'f97f9d4bfd6228048a14648a5821b133362c5f882398fcb801b7218dcdce5e0a'
OUTPUT = HERE / 'session_nat159.py'
OLD, NEW = 'loader-diag-xnu-scH-md1', 'loader-diag-xnu-scJ-md1'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-153 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-158/package-001/package.json').read_text())['images'][NEW]
    old = json.loads((ROOT / 'artifacts/nat-152/package-001/package.json').read_text())['images'][OLD]
    rules = [
        ('NAT-153 session driver for the NAT-152 image (decisions 0019/0044; loader-diag-xnu-scH-md1: scF with',
         'NAT-159 session driver for the NAT-158 image (decisions 0019/0044/0061; loader-diag-xnu-scJ-md1: scH with boot-arg '
         'fb_filter=0 (nearest-neighbour scaling) in place of rec_secs=270 rec_mb=64, and NAT-157\'s loader message fix; scH was '
         'scF with', 1),
        ("'%s':dict(" % OLD, "'%s':dict(" % NEW, 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-152/package-001'", "PACKAGE=ROOT/'artifacts/nat-158/package-001'", 1),
        ('*-nat153-%s-single-run-*.md', '*-nat159-%s-single-run-*.md', 1),
        ('artifacts/nat-153/native-attempt-%s-used.json', 'artifacts/nat-159/native-attempt-%s-used.json', 1),
        ("'NAT-145','NAT-148','NAT-150','NAT-152')", "'NAT-145','NAT-148','NAT-150','NAT-152','NAT-153','NAT-156','NAT-157','NAT-158')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-152/package' not in text and 'nat-153/native-attempt' not in text and "'%s'" % OLD not in text
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
