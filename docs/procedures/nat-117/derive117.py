#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-117: derive session_nat117.py (session driver for `loader-diag-xnu-sc5-md1`, run as NAT-118) from NAT-115's session_nat115.py
by counted text substitutions (host-only). The execution body (write, readback, watcher, collector, delivery companion, one reboot,
restore mode) is NAT-115's unchanged; only the image identity, the package path, the decision glob, the one-shot marker and the
list of tasks that must be done change.

    derive117.py            writes docs/procedures/nat-117/session_nat117.py
    derive117.py --check    compares session_nat117.py against the derivation (exit 1 on drift)
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-115/session_nat115.py"
SRC_SHA256 = "96359419d3d0a1e4ba89759aabeb40abf4ad01313e99bc2d9964ff245878fe16"
OUT = HERE / "session_nat117.py"
PACKAGE = ROOT / "artifacts/nat-117/package-001"
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sc4-md1", "loader-diag-xnu-sc5-md1"
OLD_SHA = "c0642059a4ba21e1205461bedc1b448952779b27f841b750211eb1b3c3d553f9"
OLD_PAYLOAD_SHA = "85c2989b3ef7d5ba4774894c3bde0f2039ef61acfe4056a097890afc02582dc1"
OLD_PAYLOAD_LEN = 26138512
DOC_OLD = ("NAT-116 session driver for the NAT-115 image (decision 0019; loader-diag-xnu-sc4-md1: NAT-113's image with the "
           "KRN-044-rebuilt kernel (NAT-071 watchdog feed + wait dump), `loader_return_after=150`, `rec_secs=150`, "
           "`deadline_s=475`; derived from session_nat113.py by derive115.py)")
DOC_NEW = ("NAT-118 session driver for the NAT-117 image (decisions 0019/0044; loader-diag-xnu-sc5-md1: NAT-115's image with the "
           "D22AP /product node in the ADT and wait_dump off, same kernel, `loader_return_after=150`, `rec_secs=150`, "
           "`deadline_s=475`; derived from session_nat115.py by derive117.py)")


def build():
    data = SRC.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    if got != SRC_SHA256:
        raise ValueError("session_nat115.py sha256 %s != pinned %s" % (got, SRC_SHA256))
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
    sub("PACKAGE=ROOT/'artifacts/nat-115/package-001'", "PACKAGE=ROOT/'artifacts/nat-117/package-001'", 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=%d," % OLD_PAYLOAD_LEN, "CANARY_LEN=%d," % img["payload_bytes"], 1, "Image.payload length")
    sub("*-nat116-%s-single-run-*.md", "*-nat118-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-116/native-attempt-%s-used.json", "artifacts/nat-118/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'KRN-044','NAT-071')", "'KRN-044','NAT-071','NAT-115','NAT-116','NAT-117')", 1, "required tasks")
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
            print("session_nat117.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat117.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), substitutions=done, sha256=hashlib.sha256(text.encode()).hexdigest()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
