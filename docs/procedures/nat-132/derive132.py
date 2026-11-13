#!/usr/bin/env python3
"""Counted host derivation of the NAT-132 session driver from NAT-127's (docs/procedures/nat-126/session_nat126.py); no device access.
Changes: the image (us1) and its pinned hashes, the package, the decision glob and one-shot marker, the precondition list, and the
delivery companion (NAT-130's deliver130.py with one 8 MiB bulk write per chunk and the auto checksum policy)."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-126/session_nat126.py'
SOURCE_SHA = 'deab873a984674f6005db8d5a2bb3c8eb920ebeb7b137e9ebe523fce7a099281'
OUTPUT = HERE / 'session_nat132.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-127 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-130/package-001/package.json').read_text())['images']['loader-diag-xnu-us1-md1']
    old = json.loads((ROOT / 'artifacts/nat-126/package-001/package.json').read_text())['images']['loader-diag-xnu-sc9-md1']
    rules = [
        ('NAT-127 session driver for the NAT-126 image', 'NAT-132 session driver for the NAT-130 image', 1),
        ("loader-diag-xnu-sc9-md1: NAT-119's image with the PMIC init disabled",
         "loader-diag-xnu-us1-md1: sc9 with the NAT-130 USB engine (checksum modes, SUM, GET_RXT); sc9 is NAT-119's image with the PMIC init disabled", 1),
        ('loader-diag-xnu-sc9-md1', 'loader-diag-xnu-us1-md1', 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-126/package-001'", "PACKAGE=ROOT/'artifacts/nat-130/package-001'", 1),
        ('*-nat127-%s-single-run-*.md', '*-nat132-%s-single-run-*.md', 1),
        ('artifacts/nat-127/native-attempt-%s-used.json', 'artifacts/nat-132/native-attempt-%s-used.json', 1),
        ("'NAT-125','NAT-126')", "'NAT-125','NAT-126','NAT-127','NAT-130')", 1),
        ("DELIVER=ROOT/'docs/procedures/nat-080/deliver_nat080.py'", "DELIVER=ROOT/'docs/procedures/nat-130/deliver130.py'", 1),
        ("'--wait-s',str(DELIVER_WAIT_S),'--deliver-s',str(DELIVER_S)]",
         "'--wait-s',str(DELIVER_WAIT_S),'--deliver-s',str(DELIVER_S),'--chunk','8388608','--write-size','8388608','--policy','auto','--none-chunks','4']", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
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
