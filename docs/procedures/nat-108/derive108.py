#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-108: derive session_nat108.py (session driver for `loader-diag-xnu-sc1-md1`: Stage C1 + hb + fb_diff=1) from NAT-106's session_nat106.py by counted text substitutions (host-only).

    derive108.py            writes docs/procedures/nat-108/session_nat108.py
    derive108.py --check    compares session_nat108.py against the derivation (exit 1 on drift)
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-106/session_nat106.py"
SRC_SHA256 = "e128b053ccb47ad78f36a809a2acc588fcf8ecdda59377651387c6d278d552f1"
OUT = HERE / "session_nat108.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-108" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sb2-md1", "loader-diag-xnu-sc1-md1"
OLD_SHA = "c64bbe0b73b78148b148dbb5e3780e803a2e177ace19635711f86d9f22ebd542"
OLD_PAYLOAD_SHA = "f1edc9b37d70f917d816cc462a5b09aacf152b2a0c7fa6b41ea98b99e8fb97fb"
PAYLOAD_LEN = 26134288


def _doc_old():
    """NAT-106's DOC_NEW: the docstring title carried by session_nat106.py."""
    spec = importlib.util.spec_from_file_location("nat108_derive106", HERE.parent / "nat-106" / "derive106.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = (
    '"""NAT-108 session driver for the NAT-108 image (decision 0019; loader-diag-xnu-sc1-md1: '
    "NAT-106's image with Stage C1 + hb md0 (22 DARWIN_JOBS + `--rest` on-demand plists, `lib/libhakios.sb.dylib`, two-line `etc/inject.conf`, `var/` preference plists, fixed zoneinfo/var.skel) and `fb_diff=1` boot-arg): "
    "one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\n"
    "Derived from docs/procedures/nat-106/session_nat106.py by docs/procedures/nat-108/derive108.py "
    "(counted substitutions; `derive108.py --check`); the execution body below is NAT-106's / NAT-104's / NAT-078's unchanged."
)


def build():
    """-> (new text, list of (what, count)). Raises ValueError when session_nat106.py or package-001 disagrees."""
    data = SRC.read_bytes()
    got_sha = hashlib.sha256(data).hexdigest()
    if got_sha != SRC_SHA256:
        raise ValueError("session_nat106.py sha256 %s != pinned %s" % (got_sha, SRC_SHA256))
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

    sub(_doc_old(), DOC_NEW, 1, "docstring title")
    sub(
        "analyses are analyze_nat106.py (--mode stage-b, hb, stage-a and chain over NAT-106's 8192+524288 return window) (run separately)",
        "analyses are analyze_nat108.py (--mode stage-c, stage-b, hb, stage-a and chain over NAT-108's 8192+524288 return window) (run separately)",
        1,
        "analyser names",
    )
    sub("PACKAGE=ROOT/'artifacts/nat-106/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-108/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat106-%s-single-run-*.md", "*-nat108-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-106/native-attempt-%s-used.json", "artifacts/nat-108/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-104','NAT-105','NAT-106')", "'NAT-104','NAT-105','NAT-106','NAT-107','NAT-108')", 1, "required tasks")
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
            print("session_nat108.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat108.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(
        json.dumps(
            dict(
                out=str(OUT.relative_to(ROOT)),
                sha256=hashlib.sha256(text.encode()).hexdigest(),
                substitutions=[dict(what=w, count=c) for w, c in done],
            ),
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
