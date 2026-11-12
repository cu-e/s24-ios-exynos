#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-074: compile the loader's own window code (variant or original) into the NAT-006 harness and run it on a DTB (host only).

  check_big_window.py --shim SHIM_DIR --dtb DTB --out DIR

Builds with the NAT-006 harness (docs/procedures/nat-006/window_harness.c) over the unchanged fdt.c and the ranges_sort..choose_window
text extracted verbatim from SHIM_DIR/loader.c. The DTB is mapped at the placement address, as the loader sees it. As a library:
build(shim, out) -> harness path, run(harness, dtb) -> result dict."""
import argparse
import importlib.util
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAT006 = HERE.parent / "nat-006"
CLANG = "/home/egor/.local/bin/clang"
# One placement is enough here: the exclusions (loader image, DTB, payload) are in the low bank, away from the high region.
PLACEMENT = dict(dtb=0x84000000, image=0x80000000, image_end=0x80040000, payload=0x85100000)


def _nat006():
    spec = importlib.util.spec_from_file_location("nat006_check_loader", NAT006 / "check_loader.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def build(shim: Path, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    chunk = _nat006().extract(shim / "loader.c")
    (out / "window_extract.inc").write_text(chunk)
    exe = out / "window_harness"
    argv = [CLANG, "-std=gnu11", "-O1", "-g", "-Wall", "-Wextra", "-fsanitize=undefined", "-fno-sanitize-recover=all",
            *(["-DHAVE_SELECT_FB"] if "\nloader_select_fb(" in chunk else []),
            "-I", str(shim), "-I", str(out), str(NAT006 / "window_harness.c"), str(shim / "fdt.c"), "-o", str(exe)]
    r = subprocess.run(argv, capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"harness build failed:\n{r.stderr[-2000:]}")
    return exe


def run(exe: Path, dtb: Path, placement=PLACEMENT) -> dict:
    r = subprocess.run([str(exe), str(dtb), *(hex(placement[k]) for k in ("dtb", "image", "image_end", "payload"))],
                       capture_output=True, text=True, env={"ASAN_OPTIONS": "detect_leaks=0"})
    if r.returncode:
        raise RuntimeError(f"harness exit {r.returncode}: {r.stderr[-1000:]}")
    return json.loads(r.stdout)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shim", type=Path, required=True)
    ap.add_argument("--dtb", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    res = run(build(a.shim, a.out), a.dtb)
    (a.out / "result.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res["window"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
