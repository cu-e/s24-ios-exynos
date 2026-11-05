#!/usr/bin/env python3
"""Reproduce USBREV-F01 against pinned, already hash-verified donor bytes."""
import hashlib
import json
from pathlib import Path

here = Path(__file__).resolve().parent
source = here / 'local/independent-001/reference-donor-2.stdout.txt'
profile = here / 'local/independent-001/source/profile.json'
lines = source.read_text().splitlines()
stack, facts = [], []
for number, line in enumerate(lines, 1):
    if 'tusb2e11-repeater@3E {' in line or 'ptn3222-repeater@4F {' in line:
        assert not stack, (number, stack)
        assert lines[number].strip().startswith('compatible = ')
        assert lines[number + 1].strip().startswith('reg = ')
        assert lines[number + 2].strip() == 'status = "okay";'
        facts.append(dict(line=number, node=line.strip(), conditional_stack=list(stack),
                          properties=lines[number:number + 3]))
    directive = line.lstrip()
    if directive.startswith(('#if ', '#ifdef ', '#ifndef ')):
        stack.append((number, directive))
    elif directive.startswith('#endif'):
        stack.pop()
assert len(facts) == 2
assert 'ptn3222' not in profile.read_text()
print(json.dumps(dict(finding='USBREV-F01', severity='P2',
                      donor_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      source_declares_both_enabled_nodes=facts,
                      profile_omits='ptn3222-repeater at 7-bit address 0x4f',
                      actual_fitted_hardware='unqualified'), indent=2))
