#!/usr/bin/env python3
"""Counted host derivation of sc9 session; no device access."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-123/session_nat123.py'
SOURCE_SHA = '786f2ca8f4207e7cadaa175bba8f55a569cdcf3f4e387c389dcc6b0e4c49c78a'
OUTPUT = HERE / 'session_nat126.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-126/package-001/package.json').read_text())['images']['loader-diag-xnu-sc9-md1']
    oldimg = json.loads((ROOT / 'artifacts/nat-123/package-002/package.json').read_text())['images']['loader-diag-xnu-sc8-md1']
    rules = [
        ('NAT-124 session driver for the NAT-123 image', 'NAT-127 session driver for the NAT-126 image', 1),
        ('loader-diag-xnu-sc8-md1', 'loader-diag-xnu-sc9-md1', 2),
        (oldimg['recovery_sha256'], img['recovery_sha256'], 1),
        (oldimg['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % oldimg['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-123/package-002'", "PACKAGE=ROOT/'artifacts/nat-126/package-001'", 1),
        ('*-nat124-%s-single-run-*.md', '*-nat127-%s-single-run-*.md', 1),
        ('artifacts/nat-124/native-attempt-%s-used.json', 'artifacts/nat-127/native-attempt-%s-used.json', 1),
        ("'NAT-122','NAT-123')", "'NAT-122','NAT-123','NAT-125','NAT-126')", 1),
        ('fixed ACPM layout, PM1 block, restricted LDO9/LDO18 writes with readback (decision 0049), touch step 3 default and /dev/hakios-touch',
         'PMIC init disabled (e1spmic=0), NAT-125 touch IRQ admission guard and /dev/hakios-touch', 1),
    ]
    for old, new, expected in rules:
        assert text.count(old) == expected, (old, text.count(old), expected)
        text = text.replace(old, new)
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
