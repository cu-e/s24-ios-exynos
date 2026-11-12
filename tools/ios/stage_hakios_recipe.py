#!/usr/bin/env python3
"""Copy the pinned HackiOS userland recipe out of references/hakios into a work directory.

Why a copy: sysimage/unpack.sh writes 8 GB next to itself (it does `cd "$(dirname "$0")"`), and the pinned
checkout must stay clean for `tools/sources.py verify`.  The copy keeps the donor layout (sysimage/, tools/,
xnu-deps/build/lzbitmap/, userland/) so the donor scripts find each other without modification.

Only files listed in research/sources.json review_files for source "hakios" are copied, and each is checked
against the blob in the pinned checkout.  The donor files are MIT (scripts) or APSL (libzbitmap); see the
LICENSE and NOTICE files in references/hakios.  Nothing of Apple's is involved at this step.

usage: python3 -I tools/ios/stage_hakios_recipe.py DEST [--manifest OUT.json]
"""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREFIXES = ("sysimage/", "tools/font_trim.py", "tools/apfs/", "userland/", "xnu-deps/build/lzbitmap/",
            "xnuloader/mkpayload.py", "xnu/files/bsd/miscfs/apfs/", "Makefile", "NOTICE", "LICENSE",
            "LICENSE.APSL")


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    dest = Path(argv[1])
    manifest_out = Path(argv[argv.index("--manifest") + 1]) if "--manifest" in argv else None
    sources = json.loads((ROOT / "research/sources.json").read_text())["sources"]
    src = next(s for s in sources if s["id"] == "hakios")
    verify = subprocess.run([sys.executable, "-I", str(ROOT / "tools/sources.py"), "verify", "hakios"],
                            capture_output=True, text=True, timeout=170)
    if verify.returncode != 0:
        print("hakios checkout does not verify:", verify.stderr.strip() or verify.stdout.strip())
        return 1
    report = json.loads(verify.stdout)
    if not report.get("clean") or report.get("revision") != src["revision"]:
        print("hakios checkout is not clean at the pinned revision")
        return 1
    checkout = ROOT / "references/hakios"
    files = {}
    for name in src["review_files"]:
        if not name.startswith(PREFIXES):
            continue
        sha = report["review_file_sha256"][name]
        data = (checkout / name).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha:
            print("changed since verify:", name)
            return 1
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        shutil.copymode(checkout / name, target)
        files[name] = sha
    manifest = {"source": "hakios", "origin": report["origin"], "revision": report["revision"],
                "licence_notes": src["license_notes"], "files": files}
    if manifest_out:
        manifest_out.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print("staged %d files from %s @ %s into %s" % (len(files), report["origin"], report["revision"], dest))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
