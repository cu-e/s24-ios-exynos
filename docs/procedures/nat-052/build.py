#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-052: build loader-diag-xnu-ckpt3-usb on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_build-003/source [--stops 11,30,...] [--deadline-s 60] [--service-tenths 3]
  build.py --check-only --loader-source COPY_OF_build-003/source

The image is the NAT-036 resumable-checkpoint loader (loader-diag-xnu-ckpt3) with the NAT-044 deadline/reset into Download Mode,
the NAT-047 USB log transport (NAT-041 engine + NAT-045 ladder, unmodified, from their own directories) and the NAT-052 glue
(patch_ckpt52.py, src/glue52*.h). Patch order on the loader source: nat-036/patch_loader3.py, nat-044/patch_loader4.py,
nat-047's hunks (patch_ckpt52.apply_nat047), then nat-052/patch_ckpt52.py.

Output: DIR/loader-diag-xnu-ckpt3-usb/{Image,Image.payload,loader.elf,source/} and DIR/build.json."""
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
NAME = "loader-diag-xnu-ckpt3-usb"
SRC52 = HERE / "src"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b36 = _load("nat036_build", PROC / "nat-036" / "build.py")
b47 = _load("nat047_build", PROC / "nat-047" / "build.py")
p52 = _load("nat052_patch", HERE / "patch_ckpt52.py")
b22, b44, p4 = b47.b22, b47.b44, b47.p4
ENGINE, LADDER, MODULE = b47.ENGINE, b47.LADDER, b47.MODULE
DEFAULT_DEADLINE_S = 60          # of an 83 s watchdog: the 22 passes of the 17-stop list have to fit before it
DEFAULT_SERVICE_TENTHS = 3


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cc(src, obj, extra, includes):
    """Like nat-036's cc (no -Werror on loader objects; -mgeneral-regs-only dropped for NO_SIMD objects) with several -I."""
    flags = [f for f in b22.FLAGS if f != "-Werror"]
    if b22.NO_SIMD[0] in extra:
        flags = [f for f in flags if f != "-mgeneral-regs-only"]
    b22.run(["zig", "cc", *flags, *extra, *[f"-I{i}" for i in includes], "-c", src, "-o", obj])


def prepare_tree(src, deadline_s, final=True):
    """Patch a copy of the run-006 loader source into the source tree of this image (no compiler involved). Returns the watchdog period.
    final=False stops before patch_ckpt52.py (the tests derive its output themselves)."""
    src = Path(src)
    e = src / "shim/e1s-xnu"
    # NAT-036 (which runs NAT-022's patch_loader with the ckpt2 options), then NAT-044 and NAT-047 on top of NAT-022's marker.h / markerlib.c.
    b22.run([sys.executable, "-I", PROC / "nat-036" / "patch_loader3.py", src])
    for f in ("marker.h", "markerlib.c", "ckpt.h", "ckpt.c", "ckpt2.h"):
        shutil.copy(b36.SRC22 / f, e)
    b22.run([sys.executable, "-I", PROC / "nat-044" / "patch_loader4.py", src])
    wdt = p4.wdt_seconds((e / "guard.c").read_text())
    if not 0 < deadline_s <= wdt - b47.MIN_MARGIN_S:
        raise SystemExit(f"deadline {deadline_s} s must be in (0, {wdt - b47.MIN_MARGIN_S}] for a {wdt} s watchdog")
    p52.apply_nat047(src)       # patch_loader5.py's hunks, one loader.c anchor adapted to NAT-036's include order
    for f in ("reset44.h", "markerlib4.c"):
        shutil.copy(b44.SRC44 / f, e)
    for f in ("usb47.h", "markerlib47.c"):
        shutil.copy(b47.SRC47 / f, e)
    for f in ("marker3.h", "ckpt3.h", "ckpt3_stub.S"):
        shutil.copy(b36.SRC36 / f, e)
    for f in ("glue52.h", "glue52_impl.h"):
        shutil.copy(SRC52 / f, e)
    for f in ("s5e9945_reset.h", "s5e9945_reset.c"):
        shutil.copy(MODULE / f, e)
    if final:
        b22.run([sys.executable, "-I", HERE / "patch_ckpt52.py", src])
    return wdt


