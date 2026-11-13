#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-119: derive session_nat121.py (session driver for `loader-diag-xnu-sc6-md1`, run as NAT-120) from NAT-117's session_nat121.py
by counted text substitutions (host-only). The execution body (write, readback, watcher, collector, delivery companion, one reboot,
restore mode) is NAT-115's unchanged; only the image identity, the package path, the decision glob, the one-shot marker and the
list of tasks that must be done change.

    derive121.py            writes docs/procedures/nat-117/session_nat121.py
    derive121.py --check    compares session_nat121.py against the derivation (exit 1 on drift)
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-119/session_nat119.py"
SRC_SHA256 = "53af082d56d85d3bb2edc43757bb4ceab6222f6e4286916334deec6278bf5858"
OUT = HERE / "session_nat121.py"
PACKAGE = ROOT / "artifacts/nat-121/package-001"
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sc6-md1", "loader-diag-xnu-sc7-md1"
OLD_SHA = "e430d54e302e4a4e3251022fe65ae026429ebf90e22c4c6704d2e1ead170b6ac"
OLD_PAYLOAD_SHA = "4175a7ff5aacdf48e561dd292e2ec685c5bc4e553fd1cc724a380c1b140620d1"
OLD_PAYLOAD_LEN = 26141568
DOC_OLD = ("NAT-120 session driver for the NAT-119 image (decisions 0019/0044; loader-diag-xnu-sc6-md1: NAT-117's image with the "
           "kernel's DECON0 HW-form kick (e1s_decon_hw=1) and no loader marker drawing after the kernel's return, "
           "`loader_return_after=150`, `rec_secs=150`, `deadline_s=475`; derived from session_nat117.py by derive119.py)")
DOC_NEW = ("NAT-122 session driver for the NAT-121 image (decisions 0019/0044; loader-diag-xnu-sc7-md1: NAT-119's image with the "
           "fixed e1s touch driver at e1stouch_steps=2 and /dev/hakios-touch, "
           "`loader_return_after=150`, `rec_secs=150`, `deadline_s=475`; derived from session_nat119.py by derive121.py)")


def build():
    data = SRC.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != SRC_SHA256:
        raise ValueError("session_nat119.py sha256 %s != pinned %s" % (got, SRC_SHA256))
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
    sub("PACKAGE=ROOT/'artifacts/nat-119/package-001'", "PACKAGE=ROOT/'artifacts/nat-121/package-001'", 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=%d," % OLD_PAYLOAD_LEN, "CANARY_LEN=%d," % img["payload_bytes"], 1, "Image.payload length")
    sub("*-nat120-%s-single-run-*.md", "*-nat122-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-120/native-attempt-%s-used.json", "artifacts/nat-122/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-118','NAT-119')", "'NAT-118','NAT-119','NAT-120','NAT-121')", 1, "required tasks")
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
            print("session_nat121.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat121.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), substitutions=done, sha256=hashlib.sha256(text.encode()).hexdigest()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
