#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-110 host build: `loader-diag-xnu-sc2-md1` (Stage C2 + heartbeat + quiet launchd + pruned daemons).

Builds NAT-106's chain on the host without opening a phone or modifying earlier procedures:
  1. `--ramdisk` pins NAT-110's `pid1-sc2-hb/root.apfs` (`396` files: NAT-108 `pid1-sc1-hb` + empty `etc/quiet`
     to suppress synchronous console launchd chatter - `280 KB` / `2,086` lines in NAT-109 - and minus
     `com.nat085.ps.plist` plus `27` non-UI wireless/cloud/telemetry plists);
  2. `glue62_impl.h` keeps NAT-106's `BURST=4096u`, `TAIL_RETURN=524288u` (512 KiB), and `10x` settle waits;
  3. Kernel cmdline updates tag `NAT110-sc2`, keeps `fb_diff=1`, sets `loader_return_after=63` (`83 s WDT - 20 s`
     maximum bounded kernel window, 2 digits -> `246 B < 256 B`), and raises `--deadline-s` to `365`
     (`>= rx_cap 240 + return_after 63 + work_margin 60 = 363`).
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent

NAME = "loader-diag-xnu-sc2-md1"
NEW_TAG = "nat_attempt=NAT110-sc2"
MD0_BYTES = 4194304
MD0_SHA256 = "6e9bdcef4ed6d4cd592ae004f1ec84013326242472be6f27074d5364a495583c"
BURST_NEW = 4096
TAIL_RETURN_NEW = 524288
RETURN_SETTLE_WAITS = 10
RETURN_AFTER_NEW = 63
DEADLINE_NEW = 365
FB_DIFF_TOKEN = " fb_diff=1"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b106 = _load("nat110_nat106_build", PROC / "nat-106" / "build.py")
b67 = b106.b104.b102.b87.b85.b79.b67
sha = b106.sha
argv_value = b106.argv_value


def cmdline_with_fb_diff(append_text):
    """Append ` fb_diff=1` cleanly to NAT-067's APPEND field if not already present."""
    if "fb_diff=" in append_text:
        raise SystemExit("APPEND already contains fb_diff=: " + append_text)
    return append_text + FB_DIFF_TOKEN


def with_default_timings(argv):
    """Ensure `--return-after-s 63` and `--deadline-s 365` are present when omitted from `argv`."""
    out = list(argv)
    if "--return-after-s" not in out:
        out += ["--return-after-s", str(RETURN_AFTER_NEW)]
    if "--deadline-s" not in out:
        out += ["--deadline-s", str(DEADLINE_NEW)]
    return out


def main():
    """Build `loader-diag-xnu-sc2-md1` by driving NAT-106's chain with Stage C2 md0 and cmdline overrides."""
    argv_saved = list(sys.argv)
    sys.argv = with_default_timings(argv_saved)
    saved_b106 = (
        b106.NAME,
        b106.NEW_TAG,
        b106.MD0_BYTES,
        b106.MD0_SHA256,
        b106.BURST_NEW,
        b106.TAIL_RETURN_NEW,
        b106.RETURN_SETTLE_WAITS,
    )
    saved_append = b67.APPEND
    (
        b106.NAME,
        b106.NEW_TAG,
        b106.MD0_BYTES,
        b106.MD0_SHA256,
        b106.BURST_NEW,
        b106.TAIL_RETURN_NEW,
        b106.RETURN_SETTLE_WAITS,
    ) = (
        NAME,
        NEW_TAG,
        MD0_BYTES,
        MD0_SHA256,
        BURST_NEW,
        TAIL_RETURN_NEW,
        RETURN_SETTLE_WAITS,
    )
    b67.APPEND = cmdline_with_fb_diff(saved_append)
    try:
        b106.main()
    finally:
        sys.argv = argv_saved
        b67.APPEND = saved_append
        (
            b106.NAME,
            b106.NEW_TAG,
            b106.MD0_BYTES,
            b106.MD0_SHA256,
            b106.BURST_NEW,
            b106.TAIL_RETURN_NEW,
            b106.RETURN_SETTLE_WAITS,
        ) = saved_b106

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
    tokens = cmdline.split()
    if "fb_diff=1" not in tokens:
        raise SystemExit("build.json cmdline missing fb_diff=1: %r" % (cmdline,))
    if ("loader_return_after=%d" % RETURN_AFTER_NEW) not in tokens:
        raise SystemExit("build.json cmdline missing loader_return_after=%d: %r" % (RETURN_AFTER_NEW, cmdline))
    if len(cmdline.encode()) >= 256:
        raise SystemExit("build.json cmdline exceeds 255 bytes (%d): %r" % (len(cmdline.encode()), cmdline))

    d["nat110_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
    d["nat110_changes"] = {
        "image_name": NAME,
        "cmdline_tag": NEW_TAG,
        "md0_sha256": changes.get("md0_sha256"),
        "md0_bytes": changes.get("md0_bytes"),
        "cmdline": cmdline,
        "cmdline_bytes": len(cmdline.encode()),
        "fb_diff": 1,
        "return_after_s": RETURN_AFTER_NEW,
        "deadline_s": DEADLINE_NEW,
        "glue62_impl_sha256": changes.get("glue62_impl_sha256"),
        "burst_bytes": BURST_NEW,
        "tail_return_bytes": TAIL_RETURN_NEW,
        "return_settle_waits": RETURN_SETTLE_WAITS,
    }
    d["nat110_note"] = (
        "NAT-106's image updated with Stage C2 + hb md0 (396 files: etc/quiet + 377 LaunchDaemons), "
        "fb_diff=1, loader_return_after=63, and deadline_s=365; nothing ran on a phone"
    )
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
