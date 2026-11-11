#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-052: read the stop notes of loader-diag-xnu-ckpt3-usb from the text the NAT-049 collector archived.

  decode52.progress(lines)   lines = the TEXT records of one boot, in order (str)
                             -> {"stops": [note, ...], "last": checkpoint number or None, "held": bool, "hold": {...} or None,
                                 "exception": note or None, "gaps": [...]}

A note is the loader's line "CK n=.. arr=.. last=.. x2=0x.. x3=0x.. mask=0x.. sctlr=0x.. sp=0x.. kttbr0=0x.. vbar=0x.. setups=..", plus
" esr=0x.. elr=0x.. far=0x.." for an early kernel exception (x2 == 1). The field order is glue52_impl.h's nat052_note_stop.
Reads text only; opens no device."""
import re
import sys

HEX = r"0x[0-9a-f]+"
NOTE = re.compile(r"^CK n=(?P<n>-?\d+) arr=(?P<arr>-?\d+) last=(?P<last>-?\d+) x2=(?P<x2>%s) x3=(?P<x3>%s) mask=(?P<mask>%s) "
                  r"sctlr=(?P<sctlr>%s) sp=(?P<sp>%s) kttbr0=(?P<kttbr0>%s) vbar=(?P<vbar>%s) setups=(?P<setups>-?\d+)"
                  r"(?: esr=(?P<esr>%s) elr=(?P<elr>%s) far=(?P<far>%s))?$" % ((HEX,) * 10))
HOLD = re.compile(r"^HOLD stage=(?P<stage>%s) code=(?P<code>%s)$" % (HEX, HEX))
INT_FIELDS = ("n", "arr", "last", "setups")
HEX_FIELDS = ("x2", "x3", "mask", "sctlr", "sp", "kttbr0", "vbar", "esr", "elr", "far")
MASK_FINAL = 1 << 13          # NAT036_MASK_FINAL: the last stop of the list was reached (the intended hold)
MASK_BAD_TTBR0, MASK_BAD_STATE = 1 << 12, 1 << 14


def parse_note(line):
    m = NOTE.match(line)
    if not m:
        return None
    d = {k: int(m.group(k)) for k in INT_FIELDS}
    d.update({k: int(m.group(k), 16) for k in HEX_FIELDS if m.group(k) is not None})
    d["mmu_on"] = bool(d["sctlr"] & 1)
    d["exception"] = d["x2"] == 1
    return d


def progress(lines):
    notes, hold = [], None
    for line in lines:
        n = parse_note(line)
        if n is not None:
            notes.append(n)
            continue
        m = HOLD.match(line)
        if m:
            hold = {"stage": int(m.group("stage"), 16), "code": int(m.group("code"), 16)}
    gaps = [(a["n"], b["n"]) for a, b in zip(notes, notes[1:]) if b["n"] != a["n"] + 1]
    exc = next((n for n in notes if n["exception"]), None)
    last = notes[-1]["last"] if notes else None
    return {"stops": notes, "last": last, "held": hold is not None, "hold": hold, "exception": exc, "gaps": gaps,
            "reached_final": bool(notes and notes[-1]["mask"] & MASK_FINAL)}


def main(argv):
    if len(argv) != 2:
        raise SystemExit("usage: decode52.py FILE_WITH_ONE_TEXT_RECORD_PER_LINE")
    with open(argv[1], encoding="utf-8", errors="replace") as f:
        p = progress([l.rstrip("\n") for l in f])
    print("stops %d, last checkpoint %s, held %s, final %s, exception %s, gaps %s" % (
        len(p["stops"]), p["last"], p["held"], p["reached_final"], p["exception"] is not None, p["gaps"]))


if __name__ == "__main__":
    main(sys.argv)
