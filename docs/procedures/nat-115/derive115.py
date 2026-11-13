#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-115: derive session_nat115.py (session driver for `loader-diag-xnu-sc4-md1`) from NAT-113's session_nat113.py by counted
text substitutions (host-only). The execution body (write, readback, watcher, collector, delivery companion, one reboot, restore
mode) is NAT-113's unchanged (which is NAT-110's); only the image identity, the package path, the decision glob, the one-shot
marker and the list of tasks that must be done change.

    derive115.py            writes docs/procedures/nat-115/session_nat115.py
    derive115.py --check    compares session_nat115.py against the derivation (exit 1 on drift)
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-113/session_nat113.py"
SRC_SHA256 = "bb4aaf7826a081de0a4732033d5a3b72ecae9f7d3aa081a42802aa29001abc73"
OUT = HERE / "session_nat115.py"
PACKAGE = ROOT / "artifacts/nat-115/package-001"
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sc3-md1", "loader-diag-xnu-sc4-md1"
OLD_SHA = "aedbf05f6ea72f8bd20b3ccbb8e6fa018194a224274bee607872a1ccd8ff5880"
OLD_PAYLOAD_SHA = "2c3624a1c26f38b7de8a6573e2efe28e9b06f73aeaec6261fb81c8a7f98d97e0"
OLD_PAYLOAD_LEN = 26138384
DOC_OLD = ("NAT-113 session driver for the NAT-113 image (decision 0019; loader-diag-xnu-sc3-md1: NAT-110's image (same md0) with "
           "the loader's PX/PR pixel report at the kernel's return and `rec_secs=30 rec_mb=64`, `loader_return_after=63`, "
           "`deadline_s=390`; derived from session_nat110.py by derive113.py)")
DOC_NEW = ("NAT-116 session driver for the NAT-115 image (decision 0019; loader-diag-xnu-sc4-md1: NAT-113's image with the "
           "KRN-044-rebuilt kernel (NAT-071 watchdog feed + wait dump), `loader_return_after=150`, `rec_secs=150`, "
           "`deadline_s=475`; derived from session_nat113.py by derive115.py)")


def build():
    data = SRC.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != SRC_SHA256:
        raise ValueError("session_nat113.py sha256 %s != pinned %s" % (got, SRC_SHA256))
    img = json.loads((PACKAGE / "package.json").read_text())["images"][IMAGE_NEW]
    text = data.decode()
    done = []

    def sub(old, new, want, what):
        nonlocal text
        n = text.count(old)
        if n != want:
            raise ValueError("%s: expected %d occurrence(s) of %r, found %d" % (what, want, old, n))
        text = text.replace(old, new)
        done.append((what, n))

    sub(DOC_OLD, DOC_NEW, 1, "docstring title")
    sub("PACKAGE=ROOT/'artifacts/nat-113/package-001'", "PACKAGE=ROOT/'artifacts/nat-115/package-001'", 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=%d," % OLD_PAYLOAD_LEN, "CANARY_LEN=%d," % img["payload_bytes"], 1, "Image.payload length")
    sub("*-nat113-%s-single-run-*.md", "*-nat116-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-113/native-attempt-%s-used.json", "artifacts/nat-116/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-110','NAT-111','NAT-112')", "'NAT-110','NAT-111','NAT-112','NAT-113','NAT-114','KRN-044','NAT-071')", 1, "required tasks")
    return text, done


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        text, done = build()
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    if "--check" in argv:
        if (OUT.read_text() if OUT.exists() else None) != text:
            print("session_nat115.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat115.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), substitutions=done, sha256=hashlib.sha256(text.encode()).hexdigest()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
