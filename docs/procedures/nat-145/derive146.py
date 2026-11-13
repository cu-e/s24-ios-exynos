#!/usr/bin/env python3
"""Counted host derivation of the NAT-146 session driver (native run of scE) from NAT-144's (docs/procedures/nat-143/session_nat144.py);
no device access. Changes: the image (scE) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list. Time bounds (loader deadline 595 s, watcher/collector 720 s) are scD's and unchanged."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-143/session_nat144.py'
SOURCE_SHA = '17b86433bb746a8ee61f33c0423dd77b301df5ab5961d23d342c655271f11010'
OUTPUT = HERE / 'session_nat146.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-144 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-145/package-001/package.json').read_text())['images']['loader-diag-xnu-scE-md1']
    old = json.loads((ROOT / 'artifacts/nat-143/package-001/package.json').read_text())['images']['loader-diag-xnu-scD-md1']
    rules = [
        ('NAT-144 session driver for the NAT-143 image', 'NAT-146 session driver for the NAT-145 image', 1),
        ('loader-diag-xnu-scD-md1: scC with the NAT-143 touch kernel',
         'loader-diag-xnu-scE-md1: scD with all ten CPUs (ADT cpu0-cpu9, no cpus=1); scD was scC with the NAT-143 touch kernel', 1),
        ("'loader-diag-xnu-scD-md1':dict(", "'loader-diag-xnu-scE-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-143/package-001'", "PACKAGE=ROOT/'artifacts/nat-145/package-001'", 1),
        ('*-nat144-%s-single-run-*.md', '*-nat146-%s-single-run-*.md', 1),
        ('artifacts/nat-144/native-attempt-%s-used.json', 'artifacts/nat-146/native-attempt-%s-used.json', 1),
        ("'NAT-142','NAT-143')", "'NAT-142','NAT-143','NAT-144','NAT-145')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-143/package' not in text and 'nat-144/native-attempt' not in text and "'loader-diag-xnu-scD-md1'" not in text
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
