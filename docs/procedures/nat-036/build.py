#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-036: build the loader-diag-xnu-ckpt3 image on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_build-003/source [--stops 11,30,...]
  build.py --check-only --loader-source COPY_OF_build-003/source

Uses NAT-022's build helpers (the toolchain flags, the linker and padding, the payload fix and the payload append) and adds the
one image. Every earlier image is built by nat-022/build.py and is unchanged: this script only adds a directory.

Output: DIR/loader-diag-xnu-ckpt3/{Image,Image.payload,loader.elf,source/} and DIR/build.json.
"""
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
ROOT = HERE.parents[2]
SRC22 = HERE.parent / "nat-022" / "src"
SRC36 = HERE / "src"
NAME = "loader-diag-xnu-ckpt3"

# The default stop list: every C checkpoint of arm_init in program order up to the last one before arm_vm_init that the
# NAT-035 model reaches (cp 17..21 are beyond the model, see the README). 17 stops.
DEFAULT_STOPS = (11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16)
# The shorter list for the display budget.
SHORT_STOPS = (11, 30, 35, 12, 44, 13, 14, 15, 16)


def _b22():
    spec = importlib.util.spec_from_file_location("nat022_build", HERE.parent / "nat-022" / "build.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


b22 = _b22()


def stop_macro(stops):
    return "-DNAT036_STOP_LIST=" + ",".join(str(int(s)) for s in stops)


def cc(src, obj, extra, includes):
    """The loader build's compile line (nat-022/build.py build_loader): -Werror dropped for every loader object, and
    -mgeneral-regs-only dropped for the objects built with NO_SIMD (zig cc emits SIMD with it; the feature flag removes it)."""
    flags = [f for f in b22.FLAGS if f != "-Werror"]
    if b22.NO_SIMD[0] in extra:
        flags = [f for f in flags if f != "-mgeneral-regs-only"]
    b22.run(["zig", "cc", *flags, *extra, f"-I{includes}", "-c", src, "-o", obj])


def build_ckpt3(out, source, name=NAME, stops=DEFAULT_STOPS):
    d = out / name
    d.mkdir(parents=True)
    src = d / "source"
    shutil.copytree(source, src, ignore=shutil.ignore_patterns("out", ".git"))
    b22.run([sys.executable, "-I", HERE / "patch_loader3.py", src])
    e = src / "shim/e1s-xnu"
    for f in ("marker.h", "markerlib.c", "ckpt.h", "ckpt.c", "ckpt2.h"):
        shutil.copy(SRC22 / f, e)
    for f in ("marker3.h", "markerlib3.c", "ckpt3.h", "ckpt3.c", "ckpt3_stub.S"):
        shutil.copy(SRC36 / f, e)
    # markerlib3.c includes markerlib.c: it is compiled instead of it, never beside it.
    names = ["start.S", "loader.c", "ui.c", "adt_patch.c", "gic.c", "fdt.c", "guard.c", "s5e9945.c", "markerlib3.c",
             "ckpt.c", "ckpt3.c", "ckpt3_stub.S"]
    objs = []
    for c in names:
        extra = []
        if c == "markerlib3.c":
            extra = b22.NO_SIMD + ["-DMK_TRIG=1", "-DMK_LOADER=1", "-DMK_XNU_CKPT=1"]
        elif c == "ckpt.c":
            extra = b22.NO_SIMD + ["-DNAT034_IMAGE=1"]
        elif c == "ckpt3.c":
            extra = b22.NO_SIMD + [stop_macro(stops)]
        obj = d / (c + ".o")
        cc(e / c, obj, extra, e)
        objs.append(obj)
    b22.link(objs, e / "loader.ld", d / "loader.elf", d / "Image")
    payload = b22.B3 / "payload.bin"
    assert payload.exists(), "the NAT-020 build-003 payload is missing"
    fixed, info = b22._fix_payload()(payload.read_bytes())
    payload = d / "payload.adt8.bin"
    payload.write_bytes(fixed)
    b22.payload_fixes[name] = info
    b22.run([sys.executable, "-I", src / "tools/e1s/append_payload.py", "--loader", d / "Image", "--payload", payload,
             "--output", d / "Image.payload"])
    return d / "Image"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--loader-source", required=True)
    ap.add_argument("--stops", default=",".join(str(s) for s in DEFAULT_STOPS))
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    stops = tuple(int(x) for x in a.stops.split(","))
    tmp = tempfile.TemporaryDirectory() if a.check_only else None
    out = Path(tmp.name) / "o" if tmp else Path(a.out)
    if out.exists():
        raise SystemExit("refusing existing output directory")
    out.mkdir(parents=True)
    img = build_ckpt3(out, Path(a.loader_source), stops=stops)
    d = img.read_bytes()
    assert d[56:60] == b"ARM\x64" and struct.unpack_from("<Q", d, 8)[0] == 0x80000
    assert len(d) == struct.unpack_from("<Q", d, 16)[0] and len(d) < 1 << 20
    if a.check_only:
        print("ok", len(d))
        return
    pl = img.parent / "Image.payload"
    (out / "build.json").write_text(json.dumps({
        "kind": "host-test", "device_used": False, "flashed": False, "stops": list(stops),
        "images": {NAME: {"path": str(img.relative_to(out)), "sha256": b22.sha(img), "bytes": len(d)}},
        "image_payloads": {NAME: {"path": str(pl.relative_to(out)), "sha256": b22.sha(pl), "bytes": pl.stat().st_size}},
        "payload_fixes": b22.payload_fixes, "commands": b22.log}, indent=1))
    print(json.dumps({NAME: b22.sha(img), "Image.payload": b22.sha(pl)}, indent=1))


if __name__ == "__main__":
    main()
