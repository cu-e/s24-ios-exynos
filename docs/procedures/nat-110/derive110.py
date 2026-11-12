#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-110: derive session_nat110.py (session driver for `loader-diag-xnu-sc2-md1`) from NAT-108's session_nat108.py by counted text substitutions (host-only).

    derive110.py            writes docs/procedures/nat-110/session_nat110.py
    derive110.py --check    compares session_nat110.py against the derivation (exit 1 on drift)
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-108/session_nat108.py"
SRC_SHA256 = "d6956d22c52f67febac827d71bd637d5e4e9819ee73912d39d7b2074c17a6eeb"
OUT = HERE / "session_nat110.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-110" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sc1-md1", "loader-diag-xnu-sc2-md1"
OLD_SHA = "90eecfbc45e055d8514639512c56351668f25e2aae7cd0ea6f50241a744fcdbb"
OLD_PAYLOAD_SHA = "67ec6504724b70db21b7eecc1f3c2c837166561e239303a3d3b56f048e3c9524"
PAYLOAD_LEN = 26134288


def _doc_old():
    """NAT-108's DOC_NEW: the docstring title carried by session_nat108.py."""
    spec = importlib.util.spec_from_file_location("nat110_derive108", HERE.parent / "nat-108" / "derive108.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = (
    '"""NAT-110 session driver for the NAT-110 image (decision 0019; loader-diag-xnu-sc2-md1: '
    "NAT-106's image updated with Stage C2 + hb md0 (396 files: `etc/quiet`, 377 LaunchDaemons after pruning `com.nat085.ps` + 27 non-UI plists), "
    "`fb_diff=1`, `loader_return_after=63`, `deadline_s=365`): "
    "one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\n"
    "Derived from docs/procedures/nat-108/session_nat108.py by docs/procedures/nat-110/derive110.py "
    "(counted substitutions; `derive110.py --check`); the execution body below is NAT-108's / NAT-106's / NAT-078's unchanged."
)


def build():
    """-> (new text, list of (what, count)). Raises ValueError when session_nat108.py or package-001 disagrees."""
    data = SRC.read_bytes()
    got_sha = hashlib.sha256(data).hexdigest()
    if got_sha != SRC_SHA256:
        raise ValueError("session_nat108.py sha256 %s != pinned %s" % (got_sha, SRC_SHA256))
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
        "analyses are analyze_nat108.py (--mode stage-c, stage-b, hb, stage-a and chain over NAT-108's 8192+524288 return window) (run separately)",
        "analyses are analyze_nat110.py (--mode stage-c, stage-b, hb, stage-a and chain over NAT-110's 8192+524288 return window) (run separately)",
        1,
        "analyser names",
    )
    sub("PACKAGE=ROOT/'artifacts/nat-108/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-110/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat108-%s-single-run-*.md", "*-nat110-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-108/native-attempt-%s-used.json", "artifacts/nat-110/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-106','NAT-107','NAT-108')", "'NAT-106','NAT-107','NAT-108','NAT-109','NAT-110')", 1, "required tasks")
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
            print("session_nat110.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat110.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(
        json.dumps(
            dict(
                out=str(OUT.relative_to(ROOT)),
                substitutions=done,
                sha256=hashlib.sha256(text.encode()).hexdigest(),
            ),
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
