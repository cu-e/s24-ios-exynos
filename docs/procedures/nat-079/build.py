#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-079: build loader-diag-xnu-rx-md1 (the delivery loader) on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_nat-052_build-003_source [--root-bytes 2475720704] [--deadline-s 360] [--pet-s 30]
           [--rx-cap-s 240] [--return-after-s 45] [--rx-direct 1] [--report-s 10] [--ramdisk MACHO]
  build.py --check-only --loader-source COPY_OF_... [same options]

This is NAT-074's build (docs/procedures/nat-074/build.py: the NAT-065 chain, the 4096 MiB window, the reserve-only md1, the bounded pet) with
three differences:

  * the USB engine is NAT-076's (docs/procedures/nat-076/engine: the NAT-041 engine plus one bulk-OUT endpoint) in place of NAT-041's; the build
    compiles it from its own directory, unmodified, and records its hashes;
  * make_variant79.patch_tree() runs after NAT-074's patch_tree(): the engine is brought up with the bulk-OUT endpoint present and a placeholder
    destination, and loader_main calls nat079_receive_root() on the md1 reserve between the checkpoint-slot installation and the final cache clean;
  * the run's time rules are stated and checked here: the receive cap, the kernel's free-run time (`loader_return_after`, a kernel boot-arg) and
    the NAT-044 deadline that ends the run (the loader holds until it, so it is also the length of the run) must fit together:
        pet + 20 <= 83 (NAT-074's rule)    8 <= return_after <= 63 (the kernel runs unpetted for that long: 83 s watchdog - 20 s margin)
        deadline >= rx_cap + return_after + 60    deadline <= 600    rx_cap in (0, 580]
    The 60 s are the loader's own work before and after the receive phase (about 13 s measured in NAT-075: window clear, ELF copy, cache
    clean) plus the 27 checkpoint stops of the kernel and the log dump, with margin.

