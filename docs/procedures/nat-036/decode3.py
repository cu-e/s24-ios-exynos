#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-036: decoder for the loader-diag-xnu-ckpt3 report. NAT-022's decode.py is used unchanged for everything it knows
(frame protocol, CRC, bands, the stage/regs/mask/ESR frames); this module adds the one new frame kind (13) and the reading of
a whole run.

  decode3.describe3(frames)  -> decode.describe's dict plus "ckpt3": {...} when kind-13 frames are present
  decode3.passes(frames)     -> the (arrivals, last_checkpoint) of every PASS frame, in order, consecutive repeats removed
  decode3.stops_missed(passes, stops) -> the checkpoints the list should have shown that no PASS frame covers

The PASS frame is data = (arrivals & 0xff) << 8 | (last & 0xff): the kernel passes the stops in program order, so a camera
that missed a frame is recovered from the next one (arrivals is a count, last is the number reached). Not a measurement tool:
it reads frames, it does not know whether they were drawn by the phone."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _base():
    spec = importlib.util.spec_from_file_location("nat022_decode", HERE.parent / "nat-022" / "decode.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


base = _base()
KIND_CKPT3 = 13
KINDS = dict(base.KINDS)
KINDS[KIND_CKPT3] = "CKPT3"
crc8, make_frame, parse_frame = base.crc8, base.make_frame, base.parse_frame

# idx of a CKPT3 frame (marker3.h enum mk_ckpt3_idx)
C3_PASS, C3_LIST = 0, 1
C3_SP = (2, 3, 4)
C3_KTTBR0 = (5, 6, 7)
C3_X1 = (8, 9)
C3_X0 = (10, 11, 12)

CKPT3_MASK_BITS = dict(base.CKPT_MASK_BITS)
CKPT3_MASK_BITS.update({12: "BAD: the TTBR0 read at checkpoint 5 is not a table base (nothing resumed)",
                        13: "final: the last stop of the list was reached (the intended hold)",
                        14: "BAD: a C stop arrived in a state the resume does not support (nothing resumed)"})


def _join(c, idxs, bits=16):
    if not set(idxs) <= set(c):
        return None
    v = 0
    for i in idxs:
        v = v << bits | c[i]
    return v


def describe3(frames):
    """base.describe with kind 13 understood. base.describe ignores kinds it does not know, so it is run on all frames."""
    out = base.describe(frames)
    c = {}
    for f in frames:
        if f["kind"] == KIND_CKPT3:
            c[f["idx"]] = f["data"]
    if c:
        k = {}
        if C3_PASS in c:
            k["arrivals"], k["last_checkpoint"] = c[C3_PASS] >> 8, c[C3_PASS] & 0xff
        if C3_LIST in c:
            k["stops_in_list"] = c[C3_LIST]
        for name, idxs, w in (("sp_lo48", C3_SP, 12), ("kernel_ttbr0_lo48", C3_KTTBR0, 12), ("x0_lo48", C3_X0, 12), ("x1_lo32", C3_X1, 8)):
            v = _join(c, idxs)
            if v is not None:
                k[name] = "0x%0*x" % (w, v)
        out["ckpt3"] = k
    ck = out.get("ckpt")
    if ck and "arrival_mask" in ck:
        ck["arrivals_seen"] = [n for b, n in sorted(CKPT3_MASK_BITS.items()) if ck["arrival_mask"] >> b & 1]
    return out


def passes(frames):
    out = []
    for f in frames:
        if f["kind"] == KIND_CKPT3 and f["idx"] == C3_PASS:
            p = (f["data"] >> 8, f["data"] & 0xff)
            if not out or out[-1] != p:
                out.append(p)
    return out


def stops_missed(seen, stops, first_c_arrival=6):
    """The checkpoints of `stops` (C stops after checkpoint 5, program order) that no PASS frame can account for. A PASS frame
    (arrivals, last) accounts for every stop up to its own: stop i of the list is arrival first_c_arrival + i."""
    reached = max((a for a, _ in seen), default=0)
    return [s for i, s in enumerate(stops) if first_c_arrival + i > reached]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw")
    a = ap.parse_args(argv)
    if not a.raw:
        ap.error("--raw")
    f = base.decode_raw(open(a.raw, "rb").read())
    print(json.dumps(describe3([f]) if f else None))


if __name__ == "__main__":
    main()
