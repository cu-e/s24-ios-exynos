#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-102: build loader-diag-xnu-hb-md1 on the host: NAT-096's image (restore-mode launchd, `rd=md1 ... xrd=md0`, quiet Stage A small root without the lsd job) with ONE change in the small root (md0): NAT-101's heartbeat `/redwood/bin/hb` is started from /etc/rc, in the background, just before `exec /sbin/launchd.darwin`. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-020_build-003_source --ramdisk artifacts/nat-101/pid1-hb/root.apfs
           [--root-bytes 2475720704] [--deadline-s 360] [--pet-s 30] [--rx-cap-s 240] [--return-after-s 60] [--rx-direct 1] [--report-s 10]

Why: NAT-098 (NAT-096's image, run once) showed that Apple's logd (pid 16) and containermanagerd (pid 12) ran, but none of launchd's console-form lines and none of the heartbeat `ps -A` lists reached the
kernel log (NAT-088 had both). So which other daemons stayed up is unknown. NAT-101's `hb` is a static freestanding program that, as a child of PID 1 started before launchd, writes `SWEET hb:` marker lines and
`ps -A` / `ps -Ao pid,ppid,stat,comm` lists to /dev/console every 10 s for 60 rounds. It tests hypothesis H-logd (once logd runs, console output stops reaching the kernel log) from outside launchd's job
machinery, and, if the lists arrive, answers which daemons are alive.

The change against NAT-096 (applied from outside, so docs/procedures/nat-096/build.py, nat-092/build.py, nat-087/build.py and the chain below them stay as they were reviewed and tested): the --ramdisk
file is the small root built by docs/procedures/nat-101/build_hb_root.py: file for file NAT-096's small root plus `bin/hb` and an `etc/rc` that differs only by three comment lines and `/redwood/bin/hb &`
before the final exec line (26 files against 25). This wrapper pins that file's SHA-256 (MD0_SHA256) and refuses any other. The kernel command line, the ADT, the delivered root, stage0/init, the time rules
and the receive phase are NAT-092's.

The image name (`loader-diag-xnu-hb-md1`) and the command-line tag (`nat_attempt=NAT102-hb1`) are new and have the lengths of NAT-096's, so the payload has the same length (asserted by the session
derivation); the md0 region differs. The one-shot marker and decision are per image, hence the new name. Output: DIR/loader-diag-xnu-hb-md1/{Image,Image.payload,loader.elf,probe-init,source/} and
DIR/build.json (extended with nat102_*; NAT-087's own `nat087_*` keys keep their names and carry this image's name and tag, because its build function writes whatever NAME/NEW_TAG it is given)."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-hb-md1"
NEW_TAG = "nat_attempt=NAT102-hb1"          # same length as NAT-096's tag
MD0_BYTES = 4194304
MD0_SHA256 = "97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c"   # artifacts/nat-101/pid1-hb/root.apfs: NAT-096's small root plus bin/hb and the rc line that starts it


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b87 = _load("nat102_nat087_build", PROC / "nat-087" / "build.py")
sha = b87.sha


def argv_value(argv, flag):
    """The value after `flag` in argv, or None."""
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else None


def main():
    argv_saved = list(sys.argv)
    md0 = argv_value(argv_saved, "--ramdisk")
    if "--check-only" not in argv_saved:
        if md0 is None:
            raise SystemExit("--ramdisk is required: the NAT-101 small root (NAT-096's plus the heartbeat)")
        data = Path(md0).read_bytes()
        if len(data) != MD0_BYTES:
            raise SystemExit("the small root is %d bytes, not %d" % (len(data), MD0_BYTES))
        md0_sha = hashlib.sha256(data).hexdigest()
        if md0_sha != MD0_SHA256:
            raise SystemExit("the small root is sha256 %s, not the pinned %s" % (md0_sha, MD0_SHA256))
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
    d["nat102_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
    d["nat102_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "md0_sha256": md0_sha, "md0_bytes": MD0_BYTES, "cmdline": change.get("cmdline")}
    d["nat102_note"] = ("NAT-096's image with the NAT-101 small root as md0 (the same 18 Apple job plists plus the ps heartbeat job, plus the hb program started from /etc/rc); nothing here ran on a phone")
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
