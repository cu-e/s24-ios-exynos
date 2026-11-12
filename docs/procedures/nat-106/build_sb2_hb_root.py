#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-106 Stage B + heartbeat small root builder (host-only).

Combines NAT-101's heartbeat-enabled small root (`artifacts/nat-101/pid1-hb`, 26 files:
Stage A jobs + `/redwood/bin/hb` + `/etc/rc` loop) with NAT-099's three Stage B files
(`LaunchDaemons/com.apple.backboardd.plist`, `lib/libhakios.dylib`, `etc/inject.conf`)
by wrapping `docs/procedures/nat-099/build_stage_b_root.py` over the pinned NAT-101 base.

Nothing runs on a phone. Output defaults to `artifacts/nat-106/pid1-sb2-hb`.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

HB_BASE_ROOT_APFS_SHA256 = "97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c"
HB_BASE_FILE_COUNT = 26
EXPECTED_FILES = 29


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


B99 = _load("nat106_b99", HERE.parent / "nat-099" / "build_stage_b_root.py")
BuildError = B99.BuildError


def build(out, base, recipe, dylib):
    """Build Stage B + heartbeat small root APFS image on top of pinned NAT-101 pid1-hb."""
    out, base, recipe, dylib = Path(out), Path(base), Path(recipe), Path(dylib)
    saved = (B99.BASE_ROOT_APFS_SHA256, B99.BASE_FILE_COUNT)
    B99.BASE_ROOT_APFS_SHA256 = HB_BASE_ROOT_APFS_SHA256
    B99.BASE_FILE_COUNT = HB_BASE_FILE_COUNT
    try:
        rec = B99.build(out, base, recipe, dylib)
    finally:
        B99.BASE_ROOT_APFS_SHA256, B99.BASE_FILE_COUNT = saved

    root = out / "root"
    B99.need(rec["files"] == EXPECTED_FILES, "expected %d files in Stage B + hb tree, got %d" % (EXPECTED_FILES, rec["files"]))
    B99.need((root / "bin/hb").is_file(), "bin/hb missing from Stage B + hb root")
    B99.need(b"/redwood/bin/hb" in (root / "etc/rc").read_bytes(), "etc/rc missing /redwood/bin/hb loop")

    rec["nat106_stage_b_hb"] = {
        "kind": "host build record, nothing ran on a phone",
        "hb_base": "artifacts/nat-101/pid1-hb",
        "hb_base_root_apfs_sha256": HB_BASE_ROOT_APFS_SHA256,
        "hb_base_files": HB_BASE_FILE_COUNT,
        "stage_b_donor": "docs/procedures/nat-099/build_stage_b_root.py",
        "added_files": list(B99.ADDED),
        "total_files": rec["files"],
        "script_sha256": B99.sha256_file(Path(__file__)),
    }
    (out / "build.json").write_text((json.dumps(rec, indent=1, sort_keys=True) + "\n").replace(str(ROOT) + "/", ""))
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "artifacts/nat-106/pid1-sb2-hb")
    ap.add_argument("--base", type=Path, default=ROOT / "artifacts/nat-101/pid1-hb")
    ap.add_argument("--recipe", type=Path, default=ROOT / "artifacts/ios-root/recipe")
    ap.add_argument("--dylib", type=Path, default=ROOT / "references/hakios/prebuilt/userland/libhakios.dylib")
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.base, a.recipe, a.dylib)
    except BuildError as e:
        raise SystemExit("build_sb2_hb_root: " + str(e))
    print(
        json.dumps(
            {
                "root_apfs": rec["root_apfs"],
                "files": rec["files"],
                "kernel_readback_ok": not rec["kernel_apfs_lib_readback"]["mismatches"],
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
