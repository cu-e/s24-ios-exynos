#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-108 host build: `loader-diag-xnu-sc1-md1` (Stage C1 + hb + fb_diff=1 + 512 KiB KL return tail).

Builds NAT-106's chain with three Stage C changes only, never opening a phone:
  1. `--ramdisk` defaults to and pins NAT-108's `pid1-sc1-hb/root.apfs` (423 files: NAT-106's
     Stage B + hb base extended with 22 DARWIN_JOBS + `--rest` on-demand LaunchDaemons/LaunchAngels,
     `lib/libhakios.sb.dylib`, two-line `etc/inject.conf`, `var/` preference plists, fixed zoneinfo
     and `etc/var.skel` entries);
  2. Kernel boot-args append ` fb_diff=1` before ` xrd=md0` (`246 < 256` bytes total) so
     `MiniIOMobileFramebuffer` logs changed panel pixel bounding boxes;
  3. Kernel command line tag updates `NAT106-sb2` -> `NAT108-sc1` (same 18-byte `nat_attempt=` field).
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]

NAME = "loader-diag-xnu-sc1-md1"
NEW_TAG = "nat_attempt=NAT108-sc1"
MD0_BYTES = 4194304
MD0_SHA256 = "bb02a20bd9ec5ad87df634adbed93e9936ae24c3c32901ed1369b274850e9725"
FB_DIFF_TOKEN = " fb_diff=1"
BURST_NEW = 4096
TAIL_RETURN_NEW = 524288
RETURN_SETTLE_WAITS = 10


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b106 = _load("nat108_nat106_build", PROC / "nat-106" / "build.py")
b67 = b106.b104.b102.b87.b85.b83.b79.b74.b67
sha = b106.sha
argv_value = b106.argv_value


def cmdline_with_fb_diff(append_text):
    """Append ` fb_diff=1` cleanly to NAT-067's APPEND field if not already present."""
    if "fb_diff=" in append_text:
        raise SystemExit("APPEND already contains fb_diff=: " + append_text)
    return append_text + FB_DIFF_TOKEN


def main():
    argv_saved = list(sys.argv)
    if "--check-only" not in argv_saved and "--ramdisk" not in argv_saved:
        sys.argv += ["--ramdisk", str(ROOT / "artifacts/nat-108/pid1-sc1-hb/root.apfs")]

    saved = (
        b106.NAME,
        b106.NEW_TAG,
        b106.MD0_BYTES,
        b106.MD0_SHA256,
        b106.BURST_NEW,
        b106.TAIL_RETURN_NEW,
        b106.RETURN_SETTLE_WAITS,
        b67.APPEND,
    )
    (
        b106.NAME,
        b106.NEW_TAG,
        b106.MD0_BYTES,
        b106.MD0_SHA256,
        b106.BURST_NEW,
        b106.TAIL_RETURN_NEW,
        b106.RETURN_SETTLE_WAITS,
        b67.APPEND,
    ) = (
        NAME,
        NEW_TAG,
        MD0_BYTES,
        MD0_SHA256,
        BURST_NEW,
        TAIL_RETURN_NEW,
        RETURN_SETTLE_WAITS,
        cmdline_with_fb_diff(saved[7]),
    )
    try:
        b106.main()
    finally:
        (
            b106.NAME,
            b106.NEW_TAG,
            b106.MD0_BYTES,
            b106.MD0_SHA256,
            b106.BURST_NEW,
            b106.TAIL_RETURN_NEW,
            b106.RETURN_SETTLE_WAITS,
            b67.APPEND,
        ) = saved
        sys.argv[:] = argv_saved

    if "--check-only" in argv_saved:
        return
    out = argv_value(argv_saved, "--out")
    if out is None:
        return
    rec = Path(out) / "build.json"
    d = json.loads(rec.read_text())
    d.pop("nat106_sources", None)
    changes = d.pop("nat106_changes", {})
    d.pop("nat106_note", None)
    cmdline = changes.get("cmdline") or ""
    if " fb_diff=1 " not in cmdline or not cmdline.endswith(" xrd=md0") or len(cmdline) >= 256:
        raise SystemExit("unexpected NAT-108 cmdline: %r" % (cmdline,))
    d["nat108_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
    d["nat108_changes"] = {
        "image_name": NAME,
        "cmdline_tag": NEW_TAG,
        "md0_sha256": changes.get("md0_sha256"),
        "md0_bytes": changes.get("md0_bytes"),
        "cmdline": cmdline,
        "cmdline_bytes": len(cmdline),
        "fb_diff": 1,
        "glue62_impl_sha256": changes.get("glue62_impl_sha256"),
        "burst_bytes": BURST_NEW,
        "tail_return_bytes": TAIL_RETURN_NEW,
        "return_settle_waits": RETURN_SETTLE_WAITS,
    }
    d["nat108_note"] = (
        "NAT-106's image updated with Stage C1 + hb md0 (423 files: 22 DARWIN_JOBS + --rest, libhakios.sb.dylib, "
        "var/ preference plists, fixed zoneinfo/var.skel) and `fb_diff=1` boot-arg; nothing ran on a phone"
    )
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