--ramdisk replaces the md0 ramdisk (NAT-065's probe-init, the default) with the given arm64 Mach-O (at most 1 MiB), e.g. NAT-077's hash probe;
the file's hash is recorded in build.json (nat079_ramdisk). Nothing else about the build changes.

The root image is not an input: only its size is. The size must equal the reserve (a multiple of 16 KiB: tools pad_root.py), because the receive
phase completes only when the whole reserve has been committed.

Output: DIR/loader-diag-xnu-rx-md1/{Image,Image.payload,loader.elf,probe-init,source/} and DIR/build.json (extended with nat079_*)."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-rx-md1"
NEW_TAG = "nat_attempt=NAT078-rx1"          # same length as NAT-074's tag; the run this image is for is NAT-078
ENGINE76 = PROC / "nat-076" / "engine"
DEFAULTS = {"--root-bytes": 2475720704, "--deadline-s": 360, "--pet-s": 30, "--rx-cap-s": 240, "--return-after-s": 45, "--rx-direct": 1,
            "--report-s": 10}
LOADER_WORK_MARGIN_S = 60
RETURN_AFTER_MIN_S, RETURN_AFTER_MAX_S = 8, 63
RX_CAP_MAX_S = 580
RAMDISK_MAX = 1 << 20                       # a sanity bound: NAT-065's probe-init and NAT-077's hash probe are 16 KiB each; anything over 1 MiB is not an init
MACHO64_MAGIC = b"\xcf\xfa\xed\xfe"           # MH_MAGIC_64, little endian


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b74 = _load("nat079_nat074_build", PROC / "nat-074" / "build.py")
mv79 = _load("nat079_make_variant79", HERE / "make_variant79.py")
b52, b47, b65, b67 = b74.b52, b74.b47, b74.b65, b74.b67
sha = b74.sha
STATE = {}


def check_rules79(root_bytes, deadline_s, pet_s, rx_cap_s, return_after_s, rx_direct, report_s):
    """The NAT-079 rules on top of NAT-074's check_rules(). Raises SystemExit with the broken rule."""
    reserve = b74.reserve_for(root_bytes)
    if reserve != root_bytes:
        raise SystemExit(f"root image size {root_bytes} is not a multiple of 16 KiB: pad it first (pad_root.py); the receive phase "
                         f"completes only when all {reserve} reserve bytes are committed")
    b74.check_rules(b74.WDT_S, deadline_s, pet_s)
    if not 0 < rx_cap_s <= RX_CAP_MAX_S:
        raise SystemExit(f"receive cap {rx_cap_s} s must be in (0, {RX_CAP_MAX_S}]")
    if not RETURN_AFTER_MIN_S <= return_after_s <= RETURN_AFTER_MAX_S:
        raise SystemExit(f"loader_return_after {return_after_s} s must be in [{RETURN_AFTER_MIN_S}, {RETURN_AFTER_MAX_S}]: the kernel runs "
                         f"unpetted for that long and the watchdog is {b74.WDT_S} s")
    if deadline_s < rx_cap_s + return_after_s + LOADER_WORK_MARGIN_S:
        raise SystemExit(f"deadline {deadline_s} s < receive cap {rx_cap_s} + loader_return_after {return_after_s} + {LOADER_WORK_MARGIN_S} s: "
                         f"the run would be cut off by the NAT-044 reset before the kernel's free run ends")
    if rx_direct not in (0, 1):
        raise SystemExit("rx-direct must be 0 or 1")
    if not 0 < report_s <= rx_cap_s:
        raise SystemExit("report period must be in (0, cap]")
    return reserve


def split_options(argv):
    """-> (own options with defaults applied, the arguments left for NAT-074's build.py, with --root-bytes/--deadline-s/--pet-s in them)."""
    opts = dict(DEFAULTS)
    rest = [argv[0]]
    i = 1
    while i < len(argv):
        if argv[i] in opts and i + 1 < len(argv):
            try:
                opts[argv[i]] = int(argv[i + 1])
            except ValueError:
                raise SystemExit(f"{argv[i]} needs an integer, got {argv[i + 1]!r}")
            i += 2
        else:
            rest.append(argv[i])
            i += 1
    for k in ("--root-bytes", "--deadline-s", "--pet-s"):
        rest += [k, str(opts[k])]
    return opts, rest


def take_ramdisk(rest):
    """-> (the --ramdisk file as a Path or None, the arguments without it)."""
    if "--ramdisk" not in rest:
        return None, rest
    i = rest.index("--ramdisk")
    if rest.count("--ramdisk") != 1 or i + 1 >= len(rest):
        raise SystemExit("--ramdisk takes exactly one file and may be given once")
    return Path(rest[i + 1]), rest[:i] + rest[i + 2:]


def read_ramdisk(path):
    """The md0 replacement, checked to be a plausible init: a regular file, an arm64-sized Mach-O, at most RAMDISK_MAX bytes."""
    if not path.is_file():
        raise SystemExit(f"--ramdisk {path} is not a regular file")
    data = path.read_bytes()
    if not 0 < len(data) <= RAMDISK_MAX:
        raise SystemExit(f"--ramdisk {path} is {len(data)} bytes; it must be 1..{RAMDISK_MAX}")
    if data[:4] != MACHO64_MAGIC:
        raise SystemExit(f"--ramdisk {path} is not a 64-bit Mach-O (bad magic {data[:4].hex()})")
    return data


def cmdline_append(return_after_s):
    """NAT-067's boot-args with the planned `loader_return_after`; the name and the original value must be there exactly once."""
    old = b67.APPEND
    if old.count(" loader_return_after=8") != 1:
        raise SystemExit("NAT-067's APPEND no longer has ` loader_return_after=8` exactly once: " + old)
    return old.replace(" loader_return_after=8", f" loader_return_after={return_after_s}")


def main():
    opts, rest = split_options(sys.argv)
    ramdisk_path, rest = take_ramdisk(rest)
    ramdisk = read_ramdisk(ramdisk_path) if ramdisk_path else None
    reserve = check_rules79(opts["--root-bytes"], opts["--deadline-s"], opts["--pet-s"], opts["--rx-cap-s"], opts["--return-after-s"],
                            opts["--rx-direct"], opts["--report-s"])
    argv_saved = list(sys.argv)
    sys.argv[:] = rest
    STATE.clear()

    orig_patch_tree = b74.mv.patch_tree
    saved = (b52.ENGINE, b47.ENGINE, b74.NAME, b74.NEW_TAG, b67.APPEND, b65.build_probe)

    def patch_tree79(tree, params=None):
        rec = orig_patch_tree(tree, params)
        STATE["variant79"] = mv79.patch_tree(tree, {"rx_cap_s": opts["--rx-cap-s"], "rx_direct": opts["--rx-direct"],
                                                    "report_s": opts["--report-s"]})
        return rec

    b74.mv.patch_tree = patch_tree79
    b52.ENGINE = b47.ENGINE = ENGINE76
    b74.NAME, b74.NEW_TAG = NAME, NEW_TAG
    b67.APPEND = cmdline_append(opts["--return-after-s"])
    if ramdisk is not None:
        b65.build_probe = lambda work: ramdisk
        STATE["ramdisk"] = {"path": str(ramdisk_path), "sha256": sha(ramdisk), "bytes": len(ramdisk), "replaces": "nat-065 probe-init (md0)"}
    try:
        b74.main()
    finally:
        b74.mv.patch_tree = orig_patch_tree
        b52.ENGINE, b47.ENGINE, b74.NAME, b74.NEW_TAG, b67.APPEND, b65.build_probe = saved
        sys.argv[:] = argv_saved
    if "--out" in argv_saved and "--check-only" not in argv_saved:
        out = Path(argv_saved[argv_saved.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            d["nat079_sources"] = {f: sha((HERE / f).read_bytes()) for f in ("build.py", "make_variant79.py", "src/nat079_impl.h", "src/nat079_fixed.h")}
            d["nat079_engine"] = {f: sha((ENGINE76 / f).read_bytes()) for f in b47.ENGINE_FILES}
            d["nat079_params"] = {"root_bytes": opts["--root-bytes"], "reserve_bytes": reserve, "deadline_s": opts["--deadline-s"],
                                  "pet_s": opts["--pet-s"], "rx_cap_s": opts["--rx-cap-s"], "return_after_s": opts["--return-after-s"],
                                  "rx_direct": opts["--rx-direct"], "report_s": opts["--report-s"], "wdt_s": b74.WDT_S,
                                  "loader_work_margin_s": LOADER_WORK_MARGIN_S}
            d["nat079_variant"] = STATE.get("variant79")
            d["nat079_cmdline_append"] = cmdline_append(opts["--return-after-s"])
            d["nat079_ramdisk"] = STATE.get("ramdisk")
            d["nat079_note"] = ("NAT-074's chain with the NAT-076 engine and the NAT-079 hunks applied after NAT-074's own; the root image is not an "
                                "input, only its size (= the reserve); nothing here ran on a phone")
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
