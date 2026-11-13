#!/usr/bin/env python3
"""NAT-137 analyser (rule fixed by NAT-129 before the run): window/display/power as nat-123/analyze124.py, touch from the NAT-128
polling diagnostic lines, keys from the e1s-keys line.

    analyze137.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON --out OUT_JSON

Touch, first match:
  T0-fault        a kernel panic mentions e1s_touch
  T0-no-poll      no `e1s-touch: poll N device id` line (driver did not run, or the lines are in a log gap)
  T1-no-response  every poll's device id and hardware id bytes are all 0x00 or all 0xff
  T2-chip-answers at least one poll returned an id that is neither all-0x00 nor all-0xff (bytes reported)
Keys: K0-disabled when `e1s-keys: disabled (e1skeys=0)` is present, else K1-not-disabled (a deviation from the image).
A chip answering its ID is not working input: no IRQ, no event thread, no touch reaches iOS in this image.
"""
import argparse
import importlib.util
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('nat129_analyze124', HERE.parent / 'nat-123/analyze124.py')
A124 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(A124)

RE_DEV = re.compile(r'e1s-touch: poll (\d+) device id: (.*?) \(((?:[0-9a-f]{2} ?){5})\)')
RE_HW = re.compile(r'e1s-touch: poll (\d+) hardware id: ((?:[0-9a-f]{2} ?){8})')
RE_PANIC = re.compile(r'^panic\(.*', re.M)


def trivial(byts):
    return all(b == 0 for b in byts) or all(b == 0xff for b in byts)


def parse_bytes(s):
    return [int(x, 16) for x in s.split()]


def classify(text, pixels):
    base = A124.classify(text, pixels)
    polls = {}
    for m in RE_DEV.finditer(text):
        polls.setdefault(int(m[1]), {})['device'] = dict(status=m[2], bytes=parse_bytes(m[3]))
    for m in RE_HW.finditer(text):
        polls.setdefault(int(m[1]), {})['hardware'] = parse_bytes(m[2])
    panic = RE_PANIC.search(text)
    out = dict(window=base['window'], display=base['display'], ios=base.get('ios'), power=base['power'],
               rail_readbacks=base['rail_readbacks'], polls=polls, complete='e1s-touch: poll-only diagnostic complete' in text,
               keys='K0-disabled' if 'e1s-keys: disabled (e1skeys=0)' in text else 'K1-not-disabled',
               physical_input='not-established', reasons=[])
    if panic and 'e1s_touch' in panic.group(0):
        out['touch'] = 'T0-fault'
        out['reasons'].append(panic.group(0)[:300])
    elif not any('device' in p for p in polls.values()):
        out['touch'] = 'T0-no-poll'
        out['reasons'].append('no poll device-id line')
    else:
        answers = []
        for n, p in sorted(polls.items()):
            for kind, byts in (('device', p.get('device', {}).get('bytes')), ('hardware', p.get('hardware'))):
                if byts is not None and not trivial(byts):
                    answers.append('poll %d %s id %s' % (n, kind, ' '.join('%02x' % b for b in byts)))
        if answers:
            out['touch'] = 'T2-chip-answers'
            out['reasons'] += answers
        else:
            out['touch'] = 'T1-no-response'
            out['reasons'].append('%d poll(s), every id all-00/all-ff' % len(polls))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--kernel-text', required=True, type=Path)
    ap.add_argument('--pixels', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    r = classify(a.kernel_text.read_text(errors='replace'), json.loads(a.pixels.read_text()))
    a.out.write_text(json.dumps(r, indent=2) + '\n')
    print(json.dumps({k: r[k] for k in ('window', 'display', 'touch', 'power', 'keys', 'physical_input')}))


if __name__ == '__main__':
    main()
