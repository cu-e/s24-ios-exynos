#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074: derive the big-window loader variant from the NAT-065 build tree (host only).

  make_variant.py --source SRC_SHIM_DIR --out OUT_SHIM_DIR [--record FILE]
                  [--reserve-bytes N] [--clear-after-mib N] [--clear-top-mib N] [--pet-s N]

SRC_SHIM_DIR is a copy of shim/e1s-xnu from the NAT-065 build (the loader that ran in NAT-068). The output is a copy of that
directory with exact-match hunks applied to loader.c, markerlib4.c, reset44.h and guard.c, plus a generated nat074.h; a hunk that
does not match exactly once is an error (the derivation never guesses). What changes, by hunk group:

  window     MAX_WINDOW 512 MiB -> 4096 MiB, and /memory nodes that touch or overlap are merged before the gap search (the S24
             lists 6 GiB at 0x880000000 as three 2 GiB nodes).
  clear      the RAM clear no longer walks the whole window. It clears [win_base, kernel_end - RESERVE), the first CLEAR_AFTER bytes
             above kernel_end (ADT, boot_args, the kernel's first allocations) and the top CLEAR_TOP bytes (PRAM); the range of the
             reserve-only RAMDisk1 inside kernel_end is never touched. A layout check refuses an image whose reserve does not fit.
  pet        the NAT-044 deadline (build -DNAT044_DEADLINE_S, now a hard cap) is kept as the only exit; while it has not passed,
             nat044_tick pets the hardware watchdog every PET_S seconds, and a final forced pet (same single call site) is made just
             before the jump. s5e_wdt_pet is called from exactly one place, nat074_pet() in markerlib4.c (noinline).

The result is GPL-2.0 like the loader it modifies. Nothing here compiles or runs anything."""
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

DEFAULTS = {"reserve_bytes": 2475720704, "clear_after_mib": 64, "clear_top_mib": 2, "pet_s": 30}

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

# --- loader.c: window rule (the first step of this task) -------------------------------------------------------------------
HUNKS = [
    ("max_window", "#define MAX_WINDOW\t(512UL << 20)\n",
     "#define MAX_WINDOW\t(4096UL << 20)\t/* NAT-074: was 512 MiB */\n"),
    ("merge_function", "static void\nconsider_gap(", MERGE_FN + "static void\nconsider_gap("),
    ("merge_call", "\tif (nmem <= 0)\n\t\treturn 0;\n\tnocc = fdt_reserved_ranges(dtb, occ, MAX_RANGES - 4);\n",
     "\tif (nmem <= 0)\n\t\treturn 0;\n\tranges_sort(mem, nmem);\n\tnmem = ranges_merge(mem, nmem);\n\tif (nmem <= 0)\n\t\treturn 0;\n"
     "\tnocc = fdt_reserved_ranges(dtb, occ, MAX_RANGES - 4);\n"),
]

# --- loader.c: clear plan, layout check, final pet ---------------------------------------------------------------------------
CLEAR_PLAN_FN = (
    "/* NAT-074: what the loader clears before the handoff. The range reserved inside kernel_end for the root image\n"
    " * (NAT074_RESERVE_BYTES, filled later, never by this loader's clear) is skipped. The rest of the window is not cleared: the\n"
    " * kernel's allocators zero what they hand out (page-table pages are bzero'd by their callers, arm_vm_init.c alloc_ptpage users).\n"
    " * Spans: [win_base, kernel_end - reserve), [kernel_end, +NAT074_CLEAR_AFTER) (cut at the top span), [mem_end - NAT074_CLEAR_TOP, mem_end).\n"
    " * The caller has checked reserve <= kernel_end - win_base and kernel_end <= mem_end - NAT074_CLEAR_TOP. Returns the total.\n"
    " * noinline so that the emitted code can be run on its own by the host model. */\n"
    "struct nat074_span {\n"
    "\tuint64_t base, len;\n"
    "};\n"
    "\n"
    "static __attribute__((noinline)) uint64_t\n"
    "nat074_clear_plan(uint64_t win_base, uint64_t mem_end, uint64_t kernel_end, struct nat074_span *s)\n"
    "{\n"
    "\tuint64_t top = mem_end - NAT074_CLEAR_TOP;\n"
    "\tuint64_t after = NAT074_CLEAR_AFTER;\n"
    "\n"
    "\tif (after > top - kernel_end)\n"
    "\t\tafter = top - kernel_end;\n"
    "\ts[0].base = win_base;\n"
    "\ts[0].len = kernel_end - NAT074_RESERVE_BYTES - win_base;\n"
    "\ts[1].base = kernel_end;\n"
    "\ts[1].len = after;\n"
    "\ts[2].base = top;\n"
    "\ts[2].len = NAT074_CLEAR_TOP;\n"
    "\treturn s[0].len + s[1].len + s[2].len;\n"
    "}\n"
    "\n"
)

CLEAR_OLD = (
    "\t\tfor (uint64_t off = 0; off < win_size; off += step) {\n"
    "\t\t\tchar b[64];\n"
    "\t\t\tchar *q = b;\n"
    "\t\t\tuint64_t n = win_size - off;\n"
    "\n"
    "\t\t\tif (n > step)\n"
    "\t\t\t\tn = step;\n"
    "\t\t\tzero(win_base + off, n);\n"
    "\t\t\tdiagnostic_value(\"zero_bytes\",off+n);\n"
    "\t\t\tq = ui_put_dec(q, (off + n) >> 20);\n"
    "\t\t\tq = ui_put_str(q, \" MiB\");\n"
    "\t\t\tui_set_progress(&ui,\n"
    "\t\t\t    (int)(((off + n) * 100) / win_size),\n"
    "\t\t\t    \"Clearing XNU RAM\");\n"
    "\t\t\tui_set_status(&ui, b, UI_TEXT_DIM);\n"
    "\t\t\tfb_flush();\n"
    "\t\t}\n"
)

CLEAR_NEW = (
    "\t\tstruct nat074_span cl[3];\n"
    "\t\tuint64_t total = nat074_clear_plan(win_base, mem_end, kernel_end, cl), done = 0;\n"
    "\n"
    "\t\tfor (int i = 0; i < 3; i++) {\n"
    "\t\t\tfor (uint64_t off = 0; off < cl[i].len; off += step) {\n"
    "\t\t\t\tchar b[64];\n"
    "\t\t\t\tchar *q = b;\n"
    "\t\t\t\tuint64_t n = cl[i].len - off;\n"
    "\n"
    "\t\t\t\tif (n > step)\n"
    "\t\t\t\t\tn = step;\n"
    "\t\t\t\tzero(cl[i].base + off, n);\n"
    "\t\t\t\tdone += n;\n"
    "\t\t\t\tdiagnostic_value(\"zero_bytes\",done);\n"
    "\t\t\t\tq = ui_put_dec(q, done >> 20);\n"
    "\t\t\t\tq = ui_put_str(q, \" MiB\");\n"
    "\t\t\t\tui_set_progress(&ui, (int)((done * 100) / total),\n"
    "\t\t\t\t    \"Clearing XNU RAM\");\n"
    "\t\t\t\tui_set_status(&ui, b, UI_TEXT_DIM);\n"
    "\t\t\t\tfb_flush();\n"
    "\t\t\t}\n"
    "\t\t}\n"
)

LAYOUT_OLD = (
    "\tif (kernel_end >= mem_end) {\n"
    "\t\tui_set_stage(&ui, UI_STAGE_RAM, UI_FAIL);\n"
    "\t\treturn fail(\"kernel larger than RAM window\");\n"
    "\t}\n"
)
LAYOUT_NEW = LAYOUT_OLD + (
    "\t/* NAT-074: the reserve-only RAMDisk1 range lies inside kernel_end; the clear plan and ADT placement rely on this. */\n"
    "\tif (NAT074_RESERVE_BYTES > kernel_end - win_base || (NAT074_RESERVE_BYTES & (PAGE_16K - 1)) ||\n"
    "\t    kernel_end > mem_end - NAT074_CLEAR_TOP - (1UL << 20)) {\n"
    "\t\tui_set_stage(&ui, UI_STAGE_RAM, UI_FAIL);\n"
    "\t\treturn fail(\"reserve layout does not fit the window\");\n"
    "\t}\n"
)

CLEAR_HUNKS = [
    ("include_nat074", "#include \"usb47.h\"\n", "#include \"usb47.h\"\n#include \"nat074.h\"\n"),
    ("clear_plan_fn", "#define MIN_WINDOW\t(256UL << 20)\n", CLEAR_PLAN_FN + "#define MIN_WINDOW\t(256UL << 20)\n"),
    ("layout_check", LAYOUT_OLD, LAYOUT_NEW),
    ("clear_loop", CLEAR_OLD, CLEAR_NEW),
    ("final_pet", "\thold_seconds(hold);\n\tNAT022_STAGE(MK_ST_PRE_JUMP);",
     "\thold_seconds(hold);\n\tnat074_final_pet();\t/* NAT-074: last watchdog pet before the jump, only while the cap has not passed */\n"
     "\tNAT022_STAGE(MK_ST_PRE_JUMP);"),
]

# --- markerlib4.c / reset44.h / guard.c: bounded watchdog pet -----------------------------------------------------------------
PET_FN = (
    "/* NAT-074: the only place the loader pets the watchdog (the binary check counts the calls of s5e_wdt_pet: exactly one, here).\n"
    " * Called from nat044_tick every NAT074_PET_S seconds while the cap has not passed, and once from nat074_final_pet(). */\n"
    "static __attribute__((noinline)) void nat074_pet(uint64_t now)\n"
    "{\n"
    "\ts5e_wdt_pet(&g_nat044.wdt);\n"
    "\tg_nat044.t_pet = now;\n"
    "\tg_nat044.pets++;\n"
    "}\n"
    "\n"
    "/* Forced pet before the handoff: the kernel then has the whole watchdog period. Never after the cap or after the reset path ran. */\n"
    "void nat074_final_pet(void)\n"
    "{\n"
    "\tuint64_t now = mk_cnt();\n"
    "\n"
    "\tif (g_nat044.armed && now - g_nat044.t0 < g_nat044.deadline_ticks)\n"
    "\t\tnat074_pet(now);\n"
    "}\n"
    "\n"
)

MARKER_HUNKS = [
    ("arm", "void nat044_arm(void)\n{\n#if NAT044_DEADLINE_S > 0\n\tg_nat044.t0 = mk_cnt();\n"
            "\tg_nat044.deadline_ticks = mk_freq() * (uint64_t)NAT044_DEADLINE_S;\n\tg_nat044.armed = g_nat044.pmu != 0;\n",
     "void nat044_arm(const struct s5e_wdt *w)\n{\n#if NAT044_DEADLINE_S > 0\n\tg_nat044.t0 = mk_cnt();\n"
     "\tg_nat044.deadline_ticks = mk_freq() * (uint64_t)NAT044_DEADLINE_S;\t/* NAT-074: a hard cap, not a margin inside the watchdog */\n"
     "\tg_nat044.wdt = *w;\n\tg_nat044.pet_ticks = mk_freq() * (uint64_t)NAT074_PET_S;\n\tg_nat044.t_pet = g_nat044.t0;\n"
     "\tg_nat044.armed = g_nat044.pmu != 0;\n"),
    ("pet_fn", "/* Polled from every wait loop of the marker library (mk_wait_tenths), so the deadline is met to within one draw.",
     PET_FN + "/* Polled from every wait loop of the marker library (mk_wait_tenths), so the deadline is met to within one draw."),
    ("tick", "static void nat044_tick(void)\n{\n\tif (!g_nat044.armed)\n\t\treturn;\n"
             "\tif (mk_cnt() - g_nat044.t0 < g_nat044.deadline_ticks)\n\t\treturn;\n",
     "static void nat044_tick(void)\n{\n\tuint64_t now;\n\n\tif (!g_nat044.armed)\n\t\treturn;\n\tnow = mk_cnt();\n"
     "\tif (now - g_nat044.t0 < g_nat044.deadline_ticks) {\n\t\tif (now - g_nat044.t_pet >= g_nat044.pet_ticks)\n"
     "\t\t\tnat074_pet(now);\n\t\treturn;\n\t}\n"),
]

RESET44_HUNKS = [
    ("includes", "#include \"s5e9945_reset.h\"\n", "#include \"s5e9945_reset.h\"\n#include \"s5e9945.h\"\n#include \"nat074.h\"\n"),
    ("struct", "\tuint32_t inform2_0, inform3_0, cmd_0;\t/* entry snapshot, taken before anything else touched the PMU */\n};",
     "\tuint32_t inform2_0, inform3_0, cmd_0;\t/* entry snapshot, taken before anything else touched the PMU */\n"
     "\tstruct s5e_wdt wdt;\t\t\t/* NAT-074: copy of guard.c's watchdog handle, for the bounded pet */\n"
     "\tuint64_t pet_ticks, t_pet;\n\tuint32_t pets;\n};"),
    ("arm_prototype", "void nat044_arm(void);\t\t\t\t/* guard.c: right after the watchdog is armed */",
     "void nat044_arm(const struct s5e_wdt *w);\t/* guard.c: right after the watchdog is armed */"),
]

GUARD_HUNKS = [
    ("extern", "extern void nat044_arm(void);\n", "extern void nat044_arm(const struct s5e_wdt *w);\n"),
    ("call", "    nat044_arm();\n", "    nat044_arm(&w);\n"),
]

FILE_HUNKS = {
    "loader.c": HUNKS + CLEAR_HUNKS,
    "markerlib4.c": MARKER_HUNKS,
    "reset44.h": RESET44_HUNKS,
    "guard.c": GUARD_HUNKS,
}


def header_text(reserve_bytes, clear_after_mib, clear_top_mib, pet_s):
    if reserve_bytes % 16384:
        raise SystemExit("the reserve must be a multiple of 16 KiB (the kernel's page size once memSize > 1 GiB)")
    if not (0 < pet_s < 60):
        raise SystemExit("the pet period must be in (0, 60) seconds for an 83 s watchdog")
    return (
        "/* SPDX-License-Identifier: GPL-2.0-only */\n"
        "/* NAT-074: generated by make_variant.py. Build-time constants of the big-window loader variant. */\n"
        "#ifndef NAT074_H\n#define NAT074_H\n#include <stdint.h>\n"
        f"#define NAT074_RESERVE_BYTES\t{reserve_bytes}ULL\t/* reserve-only RAMDisk1 range inside the payload's kernel_end */\n"
        f"#define NAT074_CLEAR_AFTER\t({clear_after_mib}ULL << 20)\t/* cleared above kernel_end: ADT, boot_args, first allocations */\n"
        f"#define NAT074_CLEAR_TOP\t({clear_top_mib}ULL << 20)\t/* cleared at the top of the window: PRAM */\n"
        f"#define NAT074_PET_S\t\t{pet_s}\t/* watchdog pet period while the cap has not passed */\n"
        "void nat074_final_pet(void);\n"
        "#endif\n")


def apply(text: str, hunks=HUNKS) -> str:
    for name, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"hunk {name}: expected exactly one match, found {n}; the source drifted")
        text = text.replace(old, new)
    return text


def patch_tree(tree: Path, params=None):
    """Apply every hunk group to TREE (a copy of shim/e1s-xnu) in place and write nat074.h. Returns the record."""
    p = dict(DEFAULTS, **(params or {}))
    rec = {"params": p, "files": {}, "hunks": {}}
    for fname, hunks in FILE_HUNKS.items():
        src = (tree / fname).read_bytes()
        new = apply(src.decode(), hunks).encode()
        (tree / fname).write_bytes(new)
        rec["files"][fname] = {"source_sha256": hashlib.sha256(src).hexdigest(), "variant_sha256": hashlib.sha256(new).hexdigest()}
        rec["hunks"][fname] = [h[0] for h in hunks]
    hdr = header_text(p["reserve_bytes"], p["clear_after_mib"], p["clear_top_mib"], p["pet_s"]).encode()
    (tree / "nat074.h").write_bytes(hdr)
    rec["files"]["nat074.h"] = {"source_sha256": None, "variant_sha256": hashlib.sha256(hdr).hexdigest()}
    return rec


def derive(source: Path, out: Path, params=None):
    if out.exists():
        raise SystemExit(f"{out} exists; refusing to overwrite")
    shutil.copytree(source, out)
    return patch_tree(out, params)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--record", type=Path)
    ap.add_argument("--reserve-bytes", type=int, default=DEFAULTS["reserve_bytes"])
    ap.add_argument("--clear-after-mib", type=int, default=DEFAULTS["clear_after_mib"])
    ap.add_argument("--clear-top-mib", type=int, default=DEFAULTS["clear_top_mib"])
    ap.add_argument("--pet-s", type=int, default=DEFAULTS["pet_s"])
    a = ap.parse_args()
    rec = derive(a.source, a.out, {"reserve_bytes": a.reserve_bytes, "clear_after_mib": a.clear_after_mib,
                                   "clear_top_mib": a.clear_top_mib, "pet_s": a.pet_s})
    if a.record:
        a.record.write_text(json.dumps(rec, indent=1) + "\n")
    print(json.dumps(rec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
