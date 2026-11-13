#!/usr/bin/env python3
"""Counted host derivation of the NAT-153 session driver (native run of scH) from NAT-151's (docs/procedures/nat-150/session_nat151.py);
no device access. Changes: the image (scH) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-151 is a fail record and stays open; NAT-152 is added). Time bounds (loader deadline 595 s, watcher/collector
720 s) are unchanged."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-150/session_nat151.py'
SOURCE_SHA = '7a8b73318297e7084a0e6db323644bc1d7d97a839a8641d7fbd6310c82a51ec4'
OUTPUT = HERE / 'session_nat153.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-151 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-152/package-001/package.json').read_text())['images']['loader-diag-xnu-scH-md1']
    old = json.loads((ROOT / 'artifacts/nat-150/package-001/package.json').read_text())['images']['loader-diag-xnu-scG-md1']
    rules = [
        ('NAT-151 session driver for the NAT-150 image', 'NAT-153 session driver for the NAT-152 image', 1),
        ('loader-diag-xnu-scG-md1: scF with the NAT-150 kernel (early marks of PSCI-started cores, 1 s start wait, no boot-CPU slow '
         'pairing);',
         'loader-diag-xnu-scH-md1: scF with the NAT-152 kernel (NAT-150\'s early marks out of line, every loader-checked kernel address '
         'in place, 1 s start wait) and small_cores=0 (no slow-core pairing);', 1),
        ("'loader-diag-xnu-scG-md1':dict(", "'loader-diag-xnu-scH-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-150/package-001'", "PACKAGE=ROOT/'artifacts/nat-152/package-001'", 1),
        ('*-nat151-%s-single-run-*.md', '*-nat153-%s-single-run-*.md', 1),
        ('artifacts/nat-151/native-attempt-%s-used.json', 'artifacts/nat-153/native-attempt-%s-used.json', 1),
        ("'NAT-145','NAT-148','NAT-150')", "'NAT-145','NAT-148','NAT-150','NAT-152')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-150/package' not in text and 'nat-151/native-attempt' not in text and "'loader-diag-xnu-scG-md1'" not in text
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
