#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-085: derive session_nat085.py (the session driver of the ephemeral-storage run) from NAT-083's session_nat083.py by asserted text substitution (host only).

    derive85.py            writes docs/procedures/nat-085/session_nat085.py
    derive85.py --check    compares the committed session_nat085.py with what the derivation gives (exit 1 on a difference)

Same method as docs/procedures/nat-083/derive83.py: the driver is the only launcher of the one native run, so it is a plain file a reader can open; every substitution is counted and a
NAT-083 driver that has drifted fails here instead of being half-translated.

What differs from session_nat083.py (everything else is byte-for-byte NAT-083's driver, which is NAT-078's, NAT-075's, ... NAT-049's):
  * the image (`loader-diag-xnu-ep-md1`), its two pinned hashes and the payload length come from NAT-085 package-001 (NAT-085's build packaged by NAT-044's package.py);
  * the decision file glob is `*-nat085-...-single-run-*.md`, the one-shot marker lives under artifacts/nat-085;
  * the registry gate also needs NAT-083, NAT-084 and NAT-085 done (the chain this run extends ran in NAT-084; this image was built and its driver derived in NAT-085);
  * the analysis named in the docstring is analyze_nat085.py.
The root image the companion streams is NAT-083's padded donor-recipe APFS, unchanged (same path, same SHA-256, same size): the run changes the ADT and the small root, not the big root.
The delivery companion, the receive phase, the time rules (rx cap 240 s, loader_return_after 60 s, deadline 360 s) and the single reboot are NAT-078's."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-083/session_nat083.py"
SRC_SHA256 = "4042907ab4d6e56767ff0919130d4c392eb6fb7e68232385bc0116fadd959e7d"
OUT = HERE / "session_nat085.py"
PACKAGE_NAME = "package-001"
PACKAGE = ROOT / "artifacts/nat-085" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-rt-md1", "loader-diag-xnu-ep-md1"
NEW_SHA_OLD = "db5dea2017e243fd9de1b11d9b39165b710fc157200f5c4adebbaa1e1def4725"
CANARY_OLD = "064ed64d30835660da8a6e75c4187cbc60b9a2110c71975ca275f364fafd414f"
LEN_OLD = "26134240"

DOC_OLD = '"""NAT-083 session driver for the NAT-083 image (decision 0019): the NAT-078 driver with the APFS-root image: one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-080/session_nat078.py by docs/procedures/nat-083/derive83.py (counted substitutions; `derive83.py --check`). The text below is NAT-078\'s and still describes the sequence.'
DOC_NEW = '"""NAT-085 session driver for the NAT-085 image (decision 0019): the NAT-083 driver with the ephemeral-storage image: one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-083/session_nat083.py by docs/procedures/nat-085/derive85.py (counted substitutions; `derive85.py --check`); that file is derived from NAT-078\'s. The text below is NAT-078\'s and still describes the sequence.'


def build():
    """-> (new text, list of (what, count)). Raises ValueError when the NAT-083 driver is not the file this derivation was written for."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError("session_nat083.py is not the file this derivation was written for (sha256 %s)" % hashlib.sha256(data).hexdigest())
    pkg = json.loads((PACKAGE / "package.json").read_text())
    img = pkg["images"][IMAGE_NEW]
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
    sub("analysis is analyze_nat083.py (run separately)", "analysis is analyze_nat085.py (run separately)", 1, "analyser name")
    sub("PACKAGE=ROOT/'artifacts/nat-083/package-002'", "PACKAGE=ROOT/'artifacts/nat-085/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s'" % IMAGE_OLD + ":dict(", "'%s'" % IMAGE_NEW + ":dict(", 1, "image key")
    sub(NEW_SHA_OLD, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(CANARY_OLD, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=" + LEN_OLD, "CANARY_LEN=%d" % img["payload_bytes"], 1, "Image.payload length")
    sub("*-nat083-%s-single-run-*.md", "*-nat085-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-083/native-attempt-%s-used.json", "artifacts/nat-085/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-080','NAT-070')", "'NAT-080','NAT-070','NAT-083','NAT-084','NAT-085')", 1, "required tasks")
    # the root image (artifacts/nat-083/system-padded.apfs, its size and SHA-256) is deliberately NOT substituted: the big root is NAT-083's
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
            print("session_nat085.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat085.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), sha256=hashlib.sha256(text.encode()).hexdigest(), substitutions=[dict(what=w, count=c) for w, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
