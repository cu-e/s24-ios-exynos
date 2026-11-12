#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-087: build loader-diag-xnu-rm-md1 on the host: NAT-085's image (delivered APFS as the kernel's root, rd=md1, ADT ephemeral-storage=1, one launchd job) with ONE change. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-020_build-003_source --ramdisk SMALL_ROOT.apfs
           [--root-bytes 2475720704] [--deadline-s 360] [--pet-s 30] [--rx-cap-s 240] [--return-after-s 60] [--rx-direct 1] [--report-s 10]

The one change against NAT-085 (applied from outside, so docs/procedures/nat-085/build.py and the chain below it stay as they were reviewed and tested): the kernel command line
gets a last token ` xrd=md0`.

Why: Apple's launchd decides per boot task whether to run it (predicate at 0x10003b8c8 of the pinned sbin/launchd). Its "restore/ramdisk environment" flag is set when
`strstr(kern.bootargs, "rd=md0")` is true (or the strings Restore/Ramdisk/RamDisk match); in that environment only boot tasks marked PerformAlways or PerformInRestore run, and a
missing service cache is not fatal. NAT-086 (cmdline `rd=md1 ...`) ran every boot task and died at launchd_cache_loader, which needs the /System/Library/xpc/launchd.plist that the donor
recipe deletes from the system image. XNU's boot-arg parser compares whole keys (pexpert/gen/bootargs.c: `xrd` is not `rd`), so the kernel still roots on `rd=md1`, while launchd's
substring search finds `rd=md0` inside `xrd=md0`. The donor's own boot keeps `rd=md0` for the same reason (userland/src/init.c).

The image name (`loader-diag-xnu-rm-md1`) and the command-line tag (`nat_attempt=NAT087-rm1`) are new and have the lengths of NAT-085's. The command line grows by the 8 bytes of the token;
it stays below the kernel's 256-byte limit (checked here). Output: DIR/loader-diag-xnu-rm-md1/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json (extended with nat087_*)."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-rm-md1"
NEW_TAG = "nat_attempt=NAT087-rm1"          # same length as NAT-085's tag
TOKEN = " xrd=md0"
STATE = {}


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b85 = _load("nat087_nat085_build", PROC / "nat-085" / "build.py")
b83 = b85.b83
b65 = b85.b65
sha = b85.sha


def add_token(cmdline):
    """NAT-079's command line (still `rd=md0 ...` here; NAT-083's hook turns the root into md1 afterwards) -> the same with TOKEN as the last token."""
    if "xrd=" in cmdline:
        raise SystemExit("the command line already has an xrd= token: " + cmdline)
    new = cmdline + TOKEN
    if len(new) >= 256:
        raise SystemExit("the kernel's BOOT_LINE_LENGTH is 256: the command line (%d bytes) would be cut" % len(new))
    return new


def main():
    argv_saved = list(sys.argv)
    orig = b65.make_cmdline

    def make_cmdline87(field):
        new = add_token(orig(field))
        STATE["cmdline_before_root_change"] = new
        return new

    saved = (b85.NAME, b85.NEW_TAG, b65.make_cmdline)
    b85.NAME, b85.NEW_TAG = NAME, NEW_TAG
    b65.make_cmdline = make_cmdline87
    try:
        b85.main()
    finally:
        b85.NAME, b85.NEW_TAG, b65.make_cmdline = saved
    if "--check-only" in argv_saved:
        return
    if "cmdline_before_root_change" not in STATE:
        raise SystemExit("the command-line hook never ran: the image was NOT built with the token")
    if "--out" in argv_saved:
        out = Path(argv_saved[argv_saved.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            final = (d.get("nat083_changes") or {}).get("cmdline")
            toks = (final or "").split()
            if not final or not final.endswith(TOKEN) or toks.count("rd=md1") != 1 or [t for t in toks if t.startswith("rd=")] != ["rd=md1"]:
                raise SystemExit("the final command line is not `rd=md1` once, no other rd= token, ending in the token: " + repr(final))
            d["nat087_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
            d["nat087_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "token": TOKEN.strip(), "cmdline": final, "cmdline_bytes": len(final)}
            d["nat087_note"] = ("NAT-085's build with the last command-line token ` xrd=md0` added (XNU ignores it; launchd's strstr for rd=md0 finds it); "
                                "nothing here ran on a phone")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