def build_one(out, source, stops, deadline_s, service_tenths):
    d = out / NAME
    d.mkdir(parents=True)
    src = d / "source"
    shutil.copytree(source, src, ignore=shutil.ignore_patterns("out", ".git"))
    e = src / "shim/e1s-xnu"
    wdt = prepare_tree(src, deadline_s)
    marker = ["-DMK_TRIG=1", "-DMK_LOADER=1", "-DMK_XNU_CKPT=1", f"-DNAT044_DEADLINE_S={deadline_s}",
              "-DNAT044_REASON=S5E_REASON_DOWNLOAD", "-DNAT047_FAULT=0", f'-DNAT047_TAG="{NAME}"', "-DLAD_WRITING_RUNGS",
              f"-DNAT052_SERVICE_TENTHS={service_tenths}"]
    units = [(e / c, [], [e]) for c in ("start.S", "loader.c", "ui.c", "adt_patch.c", "gic.c", "fdt.c", "guard.c", "s5e9945.c")]
    units += [(e / "markerlib52.c", b22.NO_SIMD + marker, [e, ENGINE, LADDER]),
              (e / "ckpt.c", b22.NO_SIMD + ["-DNAT034_IMAGE=1"], [e]),
              (e / "ckpt3.c", b22.NO_SIMD + [b36.stop_macro(stops)], [e]),
              (e / "ckpt3_stub.S", [], [e]),
              (e / "s5e9945_reset.c", [], [e]),
              (ENGINE / "usbmon.c", [], [ENGINE]),
              (LADDER / "ladder.c", ["-DLAD_WRITING_RUNGS"], [LADDER, ENGINE]),
              (LADDER / "ladder_usb.c", ["-DLAD_WRITING_RUNGS"], [LADDER, ENGINE])]
    objs = []
    for n, (c, extra, inc) in enumerate(units):
        obj = d / f"{n:02d}-{c.name}.o"
        cc(c, obj, extra, inc)
        objs.append(obj)
    b22.link(objs, e / "loader.ld", d / "loader.elf", d / "Image")
    payload = b22.B3 / "payload.bin"
    assert payload.exists(), "the NAT-020 build-003 payload is missing"
    fixed, info = b22._fix_payload()(payload.read_bytes())
    pfix = d / "payload.adt8.bin"
    pfix.write_bytes(fixed)
    b22.payload_fixes[NAME] = info
    b22.run([sys.executable, "-I", src / "tools/e1s/append_payload.py", "--loader", d / "Image", "--payload", pfix,
             "--output", d / "Image.payload"])
    return d / "Image", wdt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--loader-source", required=True)
    ap.add_argument("--stops", default=",".join(str(s) for s in b36.DEFAULT_STOPS))
    ap.add_argument("--deadline-s", type=int, default=DEFAULT_DEADLINE_S)
    ap.add_argument("--service-tenths", type=int, default=DEFAULT_SERVICE_TENTHS)
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    stops = tuple(int(x) for x in a.stops.split(","))
    tmp = tempfile.TemporaryDirectory() if a.check_only else None
    out = Path(tmp.name) / "o" if tmp else Path(a.out)
    if out.exists():
        raise SystemExit("refusing existing output directory")
    out.mkdir(parents=True)
    img, wdt = build_one(out, Path(a.loader_source), stops, a.deadline_s, a.service_tenths)
    data = img.read_bytes()
    assert data[56:60] == b"ARM\x64" and struct.unpack_from("<Q", data, 8)[0] == 0x80000
    assert len(data) == struct.unpack_from("<Q", data, 16)[0] and len(data) < 1 << 20
    if a.check_only:
        print("ok", len(data))
        return
    pl = img.parent / "Image.payload"
    (out / "build.json").write_text(json.dumps({
        "kind": "host-test", "device_used": False, "flashed": False, "stops": list(stops),
        "images": {NAME: {"path": str(img.relative_to(out)), "sha256": sha(img), "bytes": len(data)}},
        "image_payloads": {NAME: {"path": str(pl.relative_to(out)), "sha256": sha(pl), "bytes": pl.stat().st_size}},
        "image_meta": {NAME: {"reason": "0x12345601", "deadline_s": a.deadline_s, "wdt_s": wdt, "service_tenths": a.service_tenths}},
        "sources": {f: sha(p) for f, p in {"patch_ckpt52.py": HERE / "patch_ckpt52.py", "glue52.h": SRC52 / "glue52.h",
                                           "glue52_impl.h": SRC52 / "glue52_impl.h"}.items()},
        "nat036_sources": {f: sha(b36.SRC36 / f) for f in ("ckpt3.c", "ckpt3.h", "ckpt3_stub.S", "markerlib3.c", "marker3.h")},
        "nat047_sources": {f: sha(b47.SRC47 / f) for f in ("usb47.h", "markerlib47.c")},
        "nat041_engine": {f: sha(ENGINE / f) for f in b47.ENGINE_FILES},
        "nat045_ladder": {f: sha(LADDER / f) for f in b47.LADDER_FILES},
        "payload_fixes": b22.payload_fixes, "commands": b22.log}, indent=1))
    print(json.dumps({NAME: sha(img), "Image.payload": sha(pl)}, indent=1))


if __name__ == "__main__":
    main()
