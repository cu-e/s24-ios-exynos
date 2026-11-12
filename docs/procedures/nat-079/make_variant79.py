#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-079: turn the NAT-074 big-window loader tree into the delivery loader tree (host only; compiles and runs nothing).

  make_variant79.py --source TREE_SHIM_E1S_XNU --out OUT_DIR [--record FILE] [--rx-cap-s N] [--rx-direct 0|1] [--report-s N]

TREE is shim/e1s-xnu of a tree that has already been through NAT-074's make_variant.patch_tree() (loader.c has the 4096 MiB window rule, the
reserve layout check and the clear plan; markerlib47.c is NAT-047's). The output is a copy with exact-match hunks applied (a hunk that does not
match exactly once is an error: a drifted base fails instead of being half-translated), the two source files src/nat079_impl.h and
src/nat079_fixed.h copied in, and a generated nat079.h holding the build parameters. What changes:

  markerlib47.c  the engine is brought up with the bulk-OUT endpoint present: rx_dest = a 512-byte placeholder, rx_size = 512 (a valid
                 NAT-076 configuration; the descriptor the host reads at enumeration depends on rx_present, and enumeration happens before the
                 loader knows where the reserve is). The sender refuses a file larger than the capacity GET_RX reports, so nothing is
                 accepted into the placeholder by the project's own sender. nat079_impl.h is included before the report frames.
  loader.c       one call between the end of the checkpoint-slot installation and the final cache clean: nat079_receive_root(win_base,
                 mem_end, kernel_end - NAT074_RESERVE_BYTES, NAT074_RESERVE_BYTES, &r) and the result written to the loader log.

The destination is NAT-074's reserve: [kernel_end - NAT074_RESERVE_BYTES, kernel_end), the RAMDisk1 range of the payload, never cleared and
never written by the loader before this phase. The result is GPL-2.0 like the loader it modifies."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"
DEFAULTS = {"rx_cap_s": 240, "rx_direct": 1, "report_s": 10}
SRC_FILES = ("nat079_impl.h", "nat079_fixed.h")

LOADER_CALL = (
    "\t/* NAT-079: the root image arrives over USB into the md1 reserve [kernel_end - NAT074_RESERVE_BYTES, kernel_end). Bounded by\n"
    "\t * NAT079_RX_CAP_S and by the NAT-044 deadline (nat044_tick pets the watchdog on every round); the boot goes on whatever the result. */\n"
    "\t{\n"
    "\t\tstruct nat079_result r79;\n"
    "\n"
    "\t\tnat079_receive_root(win_base, mem_end, kernel_end - NAT074_RESERVE_BYTES, NAT074_RESERVE_BYTES, &r79);\n"
    "\t\tdiagnostic_value(\"nat079_status\", (uint64_t)(int64_t)r79.status);\n"
    "\t\tdiagnostic_value(\"nat079_pa\", r79.pa);\n"
    "\t\tdiagnostic_value(\"nat079_bytes\", r79.bytes);\n"
    "\t\tdiagnostic_value(\"nat079_committed\", r79.committed);\n"
    "\t\tdiagnostic_value(\"nat079_rx_bytes\", r79.rx_bytes);\n"
    "\t\tdiagnostic_value(\"nat079_trbs\", r79.trbs);\n"
    "\t\tdiagnostic_value(\"nat079_errors\", r79.errors);\n"
    "\t\tdiagnostic_value(\"nat079_resets\", r79.resets);\n"
    "\t\tdiagnostic_value(\"nat079_dups\", r79.dups);\n"
    "\t\tdiagnostic_value(\"nat079_gaps\", r79.gaps);\n"
    "\t\tdiagnostic_value(\"nat079_rejects\", r79.rejects);\n"
    "\t\tdiagnostic_value(\"nat079_aborts\", r79.aborts);\n"
    "\t\tdiagnostic_value(\"nat079_last_sum\", r79.last_sum);\n"
    "\t\tdiagnostic_value(\"nat079_elapsed_ticks\", r79.elapsed_ticks);\n"
    "\t\tdiagnostic_value(\"nat079_freq\", r79.freq);\n"
    "\t\tdiagnostic_value(\"nat079_selftest_bad_pa\", r79.selftest_bad_pa);\n"
    "\t}\n"
)

LOADER_HUNKS = [
    ("include", "#include \"nat074.h\"\n", "#include \"nat074.h\"\n#include \"nat079.h\"\n"),
    ("receive_call", "\tNAT022_STAGE(MK_ST_LOADER_CLEAN);\n\tdiagnostic_value(\"clean_full_window_begin\",win_base);\n",
     LOADER_CALL + "\tNAT022_STAGE(MK_ST_LOADER_CLEAN);\n\tdiagnostic_value(\"clean_full_window_begin\",win_base);\n"),
]

