#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-087: derive session_nat087.py (the session driver of the restore-mode run) from NAT-085's session_nat085.py by asserted text substitution (host only).

    derive87.py            writes docs/procedures/nat-087/session_nat087.py
    derive87.py --check    compares the committed session_nat087.py with what the derivation gives (exit 1 on a difference)

Same method as docs/procedures/nat-085/derive85.py (and nat-083/derive83.py): the driver is the only launcher of the one native run, so it is a plain file a reader can open; every
substitution is counted and a NAT-085 driver that has drifted fails here instead of being half-translated.

What differs from session_nat085.py (everything else is byte-for-byte NAT-085's driver, which is NAT-083's, NAT-078's, ... NAT-049's):
  * the image (`loader-diag-xnu-rm-md1`), its two pinned hashes come from NAT-087 package-001 (NAT-087's build packaged by NAT-044's package.py); the payload length is the same as
    NAT-085's (the command line sits in a fixed 256-byte field) and is asserted, not substituted;
  * the decision file glob is `*-nat087-...-single-run-*.md`, the one-shot marker lives under artifacts/nat-087;
  * the registry gate also needs NAT-087 done (this image was built and its driver derived there);
  * the analysis named in the docstring is analyze_nat087.py.
The root image the companion streams is NAT-083's padded donor-recipe APFS, unchanged. The delivery companion, the receive phase, the time rules (rx cap 240 s,
loader_return_after 60 s, deadline 360 s) and the single reboot are NAT-078's."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-085/session_nat085.py"
SRC_SHA256 = "fc85053523e5a9673a022dd19a41d88787ad0ab5ba526c4cc7d26d0b4195ef82"
OUT = HERE / "session_nat087.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-087" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-ep-md1", "loader-diag-xnu-rm-md1"
OLD_SHA = "fe216cd39eb68105b31dfca583a13a8e34a67287cd8a88466f4d39b6262e5593"
OLD_PAYLOAD_SHA = "dec89a07169c44afd37cc234e684388c86b201cb0bee5108721bce812f309e20"
PAYLOAD_LEN = 26134288      # NAT-085's and NAT-087's: the same


def _doc_old():
    spec = importlib.util.spec_from_file_location("nat087_derive85", HERE.parent / "nat-085" / "derive85.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DOC_NEW


DOC_NEW = ('"""NAT-087 session driver for the NAT-087 image (decision 0019): the NAT-085 driver with the restore-mode image (command line ends in `xrd=md0`): one fixed RECOVERY write, '
           'readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-085/session_nat085.py by docs/procedures/nat-087/derive87.py '
           '(counted substitutions; `derive87.py --check`); that file is derived from NAT-083\'s, which is derived from NAT-078\'s. The text below is NAT-078\'s and still describes the sequence.')


def build():
    """-> (new text, list of (what, count)). Raises ValueError when the NAT-085 driver is not the file this derivation was written for."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError("session_nat085.py is not the file this derivation was written for (sha256 %s)" % hashlib.sha256(data).hexdigest())
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
    sub("analysis is analyze_nat085.py (run separately)", "analysis is analyze_nat087.py (run separately)", 1, "analyser name")
    sub("PACKAGE=ROOT/'artifacts/nat-085/%s'" % PACKAGE_NAME, "PACKAGE=ROOT/'artifacts/nat-087/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s'" % IMAGE_OLD + ":dict(", "'%s'" % IMAGE_NEW + ":dict(", 1, "image key")
    sub(OLD_SHA, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(OLD_PAYLOAD_SHA, img["payload_sha256"], 1, "Image.payload sha256")
    sub("*-nat085-%s-single-run-*.md", "*-nat087-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-085/native-attempt-%s-used.json", "artifacts/nat-087/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-083','NAT-084','NAT-085')", "'NAT-083','NAT-084','NAT-085','NAT-087')", 1, "required tasks")
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
            print("session_nat087.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat087.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), sha256=hashlib.sha256(text.encode()).hexdigest(), substitutions=[dict(what=w, count=c) for w, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
