#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-119 host build: `loader-diag-xnu-sc6-md1` = NAT-117's image (D22AP /product ADT, wait_dump off) with two changes, applied
from outside (NAT-117/115/113 builds unchanged):

  1. kernel: KRN-044 rebuild of loader_return.c with docs/procedures/nat-119/kernel-combined.patch = NAT-115's patch + the DECON0
     HW-form kick (boot-arg e1s_decon_hw=1: once at the start of the timed window and on every 10 s heartbeat; writes only TRIG_CON
     and SHD_REG_UP_REQ, only while GLOBAL_CON reads enabled + command mode; prints TRIG_CON and FRAME_COUNT per kick).
     NAT-115's kernel swap is reused by pointing its KERNEL_DIR/KERNEL_PATCH at artifacts/nat-119/kernel-001.
  2. loader: after the kernel's own return (why=2) the loader no longer draws its marker bands into 0xfa200000 (they covered panel
     rows 0-2063 in NAT-118 and hid the iOS picture: owner observation), while its DECON kicks continue so the panel keeps showing
     the iOS frame left in the buffer. Two counted exact-match rules: a flag tested at the top of mk_draw (markerlib.c) and set in
     nat062_dump_log right before the pixel report (glue62_impl.h).

    build.py --out artifacts/nat-119/build-001 --loader-source artifacts/nat-020/build-003/source --ramdisk artifacts/nat-110/pid1-sc2-hb/root.apfs
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = PROC.parent.parent

NAME = "loader-diag-xnu-sc6-md1"
NEW_TAG = "nat_attempt=NAT119-sc6"
NEW_TOKENS = ("e1s_wdt_pet=1", "e1s_decon_hw=1")
KERNEL_DIR = ROOT / "artifacts/nat-119/kernel-001"
KERNEL_PATCH = HERE / "kernel-combined.patch"

LOADER_RULES = (
    ("markerlib.c", "draw_flag",
     "static inline void mk_draw(uint32_t frame, uint32_t prev, int full)\n{\n",
     "static int nat119_no_draw;\t/* NAT-119: set at the kernel's own return; the iOS picture stays in the buffer */\n"
     "static inline void mk_draw(uint32_t frame, uint32_t prev, int full)\n{\n\tif (nat119_no_draw)\n\t\treturn;\n"),
    ("glue62_impl.h", "set_flag",
     "\t\tnat113_pixels(pa_minus_va);\n",
     "\t\tnat119_no_draw = 1;\n\t\tnat113_pixels(pa_minus_va);\n"),
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b117 = _load("nat119_nat117_build", PROC / "nat-117" / "build.py")
b115 = b117.b115
b113 = b115.b113
b104 = b113.b106.b104
sha = b115.sha
STATE = {"loader_rules": {}}


def patch_loader(shim_dir):
    for fname, label, old, new in LOADER_RULES:
        p = Path(shim_dir) / fname
        text = p.read_text()
        n = text.count(old)
        if n != 1:
            raise SystemExit("NAT-119 rule %s: expected 1 occurrence in %s, found %d" % (label, p, n))
        p.write_text(text.replace(old, new))
        STATE["loader_rules"][label] = sha(p.read_bytes())


def main():
    if len(NAME) != len(b117.NAME) or len(NEW_TAG) != len(b117.NEW_TAG):
        raise SystemExit("image name/tag lengths differ from NAT-117's")
    saved = (b117.NAME, b117.NEW_TAG, b117.NEW_TOKENS, b115.KERNEL_DIR, b115.KERNEL_PATCH, b104.patch_glue104)
    orig_patch = b104.patch_glue104

    def patch_glue119(path):
        orig_patch(path)                    # NAT-104/106/113 rules (glue113.h include and the pixel call) first
        patch_loader(Path(path).parent)
        return sha(Path(path).read_bytes())

    b117.NAME, b117.NEW_TAG, b117.NEW_TOKENS = NAME, NEW_TAG, NEW_TOKENS
    b115.KERNEL_DIR, b115.KERNEL_PATCH = KERNEL_DIR, KERNEL_PATCH
    b104.patch_glue104 = patch_glue119
    argv_saved = list(sys.argv)
    try:
        b117.main()
    finally:
        sys.argv = argv_saved
        (b117.NAME, b117.NEW_TAG, b117.NEW_TOKENS, b115.KERNEL_DIR, b115.KERNEL_PATCH, b104.patch_glue104) = saved

    if "--check-only" in argv_saved:
        return
    o = b113.argv_value(argv_saved, "--out")
    if o is None:
        return
    if sorted(STATE["loader_rules"]) != ["draw_flag", "set_flag"]:
        raise SystemExit("loader rules applied: %r" % STATE["loader_rules"])
    path = Path(o) / "build.json"
    d = json.loads(path.read_text())
    cmd = d["payload_fixes"][NAME]["cmdline"]
    for t in NEW_TOKENS + (NEW_TAG,):
        if t not in cmd.split():
            raise SystemExit("cmdline lacks %s: %r" % (t, cmd))
    rec = json.loads((KERNEL_DIR / "rebuild.json").read_text())
    d["nat119_sources"] = {"build.py": sha((HERE / "build.py").read_bytes()), "kernel-combined.patch": sha(KERNEL_PATCH.read_bytes())}
    d["nat119_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "added_tokens": ["e1s_decon_hw=1"],
                           "kernel_no_storage_sha256": rec["no_storage_sha256"], "kernel_uuid": rec["uuid"],
                           "loader_rules": STATE["loader_rules"], "cmdline_bytes": len(cmd.encode())}
    d["nat119_note"] = ("NAT-117's image + kernel DECON0 HW-form kick (e1s_decon_hw=1) + no loader marker drawing after the kernel's "
                        "return; nothing ran on a phone")
    path.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
