#!/usr/bin/env python3
"""Host-only counted derivation of NAT-124's session from NAT-122's driver."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-121/session_nat121.py'
SOURCE_SHA = 'cd2ed56285cc8d87c93cb343ce941be51a8e5345f6fc7050e70de88cf11fc792'
OUTPUT = HERE / 'session_nat123.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'session source drift'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-123/package-002/package.json').read_text())['images']['loader-diag-xnu-sc8-md1']
    rules = [
        ('NAT-122 session driver for the NAT-121 image', 'NAT-124 session driver for the NAT-123 image', 1),
        ('loader-diag-xnu-sc7-md1', 'loader-diag-xnu-sc8-md1', 2),
        ('f62c3c9ec38d0557492235cc00520c3e035f3b10ad883e9b7652dda376c2301b', img['recovery_sha256'], 1),
        ('ec1e8c728eb68dcc02d01f3069010ff927b4812343a18ce6d8caacb8ee618475', img['payload_sha256'], 1),
        ('CANARY_LEN=26142032,', 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-121/package-001'", "PACKAGE=ROOT/'artifacts/nat-123/package-002'", 1),
        ('*-nat122-%s-single-run-*.md', '*-nat124-%s-single-run-*.md', 1),
        ('artifacts/nat-122/native-attempt-%s-used.json', 'artifacts/nat-124/native-attempt-%s-used.json', 1),
        ("'NAT-120','NAT-121')", "'NAT-120','NAT-121','NAT-122','NAT-123')", 1),
        ('fixed e1s touch driver at e1stouch_steps=2 and /dev/hakios-touch',
         'fixed ACPM layout, PM1 block, restricted LDO9/LDO18 writes with readback (decision 0049), touch step 3 default and /dev/hakios-touch', 1),
    ]
    for old, new, count in rules:
        assert text.count(old) == count, ('derivation count', old, text.count(old), count)
        text = text.replace(old, new)
    return text


def main():
    text = build()
    if '--check' in sys.argv:
        assert OUTPUT.read_text() == text, 'derived session drift'
        print('pass: session_nat123.py matches counted derivation')
    else:
        OUTPUT.write_text(text)
        print(hashlib.sha256(text.encode()).hexdigest())


if __name__ == '__main__':
    main()
