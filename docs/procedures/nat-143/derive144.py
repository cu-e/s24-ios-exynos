#!/usr/bin/env python3
"""Counted host derivation of the NAT-144 session driver (native run of scD) from NAT-142's (docs/procedures/nat-141/session_nat142.py);
no device access. Changes: the image (scD) and its pinned hashes, the package, the decision glob and one-shot marker, the precondition
list, and the watcher/collector bounds 600 -> 720 s: the scD loader holds until its 595 s deadline (scC: 475 s), so Download Mode
appears at about +620 s after the reboot and the watcher must still be running then. The delivery companion stays NAT-130's."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-141/session_nat142.py'
SOURCE_SHA = 'ced8653c205fc7cfefe742d09cd252ccce059808cdd1d9fb5293ad604c9ac84c'
OUTPUT = HERE / 'session_nat144.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-142 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-143/package-001/package.json').read_text())['images']['loader-diag-xnu-scD-md1']
    old = json.loads((ROOT / 'artifacts/nat-141/package-001/package.json').read_text())['images']['loader-diag-xnu-scC-md1']
    rules = [
        ('NAT-142 session driver for the NAT-141 image', 'NAT-144 session driver for the NAT-143 image', 1),
        ('loader-diag-xnu-scC-md1: scB with the NAT-141 touch kernel',
         'loader-diag-xnu-scD-md1: scC with the NAT-143 touch kernel (every press/release logged), loader_return_after=270, '
         'rec_secs=270 and a 595 s loader deadline; scC was scB with the NAT-141 touch kernel', 1),
        ("'loader-diag-xnu-scC-md1':dict(", "'loader-diag-xnu-scD-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-141/package-001'", "PACKAGE=ROOT/'artifacts/nat-143/package-001'", 1),
        ('*-nat142-%s-single-run-*.md', '*-nat144-%s-single-run-*.md', 1),
        ('artifacts/nat-142/native-attempt-%s-used.json', 'artifacts/nat-144/native-attempt-%s-used.json', 1),
        ("'NAT-139','NAT-140','NAT-141')", "'NAT-139','NAT-140','NAT-141','NAT-142','NAT-143')", 1),
        ('WATCH_S=600 ', 'WATCH_S=720 ', 1),
        ('COLLECT_S=600\n', 'COLLECT_S=720\n', 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-141/package' not in text and 'nat-142/native-attempt' not in text and "'loader-diag-xnu-scC-md1'" not in text
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
