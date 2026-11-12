#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-092: build loader-diag-xnu-sb-md1 on the host: NAT-087's image (restore-mode launchd, `rd=md1 ... xrd=md0`) with ONE change, the small root (md0). Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-020_build-003_source --ramdisk docs-or-artifacts/.../root.apfs
           [--root-bytes 2475720704] [--deadline-s 360] [--pet-s 30] [--rx-cap-s 240] [--return-after-s 60] [--rx-direct 1] [--report-s 10]

The change against NAT-087 (applied from outside, so docs/procedures/nat-087/build.py and the chain below it stay as they were reviewed and tested): the --ramdisk file is NAT-089's
Stage A small root (tools/ios/build_pid1_chain.py --jobs --skip-job com.apple.wifid --skip-job com.apple.backboardd --skip-job com.apple.SpringBoard --job com.nat085.ps.plist):
the same three programs, rc and files as NAT-087's, but the LaunchDaemons directory holds 19 of Apple's own job plists (the donor's set minus wifid, backboardd and SpringBoard) plus the
`ps -A` heartbeat job. The kernel command line, the ADT, the delivered root, stage0/init, the time rules and the receive phase are NAT-087's.

NAT-092 is a documented RE-RUN build: NAT-091 ran the NAT-090 image once (decision 0035) and root delivery stopped at the 240 s cap at 91.82% (10.10 MB/s on a loaded host), so the Stage A
question was not answered. The one-shot marker and decision are per image, hence a new name and tag; everything else (small root, kernel, ADT, delivered root, time rules) is NAT-090's, and
test_nat092.py compares the built payload and loader with NAT-090's byte for byte.

The image name (`loader-diag-xnu-sb-md1`) and the command-line tag (`nat_attempt=NAT092-sb1`) are new and have the lengths of NAT-087's, so the payload has the same length (asserted by the
session derivation). The md0 file must be the 4 MiB APFS container that NAT-089's builder wrote; this wrapper refuses any other size and, after the build, checks that build.json records
the same SHA-256 for md0 as the file given. Output: DIR/loader-diag-xnu-sb-md1/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json (extended with nat092_*;
NAT-087's own `nat087_*` keys keep their names and carry this image's name and tag, because its build function writes whatever NAME/NEW_TAG it is given)."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-sb-md1"
NEW_TAG = "nat_attempt=NAT092-sb1"          # same length as NAT-087's tag
MD0_BYTES = 4194304


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b87 = _load("nat092_nat087_build", PROC / "nat-087" / "build.py")
sha = b87.sha


def argv_value(argv, flag):
    """The value after `flag` in argv, or None."""
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def main():
    argv_saved = list(sys.argv)
    md0 = argv_value(argv_saved, "--ramdisk")
    if "--check-only" not in argv_saved:
        if md0 is None:
            raise SystemExit("--ramdisk is required: the Stage A small root")
        data = Path(md0).read_bytes()
        if len(data) != MD0_BYTES:
            raise SystemExit("the small root is %d bytes, not %d" % (len(data), MD0_BYTES))
        md0_sha = hashlib.sha256(data).hexdigest()
    saved = (b87.NAME, b87.NEW_TAG)
    b87.NAME, b87.NEW_TAG = NAME, NEW_TAG
    try:
        b87.main()
    finally:
        b87.NAME, b87.NEW_TAG = saved
    if "--check-only" in argv_saved:
        return
    out = argv_value(argv_saved, "--out")
    if out is None:
        return
    rec = Path(out) / "build.json"
    if not rec.exists():
        raise SystemExit("no build.json was written")
    d = json.loads(rec.read_text())
    md0_rec = (d.get("nat083_changes") or {}).get("md0_image") or {}
    if md0_rec.get("sha256") != md0_sha or md0_rec.get("bytes") != MD0_BYTES:
        raise SystemExit("build.json records md0 %r, the file given is %s (%d bytes)" % (md0_rec, md0_sha, MD0_BYTES))
    change = d.get("nat087_changes") or {}
    if change.get("image_name") != NAME or change.get("cmdline_tag") != NEW_TAG:
        raise SystemExit("build.json does not carry this image's name and tag: %r" % (change,))
    d["nat092_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
    d["nat092_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "md0_sha256": md0_sha, "md0_bytes": MD0_BYTES, "cmdline": change.get("cmdline")}
    d["nat092_note"] = ("NAT-087's build with NAT-089's Stage A small root as md0 (19 Apple job plists plus the ps heartbeat); nothing here ran on a phone")
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
