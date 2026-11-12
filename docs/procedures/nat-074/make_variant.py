#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074: derive the big-window loader variant from the NAT-065 build tree (host only).

  make_variant.py --source SRC_SHIM_DIR --out OUT_SHIM_DIR [--record FILE]

SRC_SHIM_DIR is a copy of shim/e1s-xnu from the NAT-065 build (the loader that ran in NAT-068). The output is a copy of that
directory whose loader.c has exact-match hunks applied; a hunk that does not match exactly once is an error (the derivation never
guesses). Only the window rule is changed here: MAX_WINDOW 512 MiB -> 4096 MiB, and /memory nodes that touch or overlap are merged
before the gap search (the S24 lists 6 GiB at 0x880000000 as three 2 GiB nodes). The clear, the reserve, the deadline cap and the
watchdog pet are later hunks of the same derivation (same task). The result is GPL-2.0 like the loader it modifies."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

MERGE_FN = (
    "/* NAT-074: touching or overlapping /memory nodes are one RAM range. Input must be sorted by base. */\n"
    "static int\n"
    "ranges_merge(struct fdt_range *r, int n)\n"
    "{\n"
    "\tint out = 0;\n"
    "\n"
    "\tfor (int i = 0; i < n; i++) {\n"
    "\t\tuint64_t end = r[i].base + r[i].size;\n"
    "\n"
    "\t\tif (r[i].size == 0 || end < r[i].base)\n"
    "\t\t\tcontinue;\n"
    "\t\tif (out > 0 && r[i].base <= r[out - 1].base + r[out - 1].size) {\n"
    "\t\t\tif (end > r[out - 1].base + r[out - 1].size)\n"
    "\t\t\t\tr[out - 1].size = end - r[out - 1].base;\n"
    "\t\t\tcontinue;\n"
    "\t\t}\n"
    "\t\tr[out++] = r[i];\n"
    "\t}\n"
    "\treturn out;\n"
    "}\n"
    "\n"
)

HUNKS = [
    ("max_window", "#define MAX_WINDOW\t(512UL << 20)\n",
     "#define MAX_WINDOW\t(4096UL << 20)\t/* NAT-074: was 512 MiB */\n"),
    ("merge_function", "static void\nconsider_gap(", MERGE_FN + "static void\nconsider_gap("),
    ("merge_call", "\tif (nmem <= 0)\n\t\treturn 0;\n\tnocc = fdt_reserved_ranges(dtb, occ, MAX_RANGES - 4);\n",
     "\tif (nmem <= 0)\n\t\treturn 0;\n\tranges_sort(mem, nmem);\n\tnmem = ranges_merge(mem, nmem);\n\tif (nmem <= 0)\n\t\treturn 0;\n"
     "\tnocc = fdt_reserved_ranges(dtb, occ, MAX_RANGES - 4);\n"),
]


def apply(text: str, hunks=HUNKS) -> str:
    for name, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"hunk {name}: expected exactly one match, found {n}; the source drifted")
        text = text.replace(old, new)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--record", type=Path)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; refusing to overwrite")
    src = (a.source / "loader.c").read_bytes()
    shutil.copytree(a.source, a.out)
    out = apply(src.decode()).encode()
    (a.out / "loader.c").write_bytes(out)
    rec = {"source_loader_c_sha256": hashlib.sha256(src).hexdigest(), "variant_loader_c_sha256": hashlib.sha256(out).hexdigest(),
           "hunks": [h[0] for h in HUNKS]}
    if a.record:
        a.record.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
