#!/usr/bin/env python3
"""Classify NAT-124 power/readback evidence independently of touch/display.

A reader open or synthetic events never establish working physical input.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nat123_analyze122', HERE.parent / 'nat-121/analyze122.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)


def classify(text, pixels):
    result = A.classify(text, pixels)
    result['physical_input'] = 'not-established'
    result['power'] = 'P0-no-verified-rails'
    result['rail_readbacks'] = []
    for match in re.finditer(r'e1s-pmic: touch (I/O LDO18|AVDD LDO9) enabled \(0x([0-9a-f]+) 0x([0-9a-f]+) -> 0x([0-9a-f]+) -> 0x([0-9a-f]+)\)', text):
        result['rail_readbacks'].append(dict(name=match[1], register=int(match[2], 16),
                                            before=int(match[3], 16), written=int(match[4], 16), after=int(match[5], 16)))
    if any(s in text for s in ('read-back failed', 'read-back mismatch', 'invalid chip ID', 'invalid queue pointer')):
        result['power'] = 'P1-refused-or-unverified'
    else:
        proved = set()
        for rail in result['rail_readbacks']:
            expected = {'I/O LDO18': (0x3d, 0xd8), 'AVDD LDO9': (0x34, 0xf0)}[rail['name']]
            if (rail['register'], rail['written']) == expected and rail['after'] == expected[1]:
                proved.add(rail['name'])
        for name, reg, value in (('I/O LDO18', 0x3d, 0xd8), ('AVDD LDO9', 0x34, 0xf0)):
            if f'e1s-pmic: touch {name} already on (0x{reg:02x}=0x{value:02x})' in text:
                proved.add(name)
        if len(proved) == 2 and 'e1s-pmic: touch rails are on' in text:
            result['power'] = 'P2-both-rails-verified'
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel-text', required=True, type=Path)
    parser.add_argument('--pixels', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    result = classify(args.kernel_text.read_text(errors='replace'), json.loads(args.pixels.read_text()))
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('window', 'display', 'touch', 'power', 'physical_input')}))


if __name__ == '__main__':
    main()
