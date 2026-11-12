#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-106: derive session_nat106.py (session driver for `loader-diag-xnu-sb2-md1`: Stage B + hb + 512 KiB KL tail) from NAT-104's session_nat104.py by counted text substitutions (host-only).

    derive106.py            writes docs/procedures/nat-106/session_nat106.py
    derive106.py --check    compares session_nat106.py against the derivation (exit 1 on drift)
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-104/session_nat104.py"
SRC_SHA256 = "fcb5b383f2c9ded4431317a9d5ab773f5ed362eec937789570fc0b77cf68b6c8"
OUT = HERE / "session_nat106.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-106" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-hb2-md1", "loader-diag-xnu-sb2-md1"
OLD_SHA = "540b64a5736d444bdf8c0f09a6897c0469b3fb36332dce87f3ff626377bb1963"
OLD_PAYLOAD_SHA = "4161da474ddb1c708d8b2674111d8f6e6286a697888a999b6d1fee5963d3d1b7"
PAYLOAD_LEN = 26134288


def _doc_old():
    """NAT-104's DOC_NEW: the docstring title carried by session_nat104.py."""
    spec = importlib.util.spec_from_file_location("nat106_derive104", HERE.parent / "nat-104" / "derive104.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = (
    '"""NAT-106 session driver for the NAT-106 image (decision 0019; loader-diag-xnu-sb2-md1: '
    "NAT-104's image with Stage B + hb md0 (`com.apple.backboardd.plist`, `lib/libhakios.dylib`, `etc/inject.conf` on `pid1-hb`) and `glue62_impl.h` updated to `TAIL_RETURN=524288`, `BURST=4096` and a 5 s USB settle wait on return): "
    "one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\n"
    "Derived from docs/procedures/nat-104/session_nat104.py by docs/procedures/nat-106/derive106.py "
    "(counted substitutions; `derive106.py --check`); the execution body below is NAT-104's / NAT-078's unchanged."
)


def build():
    """-> (new text, list of (what, count)). Raises ValueError when session_nat104.py or package-001 disagrees."""
    data = SRC.read_bytes()
    got_sha = hashlib.sha256(data).hexdigest()
    if got_sha != SRC_SHA256:
        raise ValueError("session_nat104.py sha256 %s != pinned %s" % (got_sha, SRC_SHA256))
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
        "analyses are analyze_nat104.py (--mode chain, stage-a and hb over NAT-104's 8192+262144 return window) (run separately)",
        "analyses are analyze_nat106.py (--mode stage-b, hb, stage-a and chain over NAT-106's 8192+524288 return window) (run separately)",
        1,
        "analyser names",
    )
    sub("PACKAGE=ROOT/'artifacts/nat-104/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-106/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat104-%s-single-run-*.md", "*-nat106-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-104/native-attempt-%s-used.json", "artifacts/nat-106/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-101','NAT-102','NAT-104')", "'NAT-101','NAT-102','NAT-104','NAT-105','NAT-106')", 1, "required tasks")
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
            print("session_nat106.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat106.py equals the derivation (%d substitutions)" % len(done))
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
