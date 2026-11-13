#!/usr/bin/env python3
"""Counted host derivation of the NAT-135 session driver from NAT-132's (docs/procedures/nat-132/session_nat132.py); no device access.
Changes: the image (pk1) and its pinned hashes, the package, the decision glob and one-shot marker, the precondition list, and the
delivery companion (NAT-134's deliver134.py: the read-only PEEK probe before the NAT-130 delivery, same arguments)."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-132/session_nat132.py'
SOURCE_SHA = 'bbf71d2b24496ad3f8ede0361714396f661b7c51954c515aef9b6f1c3ae17c64'
OUTPUT = HERE / 'session_nat135.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-132 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-134/package-001/package.json').read_text())['images']['loader-diag-xnu-pk1-md1']
    old = json.loads((ROOT / 'artifacts/nat-130/package-001/package.json').read_text())['images']['loader-diag-xnu-us1-md1']
    rules = [
        ('NAT-132 session driver for the NAT-130 image', 'NAT-135 session driver for the NAT-134 image', 1),
        ('loader-diag-xnu-us1-md1: sc9 with the NAT-130 USB engine (checksum modes, SUM, GET_RXT);',
         'loader-diag-xnu-pk1-md1: us1 with the NAT-134 engine (read-only PEEK table); us1 is sc9 with the NAT-130 USB engine (checksum modes, SUM, GET_RXT);', 1),
        ("'loader-diag-xnu-us1-md1':dict(", "'loader-diag-xnu-pk1-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-130/package-001'", "PACKAGE=ROOT/'artifacts/nat-134/package-001'", 1),
        ('*-nat132-%s-single-run-*.md', '*-nat135-%s-single-run-*.md', 1),
        ('artifacts/nat-132/native-attempt-%s-used.json', 'artifacts/nat-135/native-attempt-%s-used.json', 1),
        ("'NAT-127','NAT-130')", "'NAT-127','NAT-130','NAT-132','NAT-133','NAT-134')", 1),
        ("DELIVER=ROOT/'docs/procedures/nat-130/deliver130.py'", "DELIVER=ROOT/'docs/procedures/nat-134/deliver134.py'", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'loader-diag-xnu-us1' not in text and 'nat-130/package' not in text, 'a us1 reference survived'
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
