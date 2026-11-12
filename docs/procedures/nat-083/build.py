#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-083: build loader-diag-xnu-rt-md1 (the delivery loader whose kernel boots the delivered APFS as its root) on the host.
Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source --ramdisk SMALL_ROOT.apfs
           [--root-bytes 2475720704] [--deadline-s 360] [--pet-s 30] [--rx-cap-s 240] [--return-after-s 60] [--rx-direct 1] [--report-s 10]

This is NAT-079's build (docs/procedures/nat-079/build.py: the receive phase that puts the padded root image into the md1 reserve, the 4096 MiB
window, the bounded pet, the time rules) with exactly three differences, applied from outside so the NAT-079 file stays as it was reviewed and tested:

  * the kernel's root is /dev/md1, the delivered APFS: `rd=md0` at the start of the command line becomes `rd=md1` (same length, so the
    256-byte limit and every offset are unchanged); nothing else in the command line changes, in particular `e1stouch=0 e1sbattery=0`
    and the NAT-079 `loader_return_after`;
  * md0 is the small image of the donor userland (NAT-083's `root.apfs`: init, rc, job list, mounted on /redwood by stage0), a raw 4 MiB APFS
    container, not a Mach-O. NAT-079 accepts only an arm64 Mach-O of at most 1 MiB for md0; here the file must be an APFS container
    (`NXSB` at byte 32), 4 KiB aligned, at most 8 MiB;
  * the image name and the command-line tag are new (same lengths as NAT-079's: the loader differs from NAT-078's only in immediates).

Why md1 is the root here and md0 is the small image: the project's md0 has always been the payload ramdisk and md1 the USB-delivered reserve
(NAT-074/078), the opposite of the donor's numbering. The donor's stage0 mounts the small image as /dev/md1; the counted substitution in
docs/procedures/nat-083/make_variant83.py makes it /dev/md0.

The default `loader_return_after` is 60 s (NAT-079's rule: 8 to 63): Apple's launchd needs more than NAT-078's 45 s to show how far it gets; the
deadline rule (rx cap 240 + 60 + 60 = 360 s) still holds with the NAT-079 defaults.

Output: DIR/loader-diag-xnu-rt-md1/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json (extended with nat079_* by NAT-079's
build and nat083_* here). The file called `probe-init` is the md0 image, whatever it is."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-rt-md1"
NEW_TAG = "nat_attempt=NAT083-rt1"          # same length as NAT-079's tag; the run this image is for is the first APFS-root run
RETURN_AFTER_DEFAULT = 60
SMALL_ROOT_MAX = 8 << 20
APFS_MAGIC = b"NXSB"                        # nx_superblock magic at byte 32 of block 0
APFS_MAGIC_AT = 32
ROOT_OLD, ROOT_NEW = "rd=md0 ", "rd=md1 "


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b79 = _load("nat083_nat079_build", PROC / "nat-079" / "build.py")
b65 = b79.b65
sha = b79.sha
STATE = {}


def read_small_root(path):
    """The md0 image: a regular file, an APFS container (NXSB at byte 32), a multiple of 4 KiB, 1..SMALL_ROOT_MAX bytes."""
    if not path.is_file():
        raise SystemExit(f"--ramdisk {path} is not a regular file")
    data = path.read_bytes()
    if not 0 < len(data) <= SMALL_ROOT_MAX:
        raise SystemExit(f"--ramdisk {path} is {len(data)} bytes; it must be 1..{SMALL_ROOT_MAX}")
    if len(data) % 4096:
        raise SystemExit(f"--ramdisk {path} is {len(data)} bytes, not a multiple of 4096")
    if data[APFS_MAGIC_AT:APFS_MAGIC_AT + 4] != APFS_MAGIC:
        raise SystemExit(f"--ramdisk {path} is not an APFS container (bytes 32..36 are {data[32:36].hex()}, not NXSB)")
    return data


def root_on_md1(cmdline):
    """NAT-079's command line with the root device changed from md0 to md1: the text must start with `rd=md0 ` and carry no other rd=."""
    if not cmdline.startswith(ROOT_OLD):
        raise SystemExit("the command line does not start with `rd=md0 `: " + cmdline)
    rest = cmdline[len(ROOT_OLD):]
    for tok in rest.split():
        if tok.startswith("rd="):
            raise SystemExit("a second rd= in the command line: " + tok)
    new = ROOT_NEW + rest
    if len(new) != len(cmdline):
        raise SystemExit("the root-device change altered the length of the command line")
    return new


def main():
    if "--ramdisk" not in sys.argv:
        raise SystemExit("--ramdisk SMALL_ROOT.apfs is required (the md0 image)")
    if "--return-after-s" not in sys.argv:
        sys.argv += ["--return-after-s", str(RETURN_AFTER_DEFAULT)]
    argv_saved = list(sys.argv)
    saved = (b79.NAME, b79.NEW_TAG, b79.read_ramdisk, b65.make_cmdline)
    orig_make_cmdline = b65.make_cmdline

    def make_cmdline83(field):
        cmd = root_on_md1(orig_make_cmdline(field))
        STATE["cmdline"] = cmd
        return cmd

    b79.NAME, b79.NEW_TAG = NAME, NEW_TAG
    b79.read_ramdisk = lambda path: STATE.setdefault("small_root", read_small_root(path))
    b65.make_cmdline = make_cmdline83
    try:
        b79.main()
    finally:
        b79.NAME, b79.NEW_TAG, b79.read_ramdisk, b65.make_cmdline = saved
    if "--out" in argv_saved and "--check-only" not in argv_saved:
        out = Path(argv_saved[argv_saved.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            small = STATE.get("small_root", b"")
            d = json.loads(rec.read_text())
            d["nat083_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
            d["nat083_changes"] = {"image_name": NAME, "cmdline_tag": NEW_TAG, "root_device": "md1 (rd=md1)", "cmdline": STATE.get("cmdline"),
                                   "md0_image": {"kind": "APFS container (small root of the donor userland)", "bytes": len(small), "sha256": sha(small)}}
            d["nat083_note"] = ("NAT-079's build with the root device changed to md1 and md0 replaced by the small APFS root; nothing here ran on a phone; "
                                "the 2.31 GiB root is delivered over USB into the md1 reserve by the companion, as in NAT-078")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
