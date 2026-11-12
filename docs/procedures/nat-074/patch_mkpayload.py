#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074: derive mkpayload74.py from the pinned NAT-020 build-003 mkpayload.py (host only).

  patch_mkpayload.py --source PINNED_mkpayload.py --out mkpayload74.py

Base: artifacts/nat-020/build-003/source/tools/e1s/xnu/mkpayload.py, sha256 50c043e4033ceea682bd20134b5283c1abec51985d49609a3bce5ea0a4013ed7
(pinned by docs/procedures/nat-065/build.py). Licence of that source tree: GPL-2.0-only for the probe and loader (its README); this patch
is GPL-2.0-only as well. Upstream attribution stays with the base file.

Two additions, nothing else:
  --ramdisk1-reserve BYTES   adds /chosen/memory-map RAMDisk1 = <pa, BYTES> and moves kernel_end past the range, but adds NO segment: the
                             payload carries no bytes for it (the root is delivered later), the loader copies and zeroes nothing there,
                             and because the loader places the ADT and boot_args at kernel_end, topOfKernelData lies above the reserve.
                             BYTES must be a multiple of the 16 KiB page; it excludes --ramdisk1 (an image in the payload).
  --mem-size BYTES           the payload header's mem_size (the loader's second window limiter: win_size = min(win_size, mem_size), and
                             the loader refuses mem_size > 4 GiB). The ADT's own dram-size is left alone; the loader rewrites it at run time.
A hunk that does not match exactly once is an error."""
import argparse
import hashlib
import sys
from pathlib import Path

BASE_SHA256 = "50c043e4033ceea682bd20134b5283c1abec51985d49609a3bce5ea0a4013ed7"

HUNKS = [
    ("signature",
     "def build(kernel_path, adt_path, cmdline, ramdisk_path=None, ramdisk1_path=None):\n",
     "def build(kernel_path, adt_path, cmdline, ramdisk_path=None, ramdisk1_path=None, ramdisk1_reserve=None, mem_size=None):\n"),
    ("mem_size_override",
     "    PHYS_BASE, MEM_SIZE = adt_dram(adt_blob)\n",
     "    PHYS_BASE, MEM_SIZE = adt_dram(adt_blob)\n"
     "    if mem_size:    # NAT-074: the header's mem_size only; the ADT is rewritten by the loader\n"
     "        MEM_SIZE = mem_size\n"),
    ("reserve_block",
     "    hdr_size = SEG_TABLE + 32 * len(pieces)\n",
     "    if ramdisk1_reserve:    # NAT-074: a RAMDisk1 range without payload bytes\n"
     "        if ramdisk1_path:\n"
     "            raise SystemExit('--ramdisk1-reserve and --ramdisk1 exclude each other')\n"
     "        if ramdisk1_reserve % PAGE:\n"
     "            raise SystemExit('--ramdisk1-reserve must be a multiple of 16 KiB')\n"
     "        rd_va = kernel_end\n"
     "        kernel_end = rd_va + ramdisk1_reserve\n"
     "        rd_pa = rd_va - virt_base + PHYS_BASE\n"
     "        adt_blob = add_ramdisk_to_adt(adt_blob, rd_pa, ramdisk1_reserve, 'RAMDisk1')\n"
     "        ramdisk1 = (hex(rd_pa), hex(ramdisk1_reserve))\n"
     "\n"
     "    hdr_size = SEG_TABLE + 32 * len(pieces)\n"),
    ("args",
     "    ap.add_argument('--ramdisk1', help='second image for md1 (mounted by user space, never root)')\n",
     "    ap.add_argument('--ramdisk1', help='second image for md1 (mounted by user space, never root)')\n"
     "    ap.add_argument('--ramdisk1-reserve', type=int, help='NAT-074: RAMDisk1 range of this many bytes with no payload bytes')\n"
     "    ap.add_argument('--mem-size', type=int, help='NAT-074: payload header mem_size')\n"),
    ("call",
     "    blob, info = build(a.kernel, a.adt, a.cmdline, a.ramdisk, a.ramdisk1)\n",
     "    blob, info = build(a.kernel, a.adt, a.cmdline, a.ramdisk, a.ramdisk1, a.ramdisk1_reserve, a.mem_size)\n"),
]

NOTE = ("# NAT-074: derived from the pinned mkpayload.py (sha256 %s) by docs/procedures/nat-074/patch_mkpayload.py;\n"
        "# GPL-2.0-only like the source tree it comes from. Changes: --ramdisk1-reserve, --mem-size.\n" % BASE_SHA256)


def apply(text: str, hunks=HUNKS) -> str:
    for name, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"hunk {name}: expected exactly one match, found {n}; the source drifted")
        text = text.replace(old, new)
    first, rest = text.split("\n", 1)
    return first + "\n" + NOTE + rest


def derive(source: Path):
    raw = source.read_bytes()
    have = hashlib.sha256(raw).hexdigest()
    if have != BASE_SHA256:
        raise SystemExit(f"{source} is not the pinned mkpayload.py ({have})")
    out = apply(raw.decode()).encode()
    return out, {"base_sha256": have, "patched_sha256": hashlib.sha256(out).hexdigest(), "hunks": [h[0] for h in HUNKS]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        raise SystemExit(f"{a.out} exists; refusing to overwrite")
    out, rec = derive(a.source)
    a.out.write_bytes(out)
    print(rec)
    return 0


if __name__ == "__main__":
    sys.exit(main())
