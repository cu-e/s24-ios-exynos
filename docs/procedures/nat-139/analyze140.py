#!/usr/bin/env python3
"""NAT-140 analyser (rule fixed by NAT-139 before the run): every NAT-137 verdict (nat-129/analyze137.py: window, display, power,
touch, keys), plus the NAT-139 lines.

    analyze140.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON --out OUT_JSON

Added fields:
  spi_map     the `e1s-touch: spi9 map clk=gpp9-C mosi=gpp9-O miso=gpp9-I cs=gpp9-S` values; MAP-ok when they are 0/1/2/3,
              MAP-missing when the line is absent (the kernel did not run the NAT-139 code or the line is in a log gap)
  miso        {'cs_high': 0/1, 'cs_low': 0/1} from the same line
  log         L-pmic-kept when an `e1s-pmic:` line is in the text, otherwise L-pmic-lost; the ring size is reported as the
              bytes of the `--- kernel message buffer ---` section
Interpretation, unchanged from NAT-137: T2 means the controller answered its ID, nothing more. A MISO level alone says nothing
about the chip: a selected, powered STM may hold MISO at either level before the first clock.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat139_analyze137', HERE.parent / 'nat-129/analyze137.py')
A137 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A137)

RE_MAP = re.compile(r'e1s-touch: spi9 map clk=gpp9-(\d) mosi=gpp9-(\d) miso=gpp9-(\d) cs=gpp9-(\d); miso cs-high=([01]) cs-low=([01])')
MARK = '--- kernel message buffer ---'


def classify(text, pixels):
    out = A137.classify(text, pixels)
    m = RE_MAP.search(text)
    if m:
        pins = tuple(int(x) for x in m.groups()[:4])
        out['spi_map'] = 'MAP-ok' if pins == (0, 1, 2, 3) else 'MAP-unexpected %s' % (pins,)
        out['miso'] = dict(cs_high=int(m[5]), cs_low=int(m[6]))
    else:
        out['spi_map'] = 'MAP-missing'
        out['miso'] = None
    out['log'] = 'L-pmic-kept' if 'e1s-pmic:' in text else 'L-pmic-lost'
    i = text.find(MARK)
    out['msgbuf_section_bytes'] = len(text) - i if i >= 0 else 0
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kernel-text', required=True, type=Path)
    ap.add_argument('--pixels', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    r = classify(a.kernel_text.read_text(errors='replace'), json.loads(a.pixels.read_text()))
    a.out.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('window', 'display', 'touch', 'power', 'keys', 'spi_map', 'miso', 'log', 'physical_input')}))


if __name__ == '__main__':
    main()
