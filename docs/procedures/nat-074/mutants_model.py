#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074: mutation run over the clear-plan / pet / reserve code of make_variant.py, build.py and patch_mkpayload.py, against test_model.py.
Each mutant edits one literal in a temporary copy of this directory (the rest of the repository is linked) and test_model.py must fail.
A mutant that survives is listed, not hidden; mutants judged equivalent by reasoning are named with the reason and must survive.
Needs the NAT-065 venv (unicorn, capstone) and zig, like test_model.py.

  artifacts/nat-065/venv/bin/python -W ignore -I docs/procedures/nat-074/mutants_model.py --json PATH [--only NAME]...

Patterns are the SOURCE text of the .py files (so C text appears with literal backslash-t / backslash-n)."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent

MV, BU, PM = "make_variant.py", "build.py", "patch_mkpayload.py"
M = [
    # --- clear plan
    ("plan-after-not-cut", MV, '"\\tif (after > top - kernel_end)\\n"', '"\\tif (0)\\n"'),
    ("plan-after-cut-wrong-way", MV, '"\\tif (after > top - kernel_end)\\n"', '"\\tif (after < top - kernel_end)\\n"'),
    ("plan-reserve-not-skipped", MV, "s[0].len = kernel_end - NAT074_RESERVE_BYTES - win_base;", "s[0].len = kernel_end - win_base;"),
    ("plan-reserve-skipped-one-page-short", MV, "s[0].len = kernel_end - NAT074_RESERVE_BYTES - win_base;",
     "s[0].len = kernel_end - NAT074_RESERVE_BYTES - win_base + 0x4000;"),
    ("plan-first-span-starts-late", MV, "s[0].base = win_base;", "s[0].base = win_base + 0x4000;"),
    ("plan-after-starts-late", MV, "s[1].base = kernel_end;", "s[1].base = kernel_end + 0x4000;"),
    ("plan-top-starts-early", MV, "s[2].base = top;", "s[2].base = top - 0x4000;"),
    ("plan-top-half-length", MV, "s[2].len = NAT074_CLEAR_TOP;", "s[2].len = NAT074_CLEAR_TOP / 2;"),
    ("plan-total-omits-top", MV, "return s[0].len + s[1].len + s[2].len;", "return s[0].len + s[1].len;"),
    # --- pet
    ("pet-period-doubled", MV, "g_nat044.pet_ticks = mk_freq() * (uint64_t)NAT074_PET_S;", "g_nat044.pet_ticks = mk_freq() * (uint64_t)NAT074_PET_S * 2;"),
    ("pet-never-from-tick", MV, "\\t\\t\\tnat074_pet(now);\\n\\t\\treturn;", "\\t\\t\\t(void)now;\\n\\t\\treturn;"),
    ("pet-also-after-cap", MV,
     '"\\tif (now - g_nat044.t0 < g_nat044.deadline_ticks) {\\n\\t\\tif (now - g_nat044.t_pet >= g_nat044.pet_ticks)\\n"',
     '"\\tif (now - g_nat044.t_pet >= g_nat044.pet_ticks)\\n\\t\\tnat074_pet(now);\\n\\tif (now - g_nat044.t0 < g_nat044.deadline_ticks) {\\n\\t\\tif (0)\\n"'),
    ("tick-falls-through-to-the-reset-path", MV, "\\t\\t\\tnat074_pet(now);\\n\\t\\treturn;\\n\\t}\\n", "\\t\\t\\tnat074_pet(now);\\n\\t}\\n"),
    ("pet-time-not-recorded", MV, "\\tg_nat044.t_pet = now;\\n\"", "\\t(void)now;\\n\""),
    ("pet-count-not-kept", MV, "\\tg_nat044.pets++;\\n\"", "\\t;\\n\""),
    ("arm-keeps-no-watchdog-handle", MV, "\\tg_nat044.wdt = *w;\\n\\tg_nat044.pet_ticks", "\\tg_nat044.pet_ticks"),
    ("arm-pet-clock-starts-at-zero", MV, "g_nat044.t_pet = g_nat044.t0;", "g_nat044.t_pet = 0;"),
    ("final-pet-ignores-the-cap", MV, "if (g_nat044.armed && now - g_nat044.t0 < g_nat044.deadline_ticks)", "if (g_nat044.armed)"),
    ("final-pet-ignores-armed", MV, "if (g_nat044.armed && now - g_nat044.t0 < g_nat044.deadline_ticks)", "if (now - g_nat044.t0 < g_nat044.deadline_ticks)"),
    ("final-pet-never", MV, "\\t\\tnat074_pet(now);\\n\"", "\\t\\t(void)now;\\n\""),
    ("cap-longer-in-the-arm-call", MV, "\\tg_nat044.deadline_ticks = mk_freq() * (uint64_t)NAT044_DEADLINE_S;\\t/* NAT-074",
     "\\tg_nat044.deadline_ticks = mk_freq() * (uint64_t)NAT044_DEADLINE_S * 2;\\t/* NAT-074"),
    # --- build rules
    ("build-reserve-not-padded", BU, "return (root_bytes + PAGE - 1) & ~(PAGE - 1)", "return root_bytes"),
    ("build-4k-check-dropped", BU, "if root_bytes % 4096:", "if False:"),
    ("build-pet-margin-dropped", BU, "pet_s + GUARD_MARGIN_S > wdt_s", "pet_s > wdt_s"),
    ("build-pet-margin-off-by-one", BU, "pet_s + GUARD_MARGIN_S > wdt_s", "pet_s + GUARD_MARGIN_S >= wdt_s"),
    ("build-cap-not-above-pet", BU, "if not pet_s < cap_s <= MAX_CAP_S:", "if not cap_s <= MAX_CAP_S:"),
    ("build-cap-max-dropped", BU, "if not pet_s < cap_s <= MAX_CAP_S:", "if not pet_s < cap_s:"),
    ("build-watchdog-period-unchecked", BU, "if wdt_s != WDT_S:", "if False:"),
    ("build-window-check-dropped", BU, "if mem_size != WINDOW_MIB * 1024 * 1024:", "if False:"),
    ("build-reserve-inside-kernel-end-dropped", BU, "if kernel_off < reserve:", "if False:"),
    ("build-free-ram-floor-dropped", BU, "if free_mib < MIN_FREE_MIB:", "if False:"),
    ("build-free-ram-floor-lowered", BU, "MIN_FREE_MIB = 1024 ", "MIN_FREE_MIB = 1 "),
    ("build-cmdline-keeps-the-touch-driver-on", BU, "    b65.APPEND = b67.APPEND\n", "    pass\n"),
    ("build-cmdline-keeps-the-nat065-tag", BU, "    b65.NEW_TAG = NEW_TAG ", "    pass; _ = NEW_TAG "),
    # --- mkpayload patch
    ("payload-reserve-has-no-adt-entry", PM, "adt_blob = add_ramdisk_to_adt(adt_blob, rd_pa, ramdisk1_reserve, 'RAMDisk1')", "pass"),
    ("payload-kernel-end-not-advanced", PM, "kernel_end = rd_va + ramdisk1_reserve", "kernel_end = rd_va"),
    ("payload-reserve-pa-off-by-a-page", PM, "rd_pa = rd_va - virt_base + PHYS_BASE\\n", "rd_pa = rd_va - virt_base + PHYS_BASE + 0x4000\\n"),
    ("payload-mem-size-ignored", PM, "        MEM_SIZE = mem_size\\n", "        pass\\n"),
]

