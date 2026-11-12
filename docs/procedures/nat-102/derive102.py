#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102: derive session_nat102.py (the session driver of the heartbeat image: NAT-096's image with NAT-101's `hb` program started from /etc/rc of the small root) from NAT-096's session_nat096.py by asserted text substitution (host only).

    derive102.py            writes docs/procedures/nat-102/session_nat102.py
    derive102.py --check    compares the committed session_nat102.py with what the derivation gives (exit 1 on a difference)

Same method as docs/procedures/nat-096/derive96.py (and nat-092/derive92.py, nat-087/derive87.py, nat-085/derive85.py, nat-083/derive83.py): the driver is the only launcher of the one native run, so it is a plain
file a reader can open; every substitution is counted and a NAT-096 driver that has drifted fails here instead of being half-translated.

What differs from session_nat096.py (everything else is byte-for-byte NAT-096's driver, which is NAT-092's, NAT-087's, NAT-085's, NAT-083's, NAT-078's, ... NAT-049's):
  * the image (`loader-diag-xnu-hb-md1`) and its two pinned hashes come from NAT-102 package-001 (NAT-102's build packaged by NAT-044's package.py); the payload length is the same as
    NAT-096's (the command line sits in a fixed field and md0 keeps its 4 MiB) and is asserted, not substituted;
  * the decision file glob is `*-nat102-...-single-run-*.md`, the one-shot marker lives under artifacts/nat-102;
  * the registry gate also needs NAT-101 (the small root with the heartbeat) and NAT-102 (this image, its driver and its analyser) done; NAT-098 is NOT required: it ran and was inconclusive;
  * the analyses named in the docstring add analyze_nat102.py (the heartbeat rows H1-H5) to analyze_nat087.py (the chain rows) and analyze_nat097.py (the Stage A rows).
The root image the companion streams is NAT-083's padded donor-recipe APFS, unchanged. The delivery companion, the receive phase, the time rules (rx cap 240 s, loader_return_after 60 s, deadline 360 s)
and the single reboot are NAT-078's."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-096/session_nat096.py"
SRC_SHA256 = "80e2cc272bd7c172d1b04dc036e6a8d5f051b4fca53a9390c6d0fc15581ae22e"
OUT = HERE / "session_nat102.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-102" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-sq-md1", "loader-diag-xnu-hb-md1"
OLD_SHA = "7595b87752f0e561ada990e1bd7e4bbbdfc1c236198c80f364f49dcd07416da9"
OLD_PAYLOAD_SHA = "5f52765e57da98ab897d321f15aa2192fc0469cff3cc3f55ad32e22138fa88ec"
PAYLOAD_LEN = 26134288      # NAT-087's, NAT-090's, NAT-092's, NAT-096's and NAT-102's: the same


def _doc_old():
    """NAT-096's DOC_NEW: the docstring title the NAT-096 driver carries."""
    spec = importlib.util.spec_from_file_location("nat102_derive96", HERE.parent / "nat-096" / "derive96.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = ('"""NAT-102 session driver for the NAT-102 image (decision 0019; the heartbeat image: NAT-096\'s image with NAT-101\'s `hb` program started from /etc/rc of the small root): the NAT-087 driver with the Stage A image '
           '(restore-mode command line, small root with 18 Apple job plists plus the ps heartbeat job plus the hb program): '
           'one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-096/session_nat096.py by docs/procedures/nat-102/derive102.py '
           '(counted substitutions; `derive102.py --check`); that file is derived from NAT-092\'s, which is derived from NAT-087\'s, NAT-085\'s, NAT-083\'s and NAT-078\'s. The text below is NAT-078\'s and still describes the sequence.')


def build():
    """-> (new text, list of (what, count)). Raises ValueError when the NAT-096 driver is not the file this derivation was written for."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError("session_nat096.py is not the file this derivation was written for (sha256 %s)" % hashlib.sha256(data).hexdigest())
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
    sub("analyses are analyze_nat087.py (chain rows) and analyze_nat097.py (Stage A rows over NAT-097's reader, which infers a lost `KL begin`) (run separately)",
        "analyses are analyze_nat087.py (chain rows), analyze_nat097.py (Stage A rows over NAT-097's reader, which infers a lost `KL begin`) and analyze_nat102.py (heartbeat rows H1-H5 over the same text) (run separately)", 1, "analyser names")
    sub("PACKAGE=ROOT/'artifacts/nat-096/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-102/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s'" % IMAGE_OLD + ":dict(", "'%s'" % IMAGE_NEW + ":dict(", 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat096-%s-single-run-*.md", "*-nat102-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-096/native-attempt-%s-used.json", "artifacts/nat-102/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-092','NAT-096','NAT-097')", "'NAT-092','NAT-096','NAT-097','NAT-101','NAT-102')", 1, "required tasks")
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
            print("session_nat102.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat102.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), sha256=hashlib.sha256(text.encode()).hexdigest(), substitutions=[dict(what=w, count=c) for w, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
