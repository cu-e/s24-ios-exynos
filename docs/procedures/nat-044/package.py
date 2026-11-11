#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-044: package the reset canary images into RECOVERY candidates.

    package.py --build artifacts/nat-044/build-002 --out artifacts/nat-044/package-002 [--only loader-diag-reset]

Host only: reads the pinned stock RECOVERY, writes new files, never opens a phone, refuses an existing output directory.
What goes into the RECOVERY image is `Image.payload` (the loader followed by the XNU payload and its ADT, as in runs 001-009 and in
NAT-036's package), never the loader-only `Image`; the loader checks that payload's header. The packaging itself is NAT-022's
package.py (NAT-006 builder); this script adds what that one does not check: that the file packaged is the build record's payload
(hash), that it sits verbatim at the recorded offset of the RECOVERY image, and that the RECOVERY hash in the record is the hash of
the file. Output: <out>/<image>/{recovery.img,package.json} (NAT-022 format) and <out>/package.json (one summary).
Hashes only are committed; the images stay under artifacts/ (gitignored)."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PACKAGER = ROOT / "docs/procedures/nat-022/package.py"


def sha(b):
    return hashlib.sha256(b).hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--only", action="append", help="package only this image (repeatable)")
    a = ap.parse_args(argv)
    build = json.loads((a.build / "build.json").read_text())
    names = a.only or sorted(build["image_payloads"])
    for n in names:
        if n not in build["image_payloads"]:
            raise SystemExit("package: %s is not an image of the build record" % n)
    a.out.mkdir(parents=True, exist_ok=False)
    summary = {}
    for name in names:
        meta = build["image_payloads"][name]
        payload = a.build / meta["path"]
        data = payload.read_bytes()
        if sha(data) != meta["sha256"] or len(data) != meta["bytes"]:
            raise SystemExit("package: %s does not match the build record" % payload)
        r = subprocess.run([sys.executable, "-I", str(PACKAGER), "--image", str(payload), "--out", str(a.out / name)],
                           capture_output=True, text=True)
        if r.returncode:
            raise SystemExit("package: the NAT-022 packager failed for %s: %s" % (name, (r.stderr or r.stdout)[-300:]))
        pkg = json.loads((a.out / name / "package.json").read_text())
        img = (a.out / name / "recovery.img").read_bytes()
        off = pkg["canary_image_offset"]
        if img[off:off + len(data)] != data:
            raise SystemExit("package: %s is not verbatim at offset %d of the RECOVERY image" % (payload.name, off))
        if pkg["source_image_sha256"] != meta["sha256"] or pkg["recovery_sha256"] != sha(img):
            raise SystemExit("package: the NAT-022 record disagrees with the files for %s" % name)
        summary[name] = dict(recovery_sha256=pkg["recovery_sha256"], recovery_bytes=len(img), payload_sha256=meta["sha256"],
                             payload_bytes=len(data), payload_offset=off, loader_image_sha256=build["images"][name]["sha256"],
                             differing_4k_pages=pkg["differing_4k_pages"])
    (a.out / "package.json").write_text(json.dumps(dict(kind="host-test", device_used=False, flashed=False,
                                                        build=str(a.build), stock_sha256=pkg["stock_sha256"], images=summary), indent=1) + "\n")
    for n, s in summary.items():
        print(n, s["recovery_sha256"], "payload", s["payload_sha256"][:16], "at", s["payload_offset"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
