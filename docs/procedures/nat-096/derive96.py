#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-096: derive session_nat096.py (the session driver of the quiet Stage A image: NAT-092's image with the com.apple.lsd job left out of the small root) from NAT-092's session_nat092.py by asserted text substitution (host only).

    derive96.py            writes docs/procedures/nat-096/session_nat096.py
    derive96.py --check    compares the committed session_nat096.py with what the derivation gives (exit 1 on a difference)

Same method as docs/procedures/nat-092/derive92.py (and nat-087/derive87.py, nat-085/derive85.py, nat-083/derive83.py): the driver is the only launcher of the one native run, so it is a plain file a reader
can open; every substitution is counted and a NAT-092 driver that has drifted fails here instead of being half-translated.

What differs from session_nat092.py (everything else is byte-for-byte NAT-092's driver, which is NAT-087's, NAT-085's, NAT-083's, NAT-078's, ... NAT-049's):
  * the image (`loader-diag-xnu-sq-md1`) and its two pinned hashes come from NAT-096 package-001 (NAT-096's build packaged by NAT-044's package.py); the payload length is the same as
    NAT-092's (the command line sits in a fixed field and md0 keeps its 4 MiB) and is asserted, not substituted;
  * the decision file glob is `*-nat096-...-single-run-*.md`, the one-shot marker lives under artifacts/nat-096;
  * the registry gate also needs NAT-092 (the image this one is derived from, already in the list through NAT-090's and NAT-092's gate), NAT-096 (this image) and NAT-097 (the reader that
    infers a lost `KL begin`, so the post-run analysis is fixed before the run) done; NAT-091 and NAT-093 are NOT required: both ran and were inconclusive;
  * the analyses named in the docstring are analyze_nat087.py (the chain rows) and analyze_nat097.py (the Stage A rows A1-A8 over NAT-097's reader).
The root image the companion streams is NAT-083's padded donor-recipe APFS, unchanged. The delivery companion, the receive phase, the time rules (rx cap 240 s,
loader_return_after 60 s, deadline 360 s) and the single reboot are NAT-078's."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-092/session_nat092.py"
SRC_SHA256 = "6e47020821409f72075a68ccc5652f78f1615932c5ad770b206ff4c14b68e6e2"
OUT = HERE / "session_nat096.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-096" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sb-md1", "loader-diag-xnu-sq-md1"
OLD_SHA = "9f6c6f634bdfd75dc7e002b58b4706c04e527cd29d419a83e961b6ea3d1fc38c"
OLD_PAYLOAD_SHA = "20ed7c973f7f6349c2ada18c16a5698e674054ba582666f965fd7d122b0e47c7"
PAYLOAD_LEN = 26134288      # NAT-087's, NAT-090's, NAT-092's and NAT-096's: the same


def _doc_old():
    """NAT-092's DOC_NEW: the docstring title the NAT-092 driver carries."""
    spec = importlib.util.spec_from_file_location("nat096_derive92", HERE.parent / "nat-092" / "derive92.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = ('"""NAT-096 session driver for the NAT-096 image (decision 0019; the quiet Stage A image: NAT-092\'s image with the com.apple.lsd job left out of the small root): the NAT-087 driver with the Stage A image '
           '(restore-mode command line, small root with 18 Apple job plists plus the ps heartbeat): '
           'one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-092/session_nat092.py by docs/procedures/nat-096/derive96.py '
           '(counted substitutions; `derive96.py --check`); that file is derived from NAT-087\'s, which is derived from NAT-085\'s, NAT-083\'s and NAT-078\'s. The text below is NAT-078\'s and still describes the sequence.')


def build():
    """-> (new text, list of (what, count)). Raises ValueError when the NAT-092 driver is not the file this derivation was written for."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError("session_nat092.py is not the file this derivation was written for (sha256 %s)" % hashlib.sha256(data).hexdigest())
    pkg = json.loads((PACKAGE / "package.json").read_text())
    img = pkg["images"][IMAGE_NEW]
    if img["payload_bytes"] != PAYLOAD_LEN:
        raise ValueError("the payload length of %s is %d, not %d: the driver's CANARY_LEN would need a substitution" % (IMAGE_NEW, img["payload_bytes"], PAYLOAD_LEN))
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
    sub("analyses are analyze_nat087.py (chain rows) and analyze_nat089.py (Stage A rows) (run separately)",
        "analyses are analyze_nat087.py (chain rows) and analyze_nat097.py (Stage A rows over NAT-097's reader, which infers a lost `KL begin`) (run separately)", 1, "analyser names")
    sub("PACKAGE=ROOT/'artifacts/nat-092/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-096/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s'" % IMAGE_OLD + ":dict(", "'%s'" % IMAGE_NEW + ":dict(", 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat092-%s-single-run-*.md", "*-nat096-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-092/native-attempt-%s-used.json", "artifacts/nat-096/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-089','NAT-090','NAT-092')", "'NAT-089','NAT-090','NAT-092','NAT-096','NAT-097')", 1, "required tasks")
    # the root image (artifacts/nat-083/system-padded.apfs, its size and SHA-256) and CANARY_LEN are deliberately NOT substituted
    return text, done


def main(argv):
    try:
        text, done = build()
    except ValueError as e:
        print("refused: %s" % e, file=sys.stderr)
        return 2
    if "--check" in argv:
        have = OUT.read_text() if OUT.exists() else None
        if have != text:
            print("session_nat096.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat096.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), sha256=hashlib.sha256(text.encode()).hexdigest(), substitutions=[dict(what=w, count=c) for w, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
