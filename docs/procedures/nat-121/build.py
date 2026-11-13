#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-121 host build: `loader-diag-xnu-sc7-md1` = NAT-119's image with:

  1. kernel: KRN-044 rebuild of three objects -- loader_return.o (NAT-119's patch, unchanged), e1s_touch.o (GPIO through the mapped
     bases: NAT-066's abort; staged bring-up `e1stouch_steps`), redwood_input.o (a /dev/hakios-touch node on the same queue for the
     prebuilt libhakios reader; open and first-sample log lines). artifacts/nat-121/kernel-001.
  2. command line: `e1stouch=0` dropped, `e1stouch_steps=2` added (step 1 reads the GPIO state S-Boot left; step 2 switches gpp9[0..3]
     to GPIO and does one STM device-id transfer, no IRQ, no event thread). 255 B < 256.
Loader (NAT-119's no-draw rule), ADT (/product) and md0/md1 are NAT-119's.

    build.py --out artifacts/nat-121/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = PROC.parent.parent

NAME = "loader-diag-xnu-sc7-md1"
NEW_TAG = "nat_attempt=NAT121-sc7"
NEW_TOKENS = ("e1s_wdt_pet=1", "e1s_decon_hw=1", "e1stouch_steps=2")
KERNEL_DIR = ROOT / "artifacts/nat-121/kernel-001"
KERNEL_PATCH = HERE / "loader_return.patch"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b119 = _load("nat121_nat119_build", PROC / "nat-119" / "build.py")
b117, b115, b113 = b119.b117, b119.b115, b119.b113
sha = b115.sha


def append_new():
    return (" loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1sbattery=0 "
            + " ".join(b115.REC_TOKENS + NEW_TOKENS))


def main():
    rec = json.loads((KERNEL_DIR / "rebuild.json").read_text())
    if sorted(e["object"] for e in rec.get("extra_objects", [])) != ["bsd/e1s_touch.o", "bsd/redwood_input.o"]:
        raise SystemExit("kernel-001 is not the three-object rebuild")
    for e in rec["extra_objects"]:
        if sha((ROOT / e["patch"]).read_bytes()) != e["patch_sha256"]:
            raise SystemExit("patch changed since the rebuild: %s" % e["patch"])
    saved = (b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS, b119.KERNEL_DIR, b119.KERNEL_PATCH, b117.append_new)
    b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS = NAME, NEW_TAG, NEW_TOKENS
    b119.KERNEL_DIR, b119.KERNEL_PATCH = KERNEL_DIR, KERNEL_PATCH
    b117.append_new = append_new
    argv_saved = list(sys.argv)
    try:
        b119.main()
    finally:
        sys.argv = argv_saved
        (b119.NAME, b119.NEW_TAG, b119.NEW_TOKENS, b119.KERNEL_DIR, b119.KERNEL_PATCH, b117.append_new) = saved
    if "--check-only" in argv_saved:
        return
    o = b113.argv_value(argv_saved, "--out")
    if o is None:
        return
    path = Path(o) / "build.json"
    d = json.loads(path.read_text())
    cmd = d["payload_fixes"][NAME]["cmdline"].split()
    if "e1stouch=0" in cmd or "e1stouch_steps=2" not in cmd:
        raise SystemExit("cmdline is not NAT-121's: %r" % cmd)
    d["nat121_sources"] = {f: sha((HERE / f).read_bytes()) for f in ("build.py", "loader_return.patch", "e1s_touch.patch", "redwood_input.patch")}
    d["nat121_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "kernel_no_storage_sha256": rec["no_storage_sha256"],
                           "kernel_uuid": rec["uuid"], "extra_objects": rec["extra_objects"], "dropped_tokens": ["e1stouch=0"],
                           "added_tokens": ["e1stouch_steps=2"]}
    path.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
