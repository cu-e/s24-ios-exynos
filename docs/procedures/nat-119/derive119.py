#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-119: derive session_nat119.py (session driver for `loader-diag-xnu-sc6-md1`, run as NAT-120) from NAT-117's session_nat119.py
by counted text substitutions (host-only). The execution body (write, readback, watcher, collector, delivery companion, one reboot,
restore mode) is NAT-115's unchanged; only the image identity, the package path, the decision glob, the one-shot marker and the
list of tasks that must be done change.

    derive119.py            writes docs/procedures/nat-117/session_nat119.py
    derive119.py --check    compares session_nat119.py against the derivation (exit 1 on drift)
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-117/session_nat117.py"
SRC_SHA256 = "d4050c26ab2cbbece2855f52c47b6ec0ec5550011a7467bbf138d31d8bd1fdd4"
OUT = HERE / "session_nat119.py"
PACKAGE = ROOT / "artifacts/nat-119/package-001"
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sc5-md1", "loader-diag-xnu-sc6-md1"
OLD_SHA = "9696818ff9ccc3f38276a7196a8a934085da8860758e8ef25788a0bc581b0536"
OLD_PAYLOAD_SHA = "81b33e6de389b122e0e252d64d0cb221c3f6c5d3c4270a88472cc2cb298fd5c7"
OLD_PAYLOAD_LEN = 26141200
DOC_OLD = ("NAT-118 session driver for the NAT-117 image (decisions 0019/0044; loader-diag-xnu-sc5-md1: NAT-115's image with the "
           "D22AP /product node in the ADT and wait_dump off, same kernel, `loader_return_after=150`, `rec_secs=150`, "
           "`deadline_s=475`; derived from session_nat115.py by derive117.py)")
DOC_NEW = ("NAT-120 session driver for the NAT-119 image (decisions 0019/0044; loader-diag-xnu-sc6-md1: NAT-117's image with the "
           "kernel's DECON0 HW-form kick (e1s_decon_hw=1) and no loader marker drawing after the kernel's return, "
           "`loader_return_after=150`, `rec_secs=150`, `deadline_s=475`; derived from session_nat117.py by derive119.py)")


def build():
    data = SRC.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != SRC_SHA256:
        raise ValueError("session_nat117.py sha256 %s != pinned %s" % (got, SRC_SHA256))
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
    sub("PACKAGE=ROOT/'artifacts/nat-117/package-001'", "PACKAGE=ROOT/'artifacts/nat-119/package-001'", 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=%d," % OLD_PAYLOAD_LEN, "CANARY_LEN=%d," % img["payload_bytes"], 1, "Image.payload length")
    sub("*-nat118-%s-single-run-*.md", "*-nat120-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-118/native-attempt-%s-used.json", "artifacts/nat-120/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-116','NAT-117')", "'NAT-116','NAT-117','NAT-118','NAT-119')", 1, "required tasks")
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
            print("session_nat119.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat119.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), substitutions=done, sha256=hashlib.sha256(text.encode()).hexdigest()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
