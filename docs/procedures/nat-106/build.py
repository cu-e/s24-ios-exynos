#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-106 host build: `loader-diag-xnu-sb2-md1` (Stage B + heartbeat + 512 KiB KL return tail).

Builds NAT-104's chain with two changes only, never opening a phone:
  1. `--ramdisk` defaults to and pins NAT-106's `pid1-sb2-hb/root.apfs` (29 files:
     NAT-101's heartbeat loop + NAT-099's `com.apple.backboardd.plist`, `lib/libhakios.dylib`, `etc/inject.conf`);
  2. `glue62_impl.h` keeps NAT-104's `NAT062_BURST=4096u` and `10x N62_WAIT()` on return, and widens
     `NAT062_TAIL_RETURN` from `262144u` to `524288u` (512 KiB, `524288 % 96 = 32 != 0`) so full Stage B
     startup + swap + hb telemetry fits without tail loss;
  3. Kernel command line tag updates `NAT104-hb2` -> `NAT106-sb2` (same length, total 236 bytes < 256).
"""
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]

NAME = "loader-diag-xnu-sb2-md1"
NEW_TAG = "nat_attempt=NAT106-sb2"
MD0_BYTES = 4194304
MD0_SHA256 = "182aead762086a1f322995bd0f05365d7115184d8d775bac3563aa527fa61c56"
BURST_NEW = 4096
TAIL_RETURN_NEW = 524288
RETURN_SETTLE_WAITS = 10


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


b104 = _load("nat106_nat104_build", PROC / "nat-104" / "build.py")
sha = b104.sha
argv_value = b104.argv_value


def _make_patch_rules():
    old_tail = "%du" % b104.TAIL_RETURN_NEW
    new_tail = "%du" % TAIL_RETURN_NEW
    rules = []
    changed = 0
    for label, old, new in b104.PATCH_RULES:
        if label == "tail_return":
            if old_tail not in new:
                raise RuntimeError("expected %s in NAT-104 tail_return rule: %r" % (old_tail, new))
            new = new.replace(old_tail, new_tail)
            changed += 1
        rules.append((label, old, new))
    if changed != 1:
        raise RuntimeError("expected 1 tail_return rule in NAT-104, found %d" % changed)
    return tuple(rules)


PATCH_RULES = _make_patch_rules()


def patch_glue106(path):
    """Apply NAT-106's BURST/TAIL_RETURN=524288u/return-settle patch to `glue62_impl.h` and return its SHA-256."""
    saved = b104.PATCH_RULES
    b104.PATCH_RULES = PATCH_RULES
    try:
        return b104.patch_glue104(path)
    finally:
        b104.PATCH_RULES = saved


def main():
    argv_saved = list(sys.argv)
    saved = (
        b104.NAME,
        b104.NEW_TAG,
        b104.MD0_BYTES,
        b104.MD0_SHA256,
        b104.BURST_NEW,
        b104.TAIL_RETURN_NEW,
        b104.RETURN_SETTLE_WAITS,
        b104.PATCH_RULES,
    )
    (
        b104.NAME,
        b104.NEW_TAG,
        b104.MD0_BYTES,
        b104.MD0_SHA256,
        b104.BURST_NEW,
        b104.TAIL_RETURN_NEW,
        b104.RETURN_SETTLE_WAITS,
        b104.PATCH_RULES,
    ) = (
        NAME,
        NEW_TAG,
        MD0_BYTES,
        MD0_SHA256,
        BURST_NEW,
        TAIL_RETURN_NEW,
        RETURN_SETTLE_WAITS,
        PATCH_RULES,
    )
    try:
        b104.main()
    finally:
        (
            b104.NAME,
            b104.NEW_TAG,
            b104.MD0_BYTES,
            b104.MD0_SHA256,
            b104.BURST_NEW,
            b104.TAIL_RETURN_NEW,
            b104.RETURN_SETTLE_WAITS,
            b104.PATCH_RULES,
        ) = saved

    if "--check-only" in argv_saved:
        return
    out = argv_value(argv_saved, "--out")
    if out is None:
        return
    rec = Path(out) / "build.json"
    d = json.loads(rec.read_text())
    d.pop("nat104_sources", None)
    changes = d.pop("nat104_changes", {})
    d.pop("nat104_note", None)
    d["nat106_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
    d["nat106_changes"] = {
        "image_name": NAME,
        "cmdline_tag": NEW_TAG,
        "md0_sha256": changes.get("md0_sha256"),
        "md0_bytes": changes.get("md0_bytes"),
        "cmdline": changes.get("cmdline"),
        "glue62_impl_sha256": changes.get("glue62_impl_sha256"),
        "burst_bytes": BURST_NEW,
        "tail_return_bytes": TAIL_RETURN_NEW,
        "return_settle_waits": RETURN_SETTLE_WAITS,
    }
    d["nat106_note"] = (
        "NAT-104's image updated with Stage B + hb md0 (29 files: pid1-hb + backboardd plist + libhakios.dylib + etc/inject.conf) "
        "and TAIL_RETURN=524288 (512 KiB); nothing ran on a phone"
    )
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
