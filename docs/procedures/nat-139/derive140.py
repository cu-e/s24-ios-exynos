#!/usr/bin/env python3
"""Counted host derivation of the NAT-140 session driver (native run of scB) from NAT-137's (docs/procedures/nat-129/session_nat137.py);
no device access. Changes: the image (scB) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list. The delivery companion stays NAT-130's deliver130.py (the loader engine is NAT-130's)."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-129/session_nat137.py'
SOURCE_SHA = 'c1af9a2823620f945b510f5bbd40416df190366d1ff3f2aff46e7a08ce2dd346'
OUTPUT = HERE / 'session_nat140.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-137 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-139/package-001/package.json').read_text())['images']['loader-diag-xnu-scB-md1']
    old = json.loads((ROOT / 'artifacts/nat-129/package-001/package.json').read_text())['images']['loader-diag-xnu-scA-md1']
    rules = [
        ('NAT-137 session driver for the NAT-129 image', 'NAT-140 session driver for the NAT-139 image', 1),
        ('loader-diag-xnu-scA-md1: the NAT-128 polling-only touch ID kernel with e1spmic=2',
         'loader-diag-xnu-scB-md1: scA with the NAT-139 touch kernel (USI SPI9 pad order CLK gpp9-0 / MISO gpp9-2, read-only MISO level check) and msgbuf=1048576; scA was the NAT-128 polling-only touch ID kernel with e1spmic=2', 1),
        ("'loader-diag-xnu-scA-md1':dict(", "'loader-diag-xnu-scB-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-129/package-001'", "PACKAGE=ROOT/'artifacts/nat-139/package-001'", 1),
        ('*-nat137-%s-single-run-*.md', '*-nat140-%s-single-run-*.md', 1),
        ('artifacts/nat-137/native-attempt-%s-used.json', 'artifacts/nat-140/native-attempt-%s-used.json', 1),
        ("'NAT-129','NAT-130','NAT-132')", "'NAT-129','NAT-130','NAT-132','NAT-139')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-129/package' not in text and 'nat-137/native-attempt' not in text and "'loader-diag-xnu-scA-md1'" not in text
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
