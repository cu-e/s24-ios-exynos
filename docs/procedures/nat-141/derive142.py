#!/usr/bin/env python3
"""Counted host derivation of the NAT-142 session driver (native run of scC) from NAT-140's (docs/procedures/nat-139/session_nat140.py);
no device access. Changes: the image (scC) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list. The delivery companion stays NAT-130's deliver130.py (the loader engine is NAT-130's)."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-139/session_nat140.py'
SOURCE_SHA = 'e7814e16e3ab09ef532dd553e8059ee747b80425c86c6fa9bbae6e39bdb25633'
OUTPUT = HERE / 'session_nat142.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-140 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-141/package-001/package.json').read_text())['images']['loader-diag-xnu-scC-md1']
    old = json.loads((ROOT / 'artifacts/nat-139/package-001/package.json').read_text())['images']['loader-diag-xnu-scB-md1']
    rules = [
        ('NAT-140 session driver for the NAT-139 image', 'NAT-142 session driver for the NAT-141 image', 1),
        ('loader-diag-xnu-scB-md1: scA with the NAT-139 touch kernel',
         'loader-diag-xnu-scC-md1: scB with the NAT-141 touch kernel (Samsung screen-on STM start sequence and a polled event thread); scB was scA with the NAT-139 touch kernel', 1),
        ("'loader-diag-xnu-scB-md1':dict(", "'loader-diag-xnu-scC-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-139/package-001'", "PACKAGE=ROOT/'artifacts/nat-141/package-001'", 1),
        ('*-nat140-%s-single-run-*.md', '*-nat142-%s-single-run-*.md', 1),
        ('artifacts/nat-140/native-attempt-%s-used.json', 'artifacts/nat-142/native-attempt-%s-used.json', 1),
        ("'NAT-132','NAT-139')", "'NAT-132','NAT-139','NAT-140','NAT-141')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-139/package' not in text and 'nat-140/native-attempt' not in text and "'loader-diag-xnu-scB-md1'" not in text
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
