#!/usr/bin/env python3
"""Counted host derivation of the NAT-149 session driver (native run of scF) from NAT-146's (docs/procedures/nat-145/session_nat146.py);
no device access. Changes: the image (scF) and its pinned hashes, the package, the decision glob and one-shot marker, and the
precondition list (NAT-146 is a fail record and stays open, so NAT-148 replaces it there). Time bounds (loader deadline 595 s,
watcher/collector 720 s) are unchanged."""
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SOURCE = HERE.parent / 'nat-145/session_nat146.py'
SOURCE_SHA = '59a8002ffebe3f985450f9072701589589755548d7632f3ec682019d787ebb24'
OUTPUT = HERE / 'session_nat149.py'


def build():
    data = SOURCE.read_bytes()
    assert hashlib.sha256(data).hexdigest() == SOURCE_SHA, 'NAT-146 session driver changed'
    text = data.decode()
    img = json.loads((ROOT / 'artifacts/nat-148/package-001/package.json').read_text())['images']['loader-diag-xnu-scF-md1']
    old = json.loads((ROOT / 'artifacts/nat-145/package-001/package.json').read_text())['images']['loader-diag-xnu-scE-md1']
    rules = [
        ('NAT-146 session driver for the NAT-145 image', 'NAT-149 session driver for the NAT-148 image', 1),
        ('loader-diag-xnu-scE-md1: scD with all ten CPUs (ADT cpu0-cpu9, no cpus=1)',
         'loader-diag-xnu-scF-md1: scE with cpu1-cpu9 state "waiting" (one boot CPU); scE was scD with all ten CPUs (ADT cpu0-cpu9, no cpus=1)', 1),
        ("'loader-diag-xnu-scE-md1':dict(", "'loader-diag-xnu-scF-md1':dict(", 1),
        (old['recovery_sha256'], img['recovery_sha256'], 1),
        (old['payload_sha256'], img['payload_sha256'], 1),
        ('CANARY_LEN=%d,' % old['payload_bytes'], 'CANARY_LEN=%d,' % img['payload_bytes'], 1),
        ("PACKAGE=ROOT/'artifacts/nat-145/package-001'", "PACKAGE=ROOT/'artifacts/nat-148/package-001'", 1),
        ('*-nat146-%s-single-run-*.md', '*-nat149-%s-single-run-*.md', 1),
        ('artifacts/nat-146/native-attempt-%s-used.json', 'artifacts/nat-149/native-attempt-%s-used.json', 1),
        ("'NAT-142','NAT-143','NAT-144','NAT-145')", "'NAT-142','NAT-143','NAT-144','NAT-145','NAT-148')", 1),
    ]
    for o, n, expected in rules:
        assert text.count(o) == expected, (o, text.count(o), expected)
        text = text.replace(o, n)
    assert 'nat-145/package' not in text and 'nat-146/native-attempt' not in text and "'loader-diag-xnu-scE-md1'" not in text
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
