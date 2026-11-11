#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-047: build the USB log images on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_build-003/source [--deadline-s 45]
  build.py --check-only --loader-source COPY_OF_build-003/source

Two images, both the NAT-044 reset canary loader (run-006 loader + NAT-022 instrumentation + NAT-027 aligned ADT accesses +
NAT-026 payload header fix + NAT-044 deadline/reset into Download Mode) plus the NAT-047 patch, the NAT-047 glue
(src/markerlib47.c), the NAT-041 usbmon engine and the NAT-045 ladder, linked unmodified from their own directories:

  loader-diag-usbmon        text and stages over USB; the reset at the deadline ends the run
  loader-diag-usbmon-fault  the same, plus a controlled BRK #0x1234 in the hold loop once the host configured the device

Output: DIR/<image>/{Image,Image.payload,loader.elf,source/} and DIR/build.json (hashes, deadline, WDT, engine/ladder hashes)."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
N22, N41, N42, N44, N45 = (PROC / n for n in ("nat-022", "nat-041", "nat-042", "nat-044", "nat-045"))
ENGINE = N41 / "engine"
LADDER = N45 / "src"
SRC47 = HERE / "src"
MODULE = N42 / "module"
IMAGES = {"loader-diag-usbmon": 0, "loader-diag-usbmon-fault": 1}      # name -> NAT047_FAULT
MIN_MARGIN_S = 20          # the deadline must be at least this much before the watchdog
ENGINE_FILES = ("usbmon.c", "usbmon.h", "usbmon_port.h", "port_aarch64.h", "dwc3_regs.h")
LADDER_FILES = ("ladder.c", "ladder_usb.c", "ladder.h", "ladder_regs.h")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b44 = _load("nat044_build", N44 / "build.py")
b22, p4 = b44.b22, b44.p4
p5 = _load("nat047_patch", HERE / "patch_loader5.py")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cc(src, obj, extra, includes, werror):
    flags = [f for f in b22.FLAGS if werror or f != "-Werror"]
    b22.run(["zig", "cc", *flags, *extra, *[f"-I{i}" for i in includes], "-c", src, "-o", obj])