# Judged equivalent by reasoning: they must survive (a killed one means the reasoning is wrong). None so far: the one candidate,
# `>=` -> `>` in the pet comparison, is an equivalent mutant of the same kind but is not in the list because it was never run.
EQUIVALENT = {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, required=True)
    ap.add_argument("--only", action="append", default=[])
    a = ap.parse_args()
    results = []
    for name, fname, old, new in M:
        if a.only and name not in a.only:
            continue
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
            t = Path(t)
            for entry in ROOT.iterdir():
                if entry.name in (".git",):
                    continue
                if entry.name == "docs":
                    (t / "docs").mkdir()
                    for sub in entry.iterdir():
                        if sub.name == "procedures":
                            (t / "docs/procedures").mkdir()
                            for proc in sub.iterdir():
                                if proc.name != "nat-074":
                                    os.symlink(proc, t / "docs/procedures" / proc.name)
                        else:
                            os.symlink(sub, t / "docs" / sub.name)
                else:
                    os.symlink(entry, t / entry.name)
            d = t / "docs/procedures/nat-074"
            d.mkdir()
            for f in HERE.glob("*.py"):
                (d / f.name).write_text(f.read_text())
            src = (d / fname).read_text()
            if src.count(old) != 1:
                results.append(dict(mutant=name, outcome="invalid", reason=f"pattern found {src.count(old)} times in {fname}"))
                continue
            (d / fname).write_text(src.replace(old, new))
            r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(d / "test_model.py")], capture_output=True, text=True, cwd=t)
            survived = r.returncode == 0
            if name in EQUIVALENT:
                outcome = "equivalent" if survived else "EQUIVALENT-WAS-KILLED"
            else:
                outcome = "SURVIVED" if survived else "killed"
            tail = [l for l in r.stderr.splitlines() if l.startswith(("FAIL:", "ERROR:", "RuntimeError", "SystemExit"))][:3]
            results.append(dict(mutant=name, file=fname, outcome=outcome, exit=r.returncode, first_failures=tail,
                                **({"reason": EQUIVALENT[name]} if name in EQUIVALENT else {})))
            print(name, outcome, flush=True)
    summary = {k: sum(1 for r in results if r["outcome"] == k) for k in ("killed", "equivalent", "SURVIVED", "EQUIVALENT-WAS-KILLED", "invalid")}
    a.json.write_text(json.dumps(dict(summary=summary, results=results), indent=1) + "\n")
    print(json.dumps(summary))
    return 1 if summary["SURVIVED"] or summary["invalid"] or summary["EQUIVALENT-WAS-KILLED"] else 0


if __name__ == "__main__":
    sys.exit(main())
