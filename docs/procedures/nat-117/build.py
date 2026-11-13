#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-117 host build: `loader-diag-xnu-sc5-md1` = NAT-115's image with two changes, applied from outside (NAT-115's build.py and the
chain below it stay as reviewed):

  1. ADT: NAT-085's derivation (pinned e1s.adt + /chosen ephemeral-storage) is replaced, inside the running chain's NAT-085 build
     instance, by make_adt117.derive = the same ADT plus the real D22AP /product node (mkadt.py's rule). NAT-085's build still does the
     one counted ADT swap in the mkpayload call; this wrapper checks that its record names our output hash.
  2. command line: `wait_dump=1` dropped (NAT-116: the dump's printf with interrupts off panicked the kernel at the return). The kernel
     binary is NAT-115's unchanged (the dump code is inert without the boot-arg), so the kernel hash stays cc952151...

Everything else (loader with PX/PR report, md0, delivered md1, loader_return_after=150 with the kernel's watchdog feed, rec_secs=150,
deadline 475 s) is NAT-115's. Image name and tag have NAT-115's lengths.

    build.py --out artifacts/nat-117/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent

NAME = "loader-diag-xnu-sc5-md1"
NEW_TAG = "nat_attempt=NAT117-sc5"
NEW_TOKENS = ("e1s_wdt_pet=1",)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b115 = _load("nat117_nat115_build", PROC / "nat-115" / "build.py")
m117 = _load("nat117_make_adt", HERE / "make_adt117.py")
b113 = b115.b113
b85 = b113.b106.b104.b102.b87.b85   # the NAT-085 build instance the running chain calls (its main does the ADT swap)
sha = b115.sha
STATE = {"derive_calls": 0, "record": None}


def append_new():
    return (" loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 "
            + " ".join(b115.REC_TOKENS + NEW_TOKENS))


def main():
    if len(NEW_TAG) != len(b115.NEW_TAG) or len(NAME) != len(b115.NAME):
        raise SystemExit("image name/tag lengths differ from NAT-115's")
    im4p = m117.IM4P.read_bytes()

    def derive117(pinned_bytes, adt=None, check_pin=True):
        out, rec = m117.derive(pinned_bytes, im4p)
        STATE["derive_calls"] += 1
        STATE["record"] = rec
        return out, rec

    saved = (b115.NAME, b115.NEW_TAG, b115.NEW_TOKENS, b115.APPEND_NEW, b85.m85.derive)
    b115.NAME, b115.NEW_TAG, b115.NEW_TOKENS = NAME, NEW_TAG, NEW_TOKENS
    b115.APPEND_NEW = append_new()
    b85.m85.derive = derive117
    argv_saved = list(sys.argv)
    try:
        b115.main()
    finally:
        sys.argv = argv_saved
        (b115.NAME, b115.NEW_TAG, b115.NEW_TOKENS, b115.APPEND_NEW, b85.m85.derive) = saved

    if "--check-only" in argv_saved:
        return
    o = b113.argv_value(argv_saved, "--out")
    if o is None:
        return
    if STATE["derive_calls"] != 1:
        raise SystemExit("the NAT-117 ADT derivation ran %d times (need exactly 1)" % STATE["derive_calls"])
    path = Path(o) / "build.json"
    d = json.loads(path.read_text())
    adt85 = d.get("nat085_changes", {}).get("adt", {})
    if adt85.get("output_sha256") != STATE["record"]["output_sha256"] or d["nat085_changes"].get("adt_swaps") != 1:
        raise SystemExit("the payload was not built with the NAT-117 ADT (nat085_changes.adt %r)" % adt85.get("output_sha256"))
    cmd = d["payload_fixes"][NAME]["cmdline"]
    if "wait_dump=1" in cmd.split() or "e1s_wdt_pet=1" not in cmd.split() or NEW_TAG not in cmd.split():
        raise SystemExit("cmdline is not the NAT-117 one: %r" % cmd)
    d["nat117_sources"] = {"build.py": sha((HERE / "build.py").read_bytes()), "make_adt117.py": sha((HERE / "make_adt117.py").read_bytes())}
    d["nat117_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "dropped_tokens": ["wait_dump=1"], "adt": STATE["record"],
                           "kernel_no_storage_sha256": d["nat115_changes"]["kernel_no_storage_sha256"]}
    d["nat117_note"] = ("NAT-115's image with the D22AP /product node added to the ADT and wait_dump=1 dropped; same kernel; "
                        "nothing ran on a phone")
    path.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