def build_one(out, source, name, deadline_s):
    d = out / name
    d.mkdir(parents=True)
    src = d / "source"
    shutil.copytree(source, src, ignore=shutil.ignore_patterns("out", ".git"))
    b22.run([sys.executable, "-I", N22 / "patch_loader.py", src, "--trig-hold", "--adt-aligned"])
    e = src / "shim/e1s-xnu"
    for f in ("marker.h", "markerlib.c"):
        shutil.copy(b44.SRC22 / f, e)
    b22.run([sys.executable, "-I", N44 / "patch_loader4.py", src])
    wdt = p4.wdt_seconds((e / "guard.c").read_text())
    if not 0 < deadline_s <= wdt - MIN_MARGIN_S:
        raise SystemExit(f"deadline {deadline_s} s must be in (0, {wdt - MIN_MARGIN_S}] for a {wdt} s watchdog")
    b22.run([sys.executable, "-I", HERE / "patch_loader5.py", src])
    for f in ("reset44.h", "markerlib4.c"):
        shutil.copy(b44.SRC44 / f, e)
    for f in ("usb47.h", "markerlib47.c"):
        shutil.copy(SRC47 / f, e)
    for f in ("s5e9945_reset.h", "s5e9945_reset.c"):
        shutil.copy(MODULE / f, e)
    # (source path, extra flags, include dirs, -Werror). The engine and the ladder are compiled from their own directories.
    marker_flags = ["-DMK_TRIG=1", "-DMK_LOADER=1", f"-DNAT044_DEADLINE_S={deadline_s}", "-DNAT044_REASON=S5E_REASON_DOWNLOAD",
                    f"-DNAT047_FAULT={IMAGES[name]}", f'-DNAT047_TAG="{name}"', "-DLAD_WRITING_RUNGS"]
    units = [(e / c, [], [e], False) for c in ("start.S", "loader.c", "ui.c", "adt_patch.c", "gic.c", "fdt.c", "guard.c", "s5e9945.c")]
    units += [(e / "markerlib47.c", marker_flags, [e, ENGINE, LADDER], True),
              (e / "s5e9945_reset.c", [], [e], True),
              (ENGINE / "usbmon.c", [], [ENGINE], True),
              (LADDER / "ladder.c", ["-DLAD_WRITING_RUNGS"], [LADDER, ENGINE], True),
              (LADDER / "ladder_usb.c", ["-DLAD_WRITING_RUNGS"], [LADDER, ENGINE], True)]
    objs = []
    for n, (c, extra, inc, werror) in enumerate(units):
        obj = d / f"{n:02d}-{c.name}.o"
        cc(c, obj, extra, inc, werror)
        objs.append(obj)
    b22.link(objs, e / "loader.ld", d / "loader.elf", d / "Image")
    payload = b22.B3 / "payload.bin"
    assert payload.exists(), "the NAT-020 build-003 payload is missing"
    fixed, info = b22._fix_payload()(payload.read_bytes())
    pfix = d / "payload.adt8.bin"
    pfix.write_bytes(fixed)
    b22.payload_fixes[name] = info
    b22.run([sys.executable, "-I", src / "tools/e1s/append_payload.py", "--loader", d / "Image", "--payload", pfix,
             "--output", d / "Image.payload"])
    return d / "Image", wdt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--loader-source", required=True)
    ap.add_argument("--deadline-s", type=int, default=45)
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    tmp = tempfile.TemporaryDirectory() if a.check_only else None
    out = Path(tmp.name) / "o" if tmp else Path(a.out)
    if out.exists():
        raise SystemExit("refusing existing output directory")
    out.mkdir(parents=True)
    images, payloads, meta = {}, {}, {}
    for name in IMAGES:
        img, wdt = build_one(out, Path(a.loader_source), name, a.deadline_s)
        data = img.read_bytes()
        assert data[56:60] == b"ARM\x64" and struct.unpack_from("<Q", data, 8)[0] == 0x80000
        assert len(data) == struct.unpack_from("<Q", data, 16)[0] and len(data) < 1 << 20
        pl = img.parent / "Image.payload"
        images[name] = {"path": str(img.relative_to(out)), "sha256": sha(img), "bytes": len(data)}
        payloads[name] = {"path": str(pl.relative_to(out)), "sha256": sha(pl), "bytes": pl.stat().st_size}
        meta[name] = {"reason": "0x12345601", "deadline_s": a.deadline_s, "wdt_s": wdt, "fault": IMAGES[name]}
    if a.check_only:
        print("ok", {k: v["bytes"] for k, v in images.items()})
        return
    (out / "build.json").write_text(json.dumps({
        "kind": "host-test", "device_used": False, "flashed": False, "images": images, "image_payloads": payloads,
        "image_meta": meta,
        "nat041_engine": {f: sha(ENGINE / f) for f in ENGINE_FILES},
        "nat045_ladder": {f: sha(LADDER / f) for f in LADDER_FILES},
        "nat042_module": {f: sha(MODULE / f) for f in ("s5e9945_reset.h", "s5e9945_reset.c")},
        "nat044_sources": {f: sha(b44.SRC44 / f) for f in ("reset44.h", "markerlib4.c")} | {"patch_loader4.py": sha(N44 / "patch_loader4.py")},
        "nat047_sources": {f: sha(SRC47 / f) for f in ("usb47.h", "markerlib47.c")} | {"patch_loader5.py": sha(HERE / "patch_loader5.py")},
        "payload_fixes": b22.payload_fixes, "commands": b22.log}, indent=1))
    print(json.dumps({n: {"Image": images[n]["sha256"], "Image.payload": payloads[n]["sha256"]} for n in images}, indent=1))


if __name__ == "__main__":
    main()
