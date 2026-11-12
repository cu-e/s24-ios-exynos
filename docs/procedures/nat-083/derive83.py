#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-083: derive session_nat083.py (the session driver of the APFS-root run) from NAT-080's session_nat078.py by asserted text substitution (host only).

    derive83.py            writes docs/procedures/nat-083/session_nat083.py
    derive83.py --check    compares the committed session_nat083.py with what the derivation gives (exit 1 on a difference)

The driver is the only launcher of the one native run, so it is not imported or patched at run time: it is a plain file that a reader can open. Every substitution
is counted; a NAT-080 driver that has drifted fails here instead of being half-translated (same method as docs/procedures/nat-080/derive.py).

What differs from session_nat078.py (everything else is byte-for-byte the NAT-078 driver, which is NAT-075's, NAT-067's, ... NAT-049's):
  * the image (`loader-diag-xnu-rt-md1`), its two pinned hashes and the payload length come from NAT-083 package-002 (NAT-083's build packaged by NAT-044's package.py);
  * the root image the companion streams is NAT-083's padded donor-recipe APFS (artifacts/nat-083/system-padded.apfs, same size as NAT-078's, so the md1 reserve is unchanged);
  * the decision file glob is `*-nat083-...-single-run-*.md`, the one-shot marker lives under artifacts/nat-083;
  * the registry gate also needs NAT-070 done (the display read: the payload kernel with the e1s display map ran on the phone);
  * the analysis named in the docstring is analyze_nat083.py.
The delivery companion, the receive phase, the time rules (rx cap 240 s, loader_return_after 60 s, deadline 360 s) and the single reboot are NAT-078's."""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = ROOT / "docs/procedures/nat-080/session_nat078.py"
SRC_SHA256 = "d4c1a99b22137ed48e5d23d1fcad86e020b3bddab012a3044d28ebde04987c2b"
OUT = HERE / "session_nat083.py"
PACKAGE_NAME = "package-002"       # NAT-083 build-002 (small root with etc/rc = rc.nat083, no jobs) packaged by NAT-044's package.py
PACKAGE = ROOT / "artifacts/nat-083" / PACKAGE_NAME
IMAGE_OLD, IMAGE_NEW = "loader-diag-xnu-rx-md1", "loader-diag-xnu-rt-md1"
ROOT_SIZE = 2475720704
ROOT_SHA_OLD = "552800ff3ac3de129b550c838681d0cb1d08cc4df0d38b2dc1088a9b258a8258"
ROOT_SHA_NEW = "4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6"
NEW_SHA_OLD = "d95024989a2cc8cd96c39a10bf9c4c33552047c36dc0c2618b88dcfef10c02ef"
CANARY_OLD = "95aec19a75594a89378f79fe372bf67db1301667073ceef3036a61ad59520512"
LEN_OLD = "21956576"

DOC_OLD = '"""NAT-078 session driver for the NAT-079 image (decision 0019): one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.'
DOC_NEW = '"""NAT-083 session driver for the NAT-083 image (decision 0019): the NAT-078 driver with the APFS-root image: one fixed RECOVERY write, readback, collector + USB watcher + delivery companion, one reboot; no retries.\n\nDerived from docs/procedures/nat-080/session_nat078.py by docs/procedures/nat-083/derive83.py (counted substitutions; `derive83.py --check`). The text below is NAT-078\'s and still describes the sequence.'


def build():
    """-> (new text, list of (what, count)). Raises ValueError when the NAT-078 driver is not the file this derivation was written for."""
    data = SRC.read_bytes()
    if hashlib.sha256(data).hexdigest() != SRC_SHA256:
        raise ValueError("session_nat078.py is not the file this derivation was written for (sha256 %s)" % hashlib.sha256(data).hexdigest())
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
    sub("analysis is analyze_nat080.py (run separately)", "analysis is analyze_nat083.py (run separately)", 1, "analyser name")
    sub("PACKAGE=ROOT/'artifacts/nat-079/package-002'", "PACKAGE=ROOT/'artifacts/nat-083/%s'" % PACKAGE_NAME, 1, "package path")
    sub("'%s'" % IMAGE_OLD + ":dict(", "'%s'" % IMAGE_NEW + ":dict(", 1, "image key")
    sub(NEW_SHA_OLD, img["recovery_sha256"], 1, "RECOVERY sha256")
    sub(CANARY_OLD, img["payload_sha256"], 1, "Image.payload sha256")
    sub("CANARY_LEN=" + LEN_OLD, "CANARY_LEN=%d" % img["payload_bytes"], 1, "Image.payload length")
    sub("ROOT_IMAGE=ROOT/'artifacts/nat-077/system-padded.apfs'", "ROOT_IMAGE=ROOT/'artifacts/nat-083/system-padded.apfs'", 1, "root image path")
    sub("ROOT_SHA='%s'" % ROOT_SHA_OLD, "ROOT_SHA='%s'" % ROOT_SHA_NEW, 1, "root image sha256")
    sub("*-nat078-%s-single-run-*.md", "*-nat083-%s-single-run-*.md", 1, "decision glob")
    sub("artifacts/nat-078/native-attempt-%s-used.json", "artifacts/nat-083/native-attempt-%s-used.json", 1, "one-shot marker")
    sub("'NAT-079','NAT-080')", "'NAT-079','NAT-080','NAT-070')", 1, "required tasks")
    # the remaining mentions of the old names are inside the docstring (kept: they describe the NAT-078 sequence this file is derived from)
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
            print("session_nat083.py differs from the derivation", file=sys.stderr)
            return 1
        print("ok: session_nat083.py equals the derivation (%d substitutions)" % len(done))
        return 0
    OUT.write_text(text)
    print(json.dumps(dict(out=str(OUT.relative_to(ROOT)), sha256=hashlib.sha256(text.encode()).hexdigest(), substitutions=[dict(what=w, count=c) for w, c in done]), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
