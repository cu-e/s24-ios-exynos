#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-104: derive session_nat104.py (the session driver of loader-diag-xnu-hb2-md1: NAT-102's image with glue62_impl.h updated for B8 observability — TAIL_RETURN=262144, BURST=4096, 10x N62_WAIT before why=2 KL begin) from NAT-102's session_nat102.py by asserted text substitution (host only).

    derive104.py            writes docs/procedures/nat-104/session_nat104.py
    derive104.py --check    compares the committed session_nat104.py with what the derivation gives (exit 1 on a difference)

Same method as docs/procedures/nat-102/derive102.py: the driver is the only launcher of the one native run, so it is a plain file a reader can open; every substitution is counted and a drifted NAT-102 driver fails here instead of being half-translated.

What differs from session_nat102.py:
  * the image (`loader-diag-xnu-hb2-md1`) and its two pinned hashes come from NAT-104 package-001; the payload length is asserted to stay 26,134,288 bytes (CANARY_LEN is unchanged);
  * the decision file glob is `*-nat104-%s-single-run-*.md` and the one-shot marker lives under artifacts/nat-104;
  * the registry gate additionally requires NAT-104 done (NAT-103 stayed in_progress by its inconclusive acceptance rule);
  * the docstring names analyze_nat104.py (over the 8192+262144 return window).
"""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-102/session_nat102.py"
SRC_SHA256 = "698bdf559a23c42ec7e0b7bf2eaea3961ac95408f6fff4de30bd58cb00f6ead4"
OUT = HERE / "session_nat104.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-104" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-hb-md1", "loader-diag-xnu-hb2-md1"
OLD_SHA = "e938cb4a5578b404685feeb21c0a480285b57157f10f4573fba07f28f5afba94"
OLD_PAYLOAD_SHA = "88d6217681784ab638025ad42cb0992672d84bd2b6d21af92c09d85e54e0cd1f"
PAYLOAD_LEN = 26134288


def _doc_old():
    """NAT-102's DOC_NEW: the docstring title the NAT-102 driver carries."""
    spec = importlib.util.spec_from_file_location("nat104_derive102", HERE.parent / "nat-102" / "derive102.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = (
    '"""NAT-104 session driver for the NAT-104 image (decision 0019; loader-diag-xnu-hb2-md1: '
    "NAT-102's image with glue62_impl.h updated to TAIL_RETURN=262144, BURST=4096 and a 5 s USB settle wait on return): "
    "the NAT-102 driver over the B8-fixed build: one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\n"
    "Derived from docs/procedures/nat-102/session_nat102.py by docs/procedures/nat-104/derive104.py "
    '(counted substitutions; `derive104.py --check`); that file is derived from NAT-096\'s, NAT-092\'s, NAT-087\'s, NAT-085\'s, NAT-083\'s and NAT-078\'s. '
    "The text below is NAT-078's and still describes the sequence."
)


def build():
    """-> (new text, list of (what, count)). Raises ValueError when session_nat102.py or package-001 is not as expected."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError(
            "session_nat102.py is not the file this derivation was written for (sha256 %s)"
            % hashlib.sha256(data).hexdigest()
        )
    pkg = json.loads((PACKAGE / "package.json").read_text())
    img = pkg["images"][IMAGE_NEW]
    if img["payload_bytes"] != PAYLOAD_LEN:
        raise ValueError(
            "the payload length of %s is %d, not %d: the driver's CANARY_LEN would need a substitution"
            % (IMAGE_NEW, img["payload_bytes"], PAYLOAD_LEN)
        )
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
        "analyses are analyze_nat087.py (chain rows), analyze_nat097.py (Stage A rows over NAT-097's reader, which infers a lost `KL begin`) and analyze_nat102.py (heartbeat rows H1-H5 over the same text) (run separately)",
        "analyses are analyze_nat104.py (--mode chain, stage-a and hb over NAT-104's 8192+262144 return window) (run separately)",
        1,
        "analyser names",
    )
    sub("PACKAGE=ROOT/'artifacts/nat-102/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-104/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s':dict(" % IMAGE_OLD, "'%s':dict(" % IMAGE_NEW, 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat102-%s-single-run-*.md", "*-nat104-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-102/native-attempt-%s-used.json", "artifacts/nat-104/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-097','NAT-101','NAT-102')", "'NAT-097','NAT-101','NAT-102','NAT-104')", 1, "required tasks")
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
            print("session_nat104.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat104.py equals the derivation (%d substitutions)" % len(done))
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
