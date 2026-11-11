#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-069: derive session_nat069.py from NAT-067's session_nat067.py by asserted text substitution (host only).

    derive.py             writes docs/procedures/nat-069/session_nat069.py from the NAT-067 driver and artifacts/nat-069/package-001/package.json
    derive.py --check     compares the committed session_nat069.py with what the derivation gives (exit 1 on a difference)

The driver is the only launcher of the one native run, so it is not imported or patched at run time: it is a plain file that a reader can open. Every substitution
is counted; a NAT-067 driver that has drifted fails here instead of being half-translated."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]
OLD_IMAGE, NEW_IMAGE = "loader-diag-xnu-ne1-usb", "loader-diag-xnu-ne2-usb"

DOC = '''"""NAT-069 session driver for the NAT-069 image (decision 0019): one fixed RECOVERY write, readback, collector + USB watcher, one reboot; no retries.

    session_nat069.py --image loader-diag-xnu-ne2-usb --out DIR [--execute | --restore]

This is the NAT-067 driver (session_nat067.py, itself NAT-065's, NAT-062's, NAT-059's, NAT-057's and NAT-049's) with only these changes: the one image and its pinned hashes come from
NAT-069 package-001; the decision file is the agent-written `docs/decisions/*-nat069-loader-diag-xnu-ne2-usb-single-run-*.md` (exactly one,
naming the RECOVERY and Image.payload hashes and decision 0019; this script never creates it); the registry gate additionally needs NAT-068 and NAT-069 done
(the NAT-067 image ran PID 1 on hardware; this image exists); the one-shot marker lives under artifacts/nat-069. Everything else (the device checks, the full-hash
write and readback of RECOVERY only, the watcher and the collector started and confirmed BEFORE the single `adb reboot recovery`, the restore of the pinned
stock image on any failure before the reboot) is unchanged; test_nat069.py pins that by comparing this file with the derivation from session_nat067.py.

The default is the read-only preflight (it also runs the watcher for a second and the collector self-test, which opens no device).
--restore writes only the pinned stock image without rebooting. No file is staged on the phone. After the reboot this script exits; the watcher
and the collector keep running for WATCH_S / COLLECT_S seconds and the analysis is analyze_nat069.py (run separately)."""'''


def sub(text, old, new, count=1):
    assert text.count(old) == count, "expected %d of %r, found %d" % (count, old, text.count(old))
    return text.replace(old, new)


def derive_session(text67, new_sha, canary_sha, canary_len):
    m = re.match(r'(#!.*\n(?:#.*\n)*)("""(?:.|\n)*?""")', text67)
    assert m, "no docstring after the header comments"
    old_doc = m.group(2)
    assert old_doc.count("\n") == 13 and "NAT-067 session driver" in old_doc, "the NAT-067 docstring has changed shape"
    t = text67.replace(old_doc, DOC, 1)
    t = sub(t, "'%s':dict(" % OLD_IMAGE, "'%s':dict(" % NEW_IMAGE)
    t = sub(t, "NEW_SHA='ae946b4be577b8179ad55f8c43bc4c9ca8afc50c25c131f6823f99d98ea2552d'", "NEW_SHA='%s'" % new_sha)
    t = sub(t, "CANARY_SHA='9fd29fb999dab902f63f04d9f01313be9171c55d539de86cf4dd20c3f18c9cda'", "CANARY_SHA='%s'" % canary_sha)
    t = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=%d" % canary_len)
    t = sub(t, "artifacts/nat-067/package-001", "artifacts/nat-069/package-001")
    t = sub(t, "*-nat067-%s-single-run-*.md", "*-nat069-%s-single-run-*.md")
    t = sub(t, "artifacts/nat-067/native-attempt-%s-used.json", "artifacts/nat-069/native-attempt-%s-used.json")
    old_req = "REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062','NAT-063','NAT-064','NAT-065','NAT-066','NAT-067')"
    new_req = ("REQUIRED_DONE=('NAT-039','NAT-046','NAT-043','NAT-052','NAT-058','NAT-059','NAT-060','NAT-062','NAT-063','NAT-064','NAT-065','NAT-066','NAT-067','NAT-068','NAT-069')")
    assert t.count(old_req) == 1
    i = t.index(old_req)
    j = t.index("\n", i)
    t = t[:i] + new_req + "   # NAT-043/058/060/063/066/068: the log channel and the NAT-052/059/062/065/067 images ran on hardware; NAT-069: this image exists" + t[j:]
    assert OLD_IMAGE not in t, "a NAT-067 image name is left in the derived driver"
    assert "artifacts/nat-067" not in t and "nat067" not in t.replace("session_nat067.py", ""), "a NAT-067 path or glob is left in the derived driver"
    return t


def package_values():
    pkg = json.loads((ROOT / "artifacts/nat-069/package-001/package.json").read_text())["images"][NEW_IMAGE]
    return pkg["recovery_sha256"], pkg["payload_sha256"], pkg["payload_bytes"]


def main(argv):
    text67 = (PROC / "nat-067" / "session_nat067.py").read_text()
    new = derive_session(text67, *package_values())
    out = HERE / "session_nat069.py"
    if "--check" in argv:
        return 0 if out.read_text() == new else 1
    out.write_text(new)
    out.chmod((PROC / "nat-067" / "session_nat067.py").stat().st_mode & 0o777)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
