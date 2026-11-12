#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-101: build src/hb.c as a static arm64 Mach-O (the launchd-independent heartbeat program) with NAT-077's pipeline.

  build_hb.py --out DIR [--period 10] [--rounds 60] [--ps-timeout 8]

DIR must not exist. It receives `hb` (the static Mach-O, ad-hoc signed by mkstatic.py) and `hb.json` (sizes, SHA-256 values, toolchain, commands).
Pipeline (NAT-077, unchanged): clang -target arm64-apple-ios16.0 -ffreestanding -c  ->  lld -flavor darwin  ->  mkstatic.py (static re-layout, refuses
any __DATA segment, rebase/bind data, undefined symbol or dylib). Nothing here talks to the phone and nothing here is Apple software.
After the build the result is audited: arm64 MH_EXECUTE, LC_UNIXTHREAD present, no LC_LOAD_DYLIB, no LC_MAIN, no undefined symbol, entry inside __TEXT.
"""
import argparse
import hashlib
import importlib.util
import json
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SRC = HERE / "src"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b77 = _load("nat101_nat077_build", ROOT / "docs/procedures/nat-077/build.py")
mkstatic = b77.mkstatic

LC_UNIXTHREAD, LC_MAIN, LC_LOAD_DYLIB, LC_LOAD_DYLINKER = 0x5, 0x80000028, 0xc, 0xe


class BuildError(Exception):
    pass


def sha(b):
    return hashlib.sha256(b).hexdigest()


def audit(data):
    """Structure facts of the static Mach-O: raises BuildError when it is not what the payload kernel runs as a plain executable."""
    magic, cputype, _sub, filetype, ncmds, _size, _flags, _res = struct.unpack_from("<IiiIIIII", data, 0)
    if magic != 0xfeedfacf or cputype != 0x0100000c or filetype != 2:
        raise BuildError("not an arm64 MH_EXECUTE Mach-O")
    off, cmds, segs = 32, [], []
    for _ in range(ncmds):
        cmd, size = struct.unpack_from("<II", data, off)
        cmds.append(cmd)
        if cmd == 0x19:
            segs.append(data[off + 8:off + 24].split(b"\0")[0].decode())
        off += size
    if LC_UNIXTHREAD not in cmds:
        raise BuildError("no LC_UNIXTHREAD")
    for bad, why in ((LC_MAIN, "LC_MAIN"), (LC_LOAD_DYLIB, "LC_LOAD_DYLIB"), (LC_LOAD_DYLINKER, "LC_LOAD_DYLINKER")):
        if bad in cmds:
            raise BuildError("%s present: the program is not static" % why)
    if segs != ["__PAGEZERO", "__TEXT", "__LINKEDIT"]:
        raise BuildError("segments %s, not __PAGEZERO/__TEXT/__LINKEDIT" % segs)
    return {"load_commands": len(cmds), "segments": segs}


def build(out, period=10, rounds=60, ps_timeout=8):
    out = Path(out)
    if out.exists():
        raise BuildError("%s exists: pick a new directory" % out)
    if not (1 <= period <= 60 and 1 <= rounds <= 600 and 1 <= ps_timeout <= 30):
        raise BuildError("period 1..60, rounds 1..600, ps-timeout 1..30")
    out.mkdir(parents=True)
    defs = ["-DHB_PERIOD_S=%d" % period, "-DHB_ROUNDS=%d" % rounds, "-DHB_PS_TIMEOUT_S=%d" % ps_timeout]
    with tempfile.TemporaryDirectory(prefix="nat101-", dir=out) as w:
        obj, linked = Path(w) / "hb.o", Path(w) / "hb.lld"
        cmd = ["clang", "-target", b77.TARGET] + b77.CFLAGS + defs + ["-c", SRC / "hb.c", "-o", obj]
        b77.run(cmd)
        lcmd = b77.LLD + ["-o", linked, obj]
        b77.run(lcmd)
        data = mkstatic.wrap(linked.read_bytes())
        lld_bytes = linked.read_bytes()
    info = audit(data)
    (out / "hb").write_bytes(data)
    rec = {
        "hb": {"bytes": len(data), "sha256": sha(data)},
        "lld_output": {"bytes": len(lld_bytes), "sha256": sha(lld_bytes)},
        "params": {"period_s": period, "rounds": rounds, "ps_timeout_s": ps_timeout},
        "audit": info,
        "sources_sha256": {"hb.c": sha((SRC / "hb.c").read_bytes())},
        "mkstatic_sha256": sha((ROOT / "docs/procedures/nat-077/mkstatic.py").read_bytes()),
        "mkinit_sha256": mkstatic.MKINIT_SHA256,
        "toolchain": {"clang": b77.version(["clang", "--version"]), "lld": b77.version(["lld", "-flavor", "darwin", "--version"])},
        "commands": [" ".join(map(str, c)).replace(str(out), "$OUT").replace(str(w), "$WORK").replace(str(ROOT), "$REPO") for c in (cmd, lcmd)],
    }
    (out / "hb.json").write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
    return rec


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--period", type=int, default=10)
    ap.add_argument("--rounds", type=int, default=60)
    ap.add_argument("--ps-timeout", type=int, default=8)
    a = ap.parse_args(argv)
    try:
        rec = build(a.out, a.period, a.rounds, a.ps_timeout)
    except BuildError as e:
        raise SystemExit("build_hb: " + str(e))
    print("%s: %d bytes sha256 %s" % (a.out / "hb", rec["hb"]["bytes"], rec["hb"]["sha256"]))


if __name__ == "__main__":
    main()
