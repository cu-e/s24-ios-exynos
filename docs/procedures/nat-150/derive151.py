#!/usr/bin/env python3
"""Counted host derivation of the NAT-151 session driver (native run of scG) from NAT-149's (docs/procedures/nat-148/session_nat149.py);
no device access. Changes: the image (scG) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-149 is a fail record and stays open; NAT-150 is added). Time bounds (loader deadline 595 s, watcher/collector
720 s) are unchanged."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-148/session_nat149.py'
SOURCE_SHA = '80c9791789f6c62fe14a9624eb3becd9cc6e85b761343e6d34557c7f7de434cd'
OUTPUT = HERE / 'session_nat151.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-149 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-150/package-001/package.json').read_text())['images']['loader-diag-xnu-scG-md1']
    old = json.loads((ROOT / 'artifacts/nat-148/package-001/package.json').read_text())['images']['loader-diag-xnu-scF-md1']
    rules = [
        ('NAT-149 session driver for the NAT-148 image', 'NAT-151 session driver for the NAT-150 image', 1),
        ('loader-diag-xnu-scF-md1: scE with cpu1-cpu9 state "waiting" (one boot CPU);',
         'loader-diag-xnu-scG-md1: scF with the NAT-150 kernel (early marks of PSCI-started cores, 1 s start wait, no boot-CPU slow '
         'pairing); scF was scE with cpu1-cpu9 state "waiting" (one boot CPU);', 1),
        ("'loader-diag-xnu-scF-md1':dict(", "'loader-diag-xnu-scG-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-148/package-001'", "PACKAGE=ROOT/'artifacts/nat-150/package-001'", 1),
        ('*-nat149-%s-single-run-*.md', '*-nat151-%s-single-run-*.md', 1),
        ('artifacts/nat-149/native-attempt-%s-used.json', 'artifacts/nat-151/native-attempt-%s-used.json', 1),
        ("'NAT-144','NAT-145','NAT-148')", "'NAT-144','NAT-145','NAT-148','NAT-150')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-148/package' not in text and 'nat-149/native-attempt' not in text and "'loader-diag-xnu-scF-md1'" not in text
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
