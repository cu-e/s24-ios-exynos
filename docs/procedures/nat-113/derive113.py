#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-113: derive session_nat113.py (session driver for `loader-diag-xnu-sc3-md1`) from NAT-110's session_nat110.py by counted
text substitutions (host-only). The execution body (write, readback, watcher, collector, delivery companion, one reboot, restore
mode) is NAT-110's unchanged; only the image identity, the package path, the decision glob, the one-shot marker and the list of
tasks that must be done change.

    derive113.py            writes docs/procedures/nat-113/session_nat113.py
    derive113.py --check    compares session_nat113.py against the derivation (exit 1 on drift)
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-110/session_nat110.py"
SRC_SHA256 = "8f1d029839ac4402c8a534e8272edcce660855fd1329c06ebea1e4d56d898676"
OUT = HERE / "session_nat113.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-113" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sc2-md1", "loader-diag-xnu-sc3-md1"
OLD_SHA = "3e0c594060a58e4045ef6dee417931d8e79ed8fb139de38b5cb18d1294788258"
OLD_PAYLOAD_SHA = "31a9f150ba75d967fa074a320998ba6b88986c952ade1ff002ac718bf44a02c6"
OLD_PAYLOAD_LEN = 26134288     # NAT-110's Image.payload
PAYLOAD_LEN = 26138384         # NAT-113's: the loader grew by one 4 KiB page (glue113.h)
DOC_OLD = (
    '"""NAT-110 session driver for the NAT-110 image (decision 0019; loader-diag-xnu-sc2-md1: '
    "NAT-106's image updated with Stage C2 + hb md0 (396 files: `etc/quiet`, 377 LaunchDaemons after pruning `com.nat085.ps` + 27 non-UI plists), "
    "`fb_diff=1`, `loader_return_after=63`, `deadline_s=365`): "
)
DOC_NEW = (
    '"""NAT-113 session driver for the NAT-113 image (decision 0019; loader-diag-xnu-sc3-md1: '
    "NAT-110's image (same md0) with the loader's PX/PR pixel report at the kernel's return and `rec_secs=30 rec_mb=64`, "
    "`loader_return_after=63`, `deadline_s=390`; derived from session_nat110.py by derive113.py): "
)


def build():
    """-> (new text, list of (what, count)). Raises ValueError when session_nat110.py or package-001 disagrees."""
    data = SRC.read_bytes()
    got_sha = hashlib.sha256(data).hexdigest()
    if got_sha != SRC_SHA256:
        raise ValueError("session_nat110.py sha256 %s != pinned %s" % (got_sha, SRC_SHA256))
    pkg = json.loads((PACKAGE / "package.json").read_text())
    img = pkg["images"][IMAGE_NEW]
    if img["payload_bytes"] != PAYLOAD_LEN:
        raise ValueError("payload_bytes of %s is %d, expected %d" % (IMAGE_NEW, img["payload_bytes"], PAYLOAD_LEN))
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
    sub("the analyses are analyze_nat110.py", "the analyses are analyze_nat110.py plus decode113.py", 1, "analyser names")
    sub("PACKAGE=ROOT/'artifacts/nat-110/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-113/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=%d," % OLD_PAYLOAD_LEN, "CANARY_LEN=%d," % PAYLOAD_LEN, 1, "Image.payload length")
    sub("*-nat110-%s-single-run-*.md", "*-nat113-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-110/native-attempt-%s-used.json", "artifacts/nat-113/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-108','NAT-109','NAT-110')", "'NAT-108','NAT-109','NAT-110','NAT-111','NAT-112')", 1, "required tasks")
    return text, done


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    try:
        text, done = build()
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    if "--check" in argv:
        have = OUT.read_text() if OUT.exists() else None
        if have != text:
            print("session_nat113.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat113.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), substitutions=done,
                          sha256=hashlib.sha256(text.encode()).hexdigest()), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
