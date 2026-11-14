#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-157: absolute-address relocations in a built loader's objects (NN-*.o of an image directory).

The loader is linked at 0 and runs at S-Boot's address without relocation (NAT-151), so a stored absolute address is wrong at run
time unless it is meant as an offset from the image start. The one such use is the Image header's size field (start.S `.quad
_payload_start` in .text.head, which is 0-based by definition). Any other R_AARCH64_ABS64/ABS32 is a defect; rc 1 lists them.

  python3 -B docs/procedures/nat-157/relocscan.py artifacts/nat-152/build-001/loader-diag-xnu-scH-md1
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ABS = ('R_AARCH64_ABS64', 'R_AARCH64_ABS32', 'R_AARCH64_ABS16')
ALLOWED = {('00-start.S.o', '.rela.text.head', '_payload_start')}


def scan(image_dir):
    found = []
    for o in sorted(Path(image_dir).glob('[0-9][0-9]-*.o')):
        out = subprocess.run(['readelf', '-rW', str(o)], capture_output=True, text=True, check=True).stdout
        section = None
        for line in out.splitlines():
            m = re.match(r"Relocation section '([^']+)'", line)
            if m:
                section = m[1]
                continue
            f = line.split()
            if len(f) >= 5 and f[2] in ABS:
                sym = f[4]
                found.append(dict(object=o.name, section=section, offset=f[0], type=f[2], symbol=sym,
                                  addend=f[6] if len(f) > 6 else None,
                                  allowed=(o.name, section, sym) in ALLOWED))
    return found


def main():
    found = scan(sys.argv[1])
    bad = [r for r in found if not r['allowed']]
    print(json.dumps(dict(total=len(found), bad=bad), indent=1))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
