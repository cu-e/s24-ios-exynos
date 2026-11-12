#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-092: derive session_nat092.py (the session driver of the documented Stage A RE-RUN after the NAT-091 delivery shortfall: same payload as NAT-090 except the image name and the command-line tag) from NAT-087's session_nat087.py by asserted text substitution (host only).

    derive92.py            writes docs/procedures/nat-092/session_nat092.py
    derive92.py --check    compares the committed session_nat092.py with what the derivation gives (exit 1 on a difference)

Same method as docs/procedures/nat-087/derive87.py (and nat-085/derive85.py, nat-083/derive83.py): the driver is the only launcher of the one native run, so it is a plain file a reader can open;
every substitution is counted and a NAT-087 driver that has drifted fails here instead of being half-translated.

What differs from session_nat087.py (everything else is byte-for-byte NAT-087's driver, which is NAT-085's, NAT-083's, NAT-078's, ... NAT-049's):
  * the image (`loader-diag-xnu-sb-md1`), its two pinned hashes come from NAT-092 package-001 (NAT-092's build packaged by NAT-044's package.py); the payload length is the same as
    NAT-087's (the command line sits in a fixed field and md0 keeps its 4 MiB) and is asserted, not substituted;
  * the decision file glob is `*-nat092-...-single-run-*.md`, the one-shot marker lives under artifacts/nat-092;
  * the registry gate also needs NAT-089 (the Stage A analyser and the small root), NAT-090 (the first build of this image; NAT-091 is NOT required: it ran and was inconclusive) and NAT-092 (this image) done;
  * the analyses named in the docstring are analyze_nat087.py (the chain rows) and analyze_nat089.py (the Stage A rows A1-A8).
The root image the companion streams is NAT-083's padded donor-recipe APFS, unchanged. The delivery companion, the receive phase, the time rules (rx cap 240 s,
loader_return_after 60 s, deadline 360 s) and the single reboot are NAT-078's."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-087/session_nat087.py"
SRC_SHA256 = "413d62fbad228bed494127ed7cd243835e049bd900ee0a399498cb16d77ba8a6"
OUT = HERE / "session_nat092.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-092" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-rm-md1", "loader-diag-xnu-sb-md1"
OLD_SHA = "8827c97e365809932d5b9238913efbd72c13ae1d6ab3fb17394604e7eca1e667"
OLD_PAYLOAD_SHA = "d23c71b424de5907b576a044b0229a31e86b39dc88507c5acbc4c7fe28a137b8"
PAYLOAD_LEN = 26134288      # NAT-087's and NAT-092's: the same


def _doc_old():
    """NAT-087's DOC_NEW: the docstring title the NAT-087 driver carries."""
    spec = importlib.util.spec_from_file_location("nat092_derive87", HERE.parent / "nat-087" / "derive87.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = ('"""NAT-092 session driver for the NAT-092 image (decision 0019; a re-run of the NAT-090 Stage A content under a new name and tag): the NAT-087 driver with the Stage A image (restore-mode command line, small root with 19 Apple job plists plus the ps heartbeat): '
           'one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-087/session_nat087.py by docs/procedures/nat-092/derive92.py '
           '(counted substitutions; `derive92.py --check`); that file is derived from NAT-085\'s, which is derived from NAT-083\'s and NAT-078\'s. The text below is NAT-078\'s and still describes the sequence.')


def build():
    """-> (new text, list of (what, count)). Raises ValueError when the NAT-087 driver is not the file this derivation was written for."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError("session_nat087.py is not the file this derivation was written for (sha256 %s)" % hashlib.sha256(data).hexdigest())
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
    sub("analysis is analyze_nat087.py (run separately)", "analyses are analyze_nat087.py (chain rows) and analyze_nat089.py (Stage A rows) (run separately)", 1, "analyser names")
    sub("PACKAGE=ROOT/'artifacts/nat-087/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-092/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s'" % IMAGE_OLD + ":dict(", "'%s'" % IMAGE_NEW + ":dict(", 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat087-%s-single-run-*.md", "*-nat092-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-087/native-attempt-%s-used.json", "artifacts/nat-092/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-083','NAT-084','NAT-085','NAT-087')", "'NAT-083','NAT-084','NAT-085','NAT-087','NAT-089','NAT-090','NAT-092')", 1, "required tasks")
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
            print("session_nat092.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat092.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), sha256=hashlib.sha256(text.encode()).hexdigest(), substitutions=[dict(what=w, count=c) for w, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
