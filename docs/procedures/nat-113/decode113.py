#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-113: decode the loader's pixel report (PX / PR text records, src/glue113.h) from a collector archive or a record list.

    decode113.py ARCHIVE_DIR [--json OUT.json] [--ppm OUT.ppm]

Verdicts (first match):
  X-incomplete               no `PX end` record, or the panel summary / 234 thumbnail rows are not all there
  P1-panel-has-pixels        the panel memory the display scans has non-black pixels
  R1-recording-has-pixels    the panel is black but a recorded frame has non-zero bytes
  R0-recording-black         a recording exists and every listed frame is all zero, the panel is black
  P0-black-no-recording      black panel, no usable recording (none / refused / bad-header)
A panel with pixels is evidence that something drew into the scanned memory; it is not by itself proof that it is iOS's
picture (the thumbnail is for a human to look at) nor that the panel was lit.
"""
import base64
import json
import re
import sys
from pathlib import Path

ROWS, COLS = 234, 108
FNV0, FNVP = 2166136261, 16777619


def fnv_words(words):
    h = FNV0
    for v in words:
        h = ((h ^ v) * FNVP) & 0xffffffff
    return h


def fnv_bytes(b):
    import struct
    return fnv_words(struct.unpack("<%dI" % (len(b) // 4), b[:len(b) // 4 * 4]))


def fnv_panel(mem, w, h, stride):
    import struct
    words = []
    for y in range(h):
        words.extend(struct.unpack_from("<%dI" % w, mem, y * stride))
    return fnv_words(words)


def _kv(text):
    return {k: v for k, v in re.findall(r"(\w+)=(\S+)", text)}


def _num(v):
    return int(v, 16) if v.startswith("0x") else int(v)


def decode(records):
    """records: the TEXT of each record in order -> report dict."""
    rep = {"panel": {"rows": [None] * ROWS}, "recording": {"state": "absent", "list": []}, "complete": False}
    for t in records:
        if t.startswith("PX panel "):
            kv = _kv(t)
            rep["panel"].update({k: _num(kv[k]) for k in ("pa", "w", "h", "stride", "step", "nonzero", "fnv")})
        elif t.startswith("PX r="):
            m = re.match(r"PX r=(\d+) ([0-9a-f]*)$", t)
            if m and int(m[1]) < ROWS and len(m[2]) == 2 * COLS:
                rep["panel"]["rows"][int(m[1])] = bytes.fromhex(m[2])
        elif t.startswith("PR rec "):
            kv = _kv(t)
            r = rep["recording"]
            r.update({k: _num(kv[k]) for k in ("pa", "bytes", "w", "h", "frames", "oldest", "began") if k in kv})
            r["state"] = ("none" if t.endswith(" none") else "refused" if t.endswith(" refused")
                          else "bad-header" if t.endswith(" bad-header") else "ok")
        elif t.startswith("PR f="):
            kv = _kv(t)
            rep["recording"]["list"].append({"f": int(kv["f"]), "ns": _num(kv["ns"]), "nzb": int(kv["nzb"]),
                                             "of": int(kv["of"]), "fnv": _num(kv["fnv"])})
        elif t.startswith("PX end "):
            rep["end_recs"] = int(_kv(t)["recs"])
    p = rep["panel"]
    rep["complete"] = "end_recs" in rep and "nonzero" in p and all(r is not None for r in p["rows"])
    return rep


def verdict(rep):
    if not rep["complete"]:
        return "X-incomplete"
    if rep["panel"]["nonzero"] > 0:
        return "P1-panel-has-pixels"
    r = rep["recording"]
    if r["state"] == "ok" and r["list"]:
        return "R1-recording-has-pixels" if any(f["nzb"] for f in r["list"]) else "R0-recording-black"
    return "P0-black-no-recording"


def thumbnail_ppm(rep):
    out = bytearray(b"P6 %d %d 255\n" % (COLS, ROWS))
    for row in rep["panel"]["rows"]:
        for v in row or bytes(COLS):
            out += bytes(((v & 0xe0), (v & 0x1c) << 3, (v & 0x03) << 6))
    return bytes(out)


def records_of_archive(root):
    """TEXT payloads starting with PX / PR from usb-transfers.jsonl, in transfer order (frames as the collector logged them)."""
    texts = []
    for line in Path(root, "usb-transfers.jsonl").read_text().splitlines():
        r = json.loads(line)
        if r.get("dir") != "in" or r.get("result") != "ok":
            continue
        data = base64.b64decode(r.get("data_b64", ""))
        for m in re.finditer(rb"(P[XR] [\x20-\x7e]*)", data):
            texts.append(m.group(1).decode("ascii"))
    return texts


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        sys.exit(__doc__)
    rep = decode(records_of_archive(argv[0]))
    v = verdict(rep)
    summary = {"verdict": v, "complete": rep["complete"], "panel_nonzero": rep["panel"].get("nonzero"),
               "panel_fnv": rep["panel"].get("fnv"), "recording": {k: x for k, x in rep["recording"].items() if k != "list"},
               "frames": rep["recording"]["list"]}
    if "--json" in argv:
        Path(argv[argv.index("--json") + 1]).write_text(json.dumps(summary, indent=1))
    if "--ppm" in argv:
        Path(argv[argv.index("--ppm") + 1]).write_bytes(thumbnail_ppm(rep))
    print(json.dumps({k: summary[k] for k in ("verdict", "complete", "panel_nonzero")}))


if __name__ == "__main__":
    main()
