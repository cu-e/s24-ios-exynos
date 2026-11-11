#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-044: decoder for the loader-diag-reset report. NAT-022's decode.py is used unchanged for everything it knows (frame
protocol, CRC, bands, stage/regs/mask frames); this module adds the one new frame kind (14, RST) and the new stage code (0x41).

  decode44.describe44(frames) -> decode.describe's dict plus "reset": {...} when RST frames are present
  decode44.status(data)       -> the fields of the RST status word (reset44.h NAT044_ST_*)
  decode44.reset_attempts(frames) -> how many RESET stage frames (0x41) were seen and the rc of every RST idx 7 (attempt returned) frame

The RST frames carry the entry snapshot of the three PMU words the vendor reboot path uses (INFORM3, INFORM2, reboot-cmd) taken by
the loader before it touched anything, and the state of the deadline. Not a measurement tool: it reads frames, it does not know
whether the phone drew them."""
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
KIND_RST = 14
ST_RESET = 0x41
KINDS = dict(base.KINDS)
KINDS[KIND_RST] = "RST"
crc8, make_frame, parse_frame, decode_raw = base.crc8, base.make_frame, base.parse_frame, base.decode_raw

# idx of an RST frame (reset44.h, patch_loader4.py MK_RST comment)
R_INFORM3 = (0, 1)
R_INFORM2 = (2, 3)
R_CMD = (4, 5)
R_STATUS = 6
R_RESULT = 7      # the same status word, drawn at once when the attempt returned (nothing was triggered)

# NAT044_ST_* of reset44.h
ST_RC_MASK, ST_FIRED, ST_ARMED, ST_CLEARED, ST_CLEARFAIL = 0x00FF, 0x1000, 0x2000, 0x4000, 0x8000
RC_NAMES = {0: "no result yet / trigger written (never returns)", 1: "reason refused (nothing written)",
            2: "INFORM2 did not read back (nothing after it written)", 3: "INFORM3 did not read back",
            4: "reboot-cmd mode bits did not read back"}


def status(data):
    """The status word: low byte = rc of s5e_reset_to (negated), bits 12..15 flags."""
    rc = data & ST_RC_MASK
    return {"rc": rc, "rc_meaning": RC_NAMES.get(rc, "unknown rc"), "fired": bool(data & ST_FIRED),
            "armed": bool(data & ST_ARMED), "leftover_request_cleared": bool(data & ST_CLEARED),
            "leftover_request_clear_failed": bool(data & ST_CLEARFAIL)}


def _word(c, hi_lo):
    hi, lo = hi_lo
    return "0x%08x" % (c[hi] << 16 | c[lo]) if hi in c and lo in c else None


def describe44(frames):
    out = base.describe(frames)
    c = {}
    for f in frames:
        if f["kind"] == KIND_RST:
            c[f["idx"]] = f["data"]
    stage_codes = [f["data"] for f in frames if f["kind"] == 3 and f["idx"] == 0]
    if ST_RESET in stage_codes:
        out["stages"] = [("reset into Download Mode attempted (NAT-044)" if s == "0x41" else s) for s in out.get("stages", [])]
    if c:
        r = {}
        for name, pair in (("inform3_at_entry", R_INFORM3), ("inform2_at_entry", R_INFORM2), ("reboot_cmd_at_entry", R_CMD)):
            v = _word(c, pair)
            if v is not None:
                r[name] = v
        if R_STATUS in c:
            r["status"] = status(c[R_STATUS])
        if R_RESULT in c:
            r["status_after_failed_attempt"] = status(c[R_RESULT])
        out["reset"] = r
    return out


def reset_attempts(frames):
    """(RESET stage frames seen, [rc of every RST idx 7 frame]): idx 7 is drawn only when the attempt returned."""
    n_reset = sum(1 for f in frames if f["kind"] == 3 and f["idx"] == 0 and f["data"] == ST_RESET)
    results = [f["data"] & ST_RC_MASK for f in frames if f["kind"] == KIND_RST and f["idx"] == R_RESULT]
    return n_reset, results


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw")
    a = ap.parse_args(argv)
    if not a.raw:
        ap.error("--raw")
    f = base.decode_raw(open(a.raw, "rb").read())
    print(json.dumps(describe44([f]) if f else None))


if __name__ == "__main__":
    main()
