#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-062: build loader-diag-xnu-run-usb on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source [--deadline-s 60] [--service-tenths 3]
  build.py --check-only --loader-source COPY_OF_...

This is NAT-059's build (docs/procedures/nat-059/build.py: NAT-052's build plus patch_ckpt59.py, the stops 17..21) with three differences:
the image name `loader-diag-xnu-run-usb`; patch_run62.py over the derived tree after NAT-059's own patch (the dump of the kernel's log at the last
stop and at the kernel's own return, and a resume after the last stop); and one byte-range patch of the payload (after NAT-022's ADT-size fix):
the kernel command line field gets `nat_attempt=NAT062-run` in place of `nat_attempt=NAT020-83s` (same length) and `loader_return_after=8`
appended, so the kernel hands control back by itself 8 seconds after its startup tasks have run, if its timers work.

Output: DIR/loader-diag-xnu-run-usb/{Image,Image.payload,loader.elf,source/} and DIR/build.json."""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-run-usb"

CMDLINE_OFF = 0x48
CMDLINE_LEN = 608
OLD_TAG = b"nat_attempt=NAT020-83s"
NEW_TAG = b"nat_attempt=NAT062-run"
APPEND = b" loader_return_after=8"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def sha(b):
    return hashlib.sha256(b).hexdigest()


def patch_cmdline(data):
    """-> (new bytes, info). Only the NUL-padded command-line field changes; it must be the field NAT-029 describes."""
    d = bytearray(data)
    if d[:8] != b"SWEETXNU":
        raise SystemExit("not a SWEETXNU payload")
    field = bytes(d[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN])
    text = field.rstrip(b"\0")
    if b"\0" in text or field[len(text):] != b"\0" * (CMDLINE_LEN - len(text)):
        raise SystemExit("the command-line field is not one NUL-padded string")
    if text.count(OLD_TAG) != 1 or b"loader_return_after" in text:
        raise SystemExit("the command line is not the NAT-020 one this patch expects")
    new = text.replace(OLD_TAG, NEW_TAG) + APPEND
    if len(new) >= 256:
        raise SystemExit("the kernel's BOOT_LINE_LENGTH is 256: the command line would be cut")
    d[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN] = new + b"\0" * (CMDLINE_LEN - len(new))
    return bytes(d), {"field": "kernel command line", "payload_offset": CMDLINE_OFF, "length": CMDLINE_LEN,
                      "old": text.decode(), "new": new.decode(), "base_sha256": sha(data), "fixed_sha256": sha(bytes(d))}


b59 = _load("nat059_build", PROC / "nat-059" / "build.py")
b52 = b59.b52
_prepare_tree59 = b59.prepare_tree
_fix_payload22 = b52.b22._fix_payload


def prepare_tree(src, deadline_s, final=True):
    """NAT-059's prepare_tree, then patch_run62.py over its ckpt3.c / markerlib52.c (final=True only)."""
    wdt = _prepare_tree59(src, deadline_s, final)
    if final:
        b52.b22.run([sys.executable, "-I", HERE / "patch_run62.py", src])
    return wdt


def _fix_payload62():
    fix = _fix_payload22()

    def fix62(data):
        d, info = fix(data)
        d2, info2 = patch_cmdline(d)
        info = dict(info)
        info["cmdline_patch"] = info2
        info["fixed_sha256"] = info2["fixed_sha256"]
        return d2, info
    return fix62


def main():
    b59.NAME = NAME
    b59.prepare_tree = prepare_tree
    b52.b22._fix_payload = _fix_payload62
    b59.main()
    argv = sys.argv
    if "--out" in argv and "--check-only" not in argv:
        rec = Path(argv[argv.index("--out") + 1]) / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            d["nat062_sources"] = {f: sha((HERE / f).read_bytes()) for f in ("patch_run62.py", "build.py")}
            d["nat062_sources"].update({f: sha((HERE / "src" / f).read_bytes()) for f in ("glue62.h", "glue62_impl.h")})
            d["nat062_note"] = ("the NAT-059/052/036 hashes above are of the unpatched sources; patch_run62.py rewrites ckpt3.c and markerlib52.c "
                                "in the derived tree and copies glue62.h, glue62_impl.h; the payload's command line is changed by build.py")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
