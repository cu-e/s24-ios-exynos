#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-075: derive session_nat075.py from NAT-067's driver (session_nat067.py) by asserted text substitution (host only).

    derive.py             writes docs/procedures/nat-075/session_nat075.py from the NAT-067 driver and artifacts/nat-075/package-001/package.json
    derive.py --check     compares the committed session_nat075.py with what the derivation gives (exit 1 on a difference)

The driver is the only launcher of the one native run, so it is not imported or patched at run time: it is a plain file that a reader can open. Every
substitution is counted; a NAT-067 driver that has drifted fails here instead of being half-translated. Same method as NAT-067's derive.py."""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
ROOT = HERE.parents[2]
OLD_IMAGE, NEW_IMAGE = "loader-diag-xnu-ne1-usb", "loader-diag-xnu-bigwin-md1"

DOC = '''"""NAT-075 session driver for the NAT-075 image (decision 0019): one fixed RECOVERY write, readback, collector + USB watcher, one reboot; no retries.

    session_nat075.py --image loader-diag-xnu-bigwin-md1 --out DIR [--execute | --restore]

This is the NAT-067 driver (session_nat067.py, itself NAT-065's, NAT-062's, NAT-059's, NAT-057's and NAT-049's) with only these changes: the one image and its pinned hashes
come from NAT-075 package-001 (NAT-074's build packaged by NAT-044's package.py); the decision file is the agent-written
`docs/decisions/*-nat075-loader-diag-xnu-bigwin-md1-single-run-*.md` (exactly one, naming the RECOVERY and Image.payload hashes and decision 0019; this script never creates it);
the registry gate additionally needs NAT-068 and NAT-074 done (the NAT-067 image ran on hardware; this image exists); the one-shot marker lives under artifacts/nat-075.
Everything else (the device checks, the full-hash write and readback of RECOVERY only, the watcher and the collector started and confirmed BEFORE the single
`adb reboot recovery`, the restore of the pinned stock image on any failure before the reboot) is unchanged; test_nat075.py pins that by comparing this file with the
derivation from session_nat067.py.

The default is the read-only preflight (it also runs the watcher for a second and the collector self-test, which opens no device).
--restore writes only the pinned stock image without rebooting. No file is staged on the phone. After the reboot this script exits; the watcher
and the collector keep running for WATCH_S / COLLECT_S seconds and the analysis is analyze_nat075.py (run separately)."""'''


def sub(text, old, new, count=1):
    assert text.count(old) == count, "expected %d of %r, found %d" % (count, old, text.count(old))
    return text.replace(old, new)


def derive_session(text67, new_sha, payload_sha, payload_len):
    m = re.match(r'(#!.*\n(?:#.*\n)*)("""(?:.|\n)*?""")', text67)
    assert m, "no docstring after the header comments"
    old_doc = m.group(2)
    assert "NAT-067 session driver" in old_doc and old_doc.count("\n") == 13, "the NAT-067 docstring has changed shape"
    t = text67.replace(old_doc, DOC, 1)
    t = sub(t, "'%s':dict(" % OLD_IMAGE, "'%s':dict(" % NEW_IMAGE)
    t = sub(t, "NEW_SHA='ae946b4be577b8179ad55f8c43bc4c9ca8afc50c25c131f6823f99d98ea2552d'", "NEW_SHA='%s'" % new_sha)
    t = sub(t, "CANARY_SHA='9fd29fb999dab902f63f04d9f01313be9171c55d539de86cf4dd20c3f18c9cda'", "CANARY_SHA='%s'" % payload_sha)
    t = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=%d" % payload_len)
    t = sub(t, "artifacts/nat-067/package-001", "artifacts/nat-075/package-001")
    t = sub(t, "*-nat067-%s-single-run-*.md", "*-nat075-%s-single-run-*.md")
    t = sub(t, "artifacts/nat-067/native-attempt-%s-used.json", "artifacts/nat-075/native-attempt-%s-used.json")
    old_req = "'NAT-065','NAT-066','NAT-067')"
    new_req = "'NAT-065','NAT-066','NAT-067','NAT-068','NAT-074')"
    i = t.index("REQUIRED_DONE=")
    j = t.index("\n", i)
    line = t[i:j]
    assert line.count(old_req) == 1
    line = line.replace(old_req, new_req)
    cut = line.index("   # ")
    line = line[:cut] + "   # NAT-068: the NAT-067 image (md0 probe PID 1) ran on hardware; NAT-074: this image exists"
    t = t[:i] + line + t[j:]
    assert OLD_IMAGE not in t, "a NAT-067 image name is left in the derived driver"
    code = t.replace(DOC, "")
    assert "nat067" not in code and "artifacts/nat-067" not in code, "a NAT-067 path or glob is left in the derived driver"
    return t


def package_values():
    pkg = json.loads((ROOT / "artifacts/nat-075/package-001/package.json").read_text())["images"][NEW_IMAGE]
    return pkg["recovery_sha256"], pkg["payload_sha256"], pkg["payload_bytes"]


def main(argv):
    text67 = (PROC / "nat-067" / "session_nat067.py").read_text()
    new = derive_session(text67, *package_values())
    out = HERE / "session_nat075.py"
    if "--check" in argv:
        return 0 if out.read_text() == new else 1
    out.write_text(new)
    out.chmod((PROC / "nat-067" / "session_nat067.py").stat().st_mode & 0o777)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
