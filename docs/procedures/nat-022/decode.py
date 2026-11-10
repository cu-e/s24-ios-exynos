#!/usr/bin/env python3
"""NAT-022 decoder for framebuffer band markers (see src/marker.h).

Inputs are observations, never inferences about kernel execution:
  * raw: a linear dump of the marker region (host tests);
  * rows: per-row luminance (0..1) of a photographed/recorded screen, top to
    bottom, with the hypothesised row stride in bytes. Stride is unknown on the
    phone (NAT-005), so --strides tries candidates and keeps only those for
    which both sync bands and the CRC validate.
"""
from __future__ import annotations
import argparse, json, struct, sys

BAND_BYTES = 0x40000
PAYLOAD_BITS = 32
BANDS = 2 + PAYLOAD_BITS
KINDS = {1: "ENTRY", 2: "BOOTID", 3: "STAGE", 4: "ESR", 5: "ELR", 6: "FAR", 7: "SLOT", 8: "CHECK", 9: "REG", 10: "XNU", 11: "CKPT"}
KICK_STATUS = {0: "no kick", 1: "sent: global update + HW-trigger unmask", 2: "sent: global update + SW trigger",
               3: "skipped: DECON not enabled", 4: "skipped: video mode", 5: "skipped: MMU on",
               6: "skipped: earlier kick faulted"}
STAGES = {0x01: "entry", 0x02: "halt: MMU/cache on at entry", 0x03: "halt: unsupported EL",
          0x10: "canary C reached via call", 0x11: "about to BRK #0x1234", 0x1f: "exception record",
          0x20: "loader_main", 0x21: "loader fb selected", 0x30: "memory window chosen",
          0x31: "XNU RAM zeroed", 0x32: "kernel segments copied", 0x33: "ADT/boot_args built",
          0x34: "about to clean the XNU window", 0x3f: "loader fail() (STAGE idx2 = message hash)",
          0x40: "pre-jump (NOT proof of kernel entry)", 0x50: "inside XNU entry stub", 0x51: "inside NAT-031 return stub"}

def crc8(v24: int) -> int:
    crc = 0
    for b in (2, 1, 0):
        crc ^= (v24 >> (8 * b)) & 0xFF
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc

def make_frame(kind: int, idx: int, data16: int) -> int:
    v = ((kind & 0xF) << 20) | ((idx & 0xF) << 16) | (data16 & 0xFFFF)
    return (v << 8) | crc8(v)

def parse_frame(word: int):
    v = word >> 8
    if crc8(v) != (word & 0xFF):
        return None
    return {"kind": (v >> 20) & 0xF, "idx": (v >> 16) & 0xF, "data": v & 0xFFFF}

def bits_to_word(bits):
    w = 0
    for b in bits:
        w = (w << 1) | b
    return w

def decode_bands(levels):
    """levels: BANDS floats in 0..1. Sync: band0 high, band1 low; threshold between."""
    if len(levels) != BANDS:
        return None
    hi, lo = levels[0], levels[1]
    if hi - lo < 0.25:
        return None
    thr = (hi + lo) / 2
    word = bits_to_word(1 if x > thr else 0 for x in levels[2:])
    return parse_frame(word)

