#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-067: derive session_nat067.py from session_nat065.py by asserted text substitution (host only).

    derive.py             writes docs/procedures/nat-067/session_nat067.py from the NAT-065 driver and artifacts/nat-067/package-001/package.json
    derive.py --check     compares the committed session_nat067.py with what the derivation gives (exit 1 on a difference)

The driver is the only launcher of the one native run, so it is not imported or patched at run time: it is a plain file that a reader can open. Every substitution
is counted; a NAT-065 driver that has drifted fails here instead of being half-translated."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]
OLD_IMAGE, NEW_IMAGE = "loader-diag-xnu-md0-usb", "loader-diag-xnu-ne1-usb"

DOC = '''"""NAT-067 session driver for the NAT-067 image (decision 0019): one fixed RECOVERY write, readback, collector + USB watcher, one reboot; no retries.

    session_nat067.py --image loader-diag-xnu-ne1-usb --out DIR [--execute | --restore]

This is the NAT-065 driver (session_nat065.py, itself NAT-062's, NAT-059's, NAT-057's and NAT-049's) with only these changes: the one image and its pinned hashes come from
NAT-067 package-001; the decision file is the agent-written `docs/decisions/*-nat067-loader-diag-xnu-ne1-usb-single-run-*.md` (exactly one,
naming the RECOVERY and Image.payload hashes and decision 0019; this script never creates it); the registry gate additionally needs NAT-066 and NAT-067 done
(the NAT-065 image ran on hardware; this image exists); the one-shot marker lives under artifacts/nat-067. Everything else (the device checks, the full-hash
write and readback of RECOVERY only, the watcher and the collector started and confirmed BEFORE the single `adb reboot recovery`, the restore of the pinned
stock image on any failure before the reboot) is unchanged; test_nat067.py pins that by comparing this file with the derivation from session_nat065.py.

The default is the read-only preflight (it also runs the watcher for a second and the collector self-test, which opens no device).
--restore writes only the pinned stock image without rebooting. No file is staged on the phone. After the reboot this script exits; the watcher
and the collector keep running for WATCH_S / COLLECT_S seconds and the analysis is analyze_nat067.py (run separately)."""'''


def sub(text, old, new, count=1):
    assert text.count(old) == count, "expected %d of %r, found %d" % (count, old, text.count(old))
    return text.replace(old, new)


def derive_session(text65, new_sha, canary_sha, canary_len):
    m = re.match(r'(#!.*\n(?:#.*\n)*)("""(?:.|\n)*?""")', text65)
    assert m, "no docstring after the header comments"
    old_doc = m.group(2)
    assert old_doc.count("\n") == 14 and "NAT-065 session driver" in old_doc, "the NAT-065 docstring has changed shape"
    t = text65.replace(old_doc, DOC, 1)
    t = sub(t, "'%s':dict(" % OLD_IMAGE, "'%s':dict(" % NEW_IMAGE)
    t = sub(t, "NEW_SHA='c6f4a6e45806edf211ce7de16bf0882268b3f8d22f065a21e575bdb66b06f34d'", "NEW_SHA='%s'" % new_sha)
    t = sub(t, "CANARY_SHA='60ca7fc9759efff584b9a13795a16b3a262310cd7823770a408fbac2109087ce'", "CANARY_SHA='%s'" % canary_sha)
    t = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=%d" % canary_len)
    t = sub(t, "artifacts/nat-065/package-001", "artifacts/nat-067/package-001")
    t = sub(t, "*-nat065-%s-single-run-*.md", "*-nat067-%s-single-run-*.md")
    t = sub(t, "artifacts/nat-065/native-attempt-%s-used.json", "artifacts/nat-067/native-attempt-%s-used.json")
    old_req = "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062','NAT-063','NAT-064','NAT-065')"
    new_req = "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062','NAT-063','NAT-064','NAT-065','NAT-066','NAT-067')"
    assert t.count(old_req) == 1
    i = t.index(old_req)
    j = t.index("\n", i)
    t = t[:i] + new_req + "   # NAT-043/058/060/063/066: the log channel and the NAT-052/059/062/065 images ran on hardware; NAT-067: this image exists" + t[j:]
    assert OLD_IMAGE not in t and "nat065" not in t.replace("session_nat065.py", "").replace("NAT-065", "").lower().replace("nat-065", ""), "a NAT-065 name is left in the derived driver"
    return t


def package_values():
    pkg = json.loads((ROOT / "artifacts/nat-067/package-001/package.json").read_text())["images"][NEW_IMAGE]
    return pkg["recovery_sha256"], pkg["payload_sha256"], pkg["payload_bytes"]


def main(argv):
    text65 = (PROC / "nat-065" / "session_nat065.py").read_text()
    new = derive_session(text65, *package_values())
    out = HERE / "session_nat067.py"
    if "--check" in argv:
        return 0 if out.read_text() == new else 1
    out.write_text(new)
    out.chmod((PROC / "nat-065" / "session_nat065.py").stat().st_mode & 0o777)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
