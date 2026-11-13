#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Host-only NAT-123 image; NAT-119 loader/ADT and NAT-121 input fixes.

The touch stage defaults to 3 in the compiled driver. Omitting the redundant
step token leaves room for e1spmic=2 under the 255-byte command-line bound.
"""
import importlib.util
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
NAME = "loader-diag-xnu-sc8-md1"
TAG = "nat_attempt=NAT123-sc8"
KERNEL_DIR = ROOT / "artifacts/nat-123/kernel-003"
KERNEL_PATCH = HERE.parent / "nat-121/loader_return.patch"
TOKENS = ("e1s_wdt_pet=1", "e1s_decon_hw=1", "e1spmic=2")
spec = importlib.util.spec_from_file_location("nat123_nat119", HERE.parent / "nat-119/build.py")
b119 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b119)


def append_new():
    return (" loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1sbattery=0 "
            + " ".join(b119.b115.REC_TOKENS + TOKENS))


def main():
    rec = json.loads((KERNEL_DIR / "rebuild.json").read_text())
    expected = {"bsd/e1s_touch.o", "bsd/redwood_input.o", "bsd/e1s_acpm.o", "bsd/e1s_pmic.o"}
    if {e["object"] for e in rec["extra_objects"]} != expected:
        raise SystemExit("expected the five-object kernel rebuild")
    for entry in rec["extra_objects"]:
        if b119.sha((ROOT / entry["patch"]).read_bytes()) != entry["patch_sha256"]:
            raise SystemExit("patch changed since rebuild: " + entry["patch"])
    saved = (b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS, b119.KERNEL_DIR,
             b119.KERNEL_PATCH, b119.b117.append_new)
    b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS = NAME, TAG, TOKENS
    b119.KERNEL_DIR, b119.KERNEL_PATCH = KERNEL_DIR, KERNEL_PATCH
    b119.b117.append_new = append_new
    args = list(sys.argv)
    try:
        b119.main()
    finally:
        sys.argv = args
        (b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS, b119.KERNEL_DIR,
         b119.KERNEL_PATCH, b119.b117.append_new) = saved
    if "--check-only" in args:
        return
    out = b119.b113.argv_value(args, "--out")
    if out is None:
        return
    path = Path(out) / "build.json"
    report = json.loads(path.read_text())
    tokens = report["payload_fixes"][NAME]["cmdline"].split()
    if any(t in tokens for t in ("e1stouch=0", "e1spmic=0", "e1stouch_steps=2")):
        raise SystemExit("unexpected disabled or staged input token")
    report["nat123_changes"] = {"image_name": NAME, "kernel": rec["no_storage_sha256"],
                                "touch_steps": "3 (compiled default)", "pmic_mode": 2,
                                "authorization": "decision 0049; per-image decision still required"}
    report["nat123_sources"] = {name: b119.sha((HERE / name).read_bytes())
                                for name in ("build.py", "e1s_acpm.patch", "e1s_pmic.patch")}
    path.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