def decode_raw(buf: bytes):
    if len(buf) < BANDS * BAND_BYTES:
        return None
    levels = []
    for b in range(BANDS):
        seg = buf[b * BAND_BYTES:(b + 1) * BAND_BYTES]
        ones = sum(1 for i in range(0, len(seg), 4096) if seg[i:i + 8] == b"\xff" * 8)
        levels.append(ones / (len(seg) // 4096))
    return decode_bands(levels)

def rows_to_levels(rows, stride: int, total_rows=None):
    """Median luminance of the middle third of each band's rows."""
    out = []
    for b in range(BANDS):
        r0 = (b * BAND_BYTES) // stride
        r1 = ((b + 1) * BAND_BYTES) // stride
        if r1 > len(rows):
            return None
        span = max(r1 - r0, 1)
        sel = sorted(rows[r0 + span // 3: max(r0 + 2 * span // 3, r0 + span // 3 + 1)])
        out.append(sel[len(sel) // 2])
    return out

def decode_rows(rows, strides):
    """Return all valid (stride, frame) hypotheses; ambiguity is reported, not hidden."""
    hits = []
    for s in strides:
        lv = rows_to_levels(rows, s)
        f = decode_bands(lv) if lv else None
        if f:
            hits.append({"stride": s, **f})
    return hits

# loader-diag-trig: bit n of the STAGE idx1 mask = the loader reached this stage (drawn by mk_stage).
MASK_BITS = ["entry", "loader_main", "fb selected", "memory window", "RAM zeroed", "segments copied",
             "ADT built", "window clean started", "pre-jump", "fail", "xnu entry stub (NAT-028)",
             "ckpt return stub (NAT-031)"]

# NAT-031 CKPT frames (idx): 0 = x2<<8|x3 as the kernel passed them; 1 = arrival mask; 2/3 = SCTLR_EL1 low/high 16
# bits; 4/5/6 = TTBR1_EL1 bits 47:32/31:16/15:0; 7 = VBAR_EL1 bits 15:0; 8/9 = TCR_EL1 low/high 16 bits; 10 = arrivals.
CKPT_MASK_BITS = {1: "checkpoint 1", 2: "checkpoint 2", 3: "checkpoint 3", 4: "checkpoint 4", 5: "checkpoint 5",
                  8: "early-exception report (x2=1)", 9: "orderly end (x2=0)", 10: "other arrival (unexpected reason/code)"}

def fnv16(msg: str) -> int:
    """Independent implementation of mk_hash16: FNV-1a/32 folded to 16 bits."""
    h = 0x811C9DC5
    for b in msg.encode():
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return (h ^ (h >> 16)) & 0xFFFF

def describe(frames):
    """Assemble a sequence of decoded frames into named fields."""
    out, acc = {}, {}
    for f in frames:
        k = KINDS.get(f["kind"], f"kind{f['kind']}")
        if k == "ENTRY":
            d = f["data"]
            out["entry"] = {"el": d >> 14 & 3, "cur": {"M": d >> 13 & 1, "C": d >> 12 & 1, "I": d >> 11 & 1},
                            "el1": {"M": d >> 10 & 1, "C": d >> 9 & 1, "I": d >> 8 & 1}}
        elif k == "STAGE" and f["idx"] == 1:
            out["stage_mask"] = f["data"]
            out["stages_reached"] = [n for i, n in enumerate(MASK_BITS) if f["data"] >> i & 1]
        elif k == "STAGE" and f["idx"] == 2:
            out["stage_code"] = f["data"]
        elif k == "STAGE":
            out.setdefault("stages", []).append(STAGES.get(f["data"], hex(f["data"])))
        elif k == "CHECK":
            out["stack_roundtrip"] = f["data"] == 0xA5A5
        elif k == "SLOT":
            out["slot"] = f["data"]
        elif k == "BOOTID":
            acc.setdefault("bootid", {})[f["idx"]] = f["data"]
        elif k in ("ESR", "ELR", "FAR"):
            acc.setdefault(k, {})[f["idx"]] = f["data"]
        elif k == "REG":
            acc.setdefault("REG", {})[f["idx"]] = f["data"]
        elif k == "XNU":
            acc.setdefault("XNU", {})[f["idx"]] = f["data"]
        elif k == "CKPT":
            acc.setdefault("CKPT", {})[f["idx"]] = f["data"]
    c = acc.get("CKPT", {})
    if c:
        ck = {}
        if 0 in c:
            ck["x2"], ck["x3"] = c[0] >> 8, c[0] & 0xff
        if 1 in c:
            ck["arrival_mask"] = c[1]
            ck["arrivals_seen"] = [n for b, n in sorted(CKPT_MASK_BITS.items()) if c[1] >> b & 1]
        if 10 in c:
            ck["arrivals"] = c[10]
        if 2 in c and 3 in c:
            ck["sctlr_el1_lo32"] = "0x%08x" % (c[3] << 16 | c[2])
        if set(c) >= {4, 5, 6}:
            ck["ttbr1_el1_lo48"] = "0x%012x" % (c[4] << 32 | c[5] << 16 | c[6])
        if 7 in c:
            ck["vbar_el1_lo16"] = "0x%04x" % c[7]
        if 8 in c and 9 in c:
            ck["tcr_el1_lo32"] = "0x%08x" % (c[9] << 16 | c[8])
        out["ckpt"] = ck
    x = acc.get("XNU", {})
    if set(x) >= {0, 1, 2, 3}:
        out["xnu_stub_pc"] = "0x%016x" % bits_to_word_n([x[i] for i in range(4)])
    if set(x) >= {4, 5, 6, 7}:
        out["xnu_stub_x0"] = "0x%016x" % bits_to_word_n([x[i] for i in range(4, 8)])
    if "bootid" in acc and set(acc["bootid"]) >= {0, 1}:
        out["boot_id_cntvct32"] = acc["bootid"][1] << 16 | acc["bootid"][0]
    r = acc.get("REG", {})
    if r:
        d = {"kick_status": KICK_STATUS.get(r[0], hex(r[0])) if 0 in r else None}
        for name, hi, lo in (("global_con", 1, 2), ("trig_con_before", 3, 4), ("trig_con_after", 5, 6)):
            if hi in r and lo in r:
                d[name] = "0x%08x" % (r[hi] << 16 | r[lo])
        if 7 in r: d["frame_count_prev16"] = r[7]
        if 8 in r: d["frame_count_now16"] = r[8]
        if 9 in r: d["kicks"] = r[9]
        out["decon"] = d
    for k in ("ESR", "ELR", "FAR"):
        if k in acc and set(acc[k]) == {0, 1, 2, 3}:
            out[k.lower()] = "0x%016x" % bits_to_word_n([acc[k][i] for i in range(4)])
    return out

def bits_to_word_n(parts):
    v = 0
    for p in parts:
        v = v << 16 | p
    return v

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw")
    ap.add_argument("--rows", help="JSON list of per-row luminance 0..1")
    ap.add_argument("--strides", default="4320,4352,4096,4608,5120", help="candidate row strides in bytes")
    a = ap.parse_args(argv)
    if a.raw:
        print(json.dumps(decode_raw(open(a.raw, "rb").read())))
    elif a.rows:
        print(json.dumps(decode_rows(json.load(open(a.rows)), [int(x) for x in a.strides.split(",")])))
    else:
        ap.error("--raw or --rows")

if __name__ == "__main__":
    main()