MARKER_HUNKS = [
    ("include", "#include \"ladder.h\"\n", "#include \"ladder.h\"\n#include \"nat079.h\"\n"),
    ("hold_buffer", "struct nat047 g_nat047 __attribute__((aligned(64)));\n",
     "struct nat047 g_nat047 __attribute__((aligned(64)));\n\n"
     "/* NAT-079: destination of the engine's bulk-OUT stream until the loader has laid out the window (nat079_receive_root() replaces it). */\n"
     "static uint8_t g_nat079_hold[NAT079_HOLD_BYTES] __attribute__((aligned(64)));\n"),
    ("rx_config", "\tuc.gfladj_refclk_lpm_sel = NAT047_LPM_SEL;\n",
     "\tuc.gfladj_refclk_lpm_sel = NAT047_LPM_SEL;\n"
     "\tuc.rx_dest = g_nat079_hold;\t\t/* NAT-079: bulk-OUT endpoint present from the first descriptor read */\n"
     "\tuc.rx_size = NAT079_HOLD_BYTES;\n"
     "\tuc.rx_direct = NAT079_RX_DIRECT;\n"),
    ("impl_include", "/* The report frames of the hold and exception loops: status word, ladder stop code, its op, record count, bytes written. */\n",
     "#define N79_ENGINE()\t(&g_nat047.m)\n#define N79_UP()\t(g_nat047.up)\n"
     "#define N79_BARRIER()\t__asm__ volatile(\"dsb sy\" ::: \"memory\")\n"
     "#include \"nat079_impl.h\"\n\n"
     "/* The report frames of the hold and exception loops: status word, ladder stop code, its op, record count, bytes written. */\n"),
]

FILE_HUNKS = {"loader.c": LOADER_HUNKS, "markerlib47.c": MARKER_HUNKS}


def header_text(rx_cap_s, rx_direct, report_s):
    if not 0 < rx_cap_s <= 580:
        raise SystemExit("the receive cap must be in (0, 580] seconds (the NAT-044 deadline is at most 600 s)")
    if rx_direct not in (0, 1):
        raise SystemExit("rx_direct is 0 (staged: the controller writes the DMA block, the CPU copies) or 1 (the controller writes the reserve)")
    if not 0 < report_s <= rx_cap_s:
        raise SystemExit("the report period must be in (0, cap]")
    return (
        "/* SPDX-License-Identifier: GPL-2.0-only */\n"
        "/* NAT-079: generated by make_variant79.py. Build parameters of the delivery loader variant. */\n"
        "#ifndef NAT079_H\n#define NAT079_H\n"
        f"#define NAT079_RX_CAP_S\t\t{rx_cap_s}\t/* the receive phase gives up after this many seconds */\n"
        f"#define NAT079_RX_DIRECT\t{rx_direct}\t/* 1: the controller DMAs into the reserve; 0: staged through the engine's DMA block */\n"
        f"#define NAT079_REPORT_S\t\t{report_s}\t/* progress line period */\n"
        "#include \"nat079_fixed.h\"\n#endif\n")


def apply(text, hunks):
    for name, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"hunk {name}: expected exactly one match, found {n}; the source drifted")
        text = text.replace(old, new)
    return text


def patch_tree(tree, params=None):
    """Apply the NAT-079 hunks to TREE (shim/e1s-xnu after NAT-074's patch_tree) in place. Returns the record."""
    tree = Path(tree)
    p = dict(DEFAULTS, **(params or {}))
    hdr = header_text(p["rx_cap_s"], p["rx_direct"], p["report_s"]).encode()
    rec = {"params": p, "files": {}, "hunks": {}}
    patched = {}
    for fname, hunks in FILE_HUNKS.items():          # every hunk of every file first: a drifted base writes nothing at all
        src = (tree / fname).read_bytes()
        patched[fname] = apply(src.decode(), hunks).encode()
        rec["files"][fname] = {"source_sha256": hashlib.sha256(src).hexdigest(), "variant_sha256": hashlib.sha256(patched[fname]).hexdigest()}
        rec["hunks"][fname] = [h[0] for h in hunks]
    for fname, new in patched.items():
        (tree / fname).write_bytes(new)
    for f in SRC_FILES:
        data = (SRC / f).read_bytes()
        (tree / f).write_bytes(data)
        rec["files"][f] = {"source_sha256": None, "variant_sha256": hashlib.sha256(data).hexdigest()}
    (tree / "nat079.h").write_bytes(hdr)
    rec["files"]["nat079.h"] = {"source_sha256": None, "variant_sha256": hashlib.sha256(hdr).hexdigest()}
    return rec


def derive(source, out, params=None):
    out = Path(out)
    if out.exists():
        raise SystemExit(f"{out} exists; refusing to overwrite")
    shutil.copytree(source, out)
    return patch_tree(out, params)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--record", type=Path)
    ap.add_argument("--rx-cap-s", type=int, default=DEFAULTS["rx_cap_s"])
    ap.add_argument("--rx-direct", type=int, default=DEFAULTS["rx_direct"])
    ap.add_argument("--report-s", type=int, default=DEFAULTS["report_s"])
    a = ap.parse_args()
    rec = derive(a.source, a.out, {"rx_cap_s": a.rx_cap_s, "rx_direct": a.rx_direct, "report_s": a.report_s})
    if a.record:
        a.record.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
