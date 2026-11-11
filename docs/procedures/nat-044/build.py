#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-044: build the reset canary images on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_build-003/source [--deadline-s 45]
  build.py --check-only --loader-source COPY_OF_build-003/source

Two images, both the run-006 loader (loader-diag-trig-hold-adt8-aln: NAT-020 build-003 loader + NAT-022 instrumentation +
NAT-027 aligned ADT accesses + the NAT-026 payload header fix) plus the NAT-044 patch and the unmodified NAT-042 reset module:

  loader-diag-reset     the reset reason is DOWNLOAD (0x12345601), the primary experiment
  loader-diag-reset-bl  the reset reason is BOOTLOADER (0x1234560d), the U4 alternative

Output: DIR/<image>/{Image,Image.payload,loader.elf,source/} and DIR/build.json (hashes, deadline, WDT, module hash)."""
import argparse
import hashlib
import importlib.util
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
N22 = HERE.parent / "nat-022"
N42 = HERE.parent / "nat-042" / "module"
SRC22 = N22 / "src"
SRC44 = HERE / "src"
REASONS = {"loader-diag-reset": ("S5E_REASON_DOWNLOAD", 0x12345601), "loader-diag-reset-bl": ("S5E_REASON_BOOTLOADER", 0x1234560D)}
MIN_MARGIN_S = 20          # the deadline must be at least this much before the watchdog


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


b22 = _load("nat022_build", N22 / "build.py")
p4 = _load("nat044_patch", HERE / "patch_loader4.py")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def cc(src, obj, extra, includes, werror=False):
    flags = [f for f in b22.FLAGS if werror or f != "-Werror"]
    b22.run(["zig", "cc", *flags, *extra, f"-I{includes}", "-c", src, "-o", obj])


def build_one(out, source, name, deadline_s):
    reason_name, reason = REASONS[name]
    d = out / name
    d.mkdir(parents=True)
    src = d / "source"
    shutil.copytree(source, src, ignore=shutil.ignore_patterns("out", ".git"))
    b22.run([sys.executable, "-I", N22 / "patch_loader.py", src, "--trig-hold", "--adt-aligned"])
    e = src / "shim/e1s-xnu"
    for f in ("marker.h", "markerlib.c"):
        shutil.copy(SRC22 / f, e)
    b22.run([sys.executable, "-I", HERE / "patch_loader4.py", src])
    wdt = p4.wdt_seconds((e / "guard.c").read_text())
    if not 0 < deadline_s <= wdt - MIN_MARGIN_S:
        raise SystemExit(f"deadline {deadline_s} s must be in (0, {wdt - MIN_MARGIN_S}] for a {wdt} s watchdog")
    for f in ("reset44.h", "markerlib4.c"):
        shutil.copy(SRC44 / f, e)
    for f in ("s5e9945_reset.h", "s5e9945_reset.c"):
        shutil.copy(N42 / f, e)
    names = ["start.S", "loader.c", "ui.c", "adt_patch.c", "gic.c", "fdt.c", "guard.c", "s5e9945.c", "markerlib4.c",
             "s5e9945_reset.c"]
    objs = []
    for c in names:
        extra = []
        if c == "markerlib4.c":
            extra = ["-DMK_TRIG=1", "-DMK_LOADER=1", f"-DNAT044_DEADLINE_S={deadline_s}", f"-DNAT044_REASON={reason_name}"]
        obj = d / (c + ".o")
        cc(e / c, obj, extra, e, werror=(c == "s5e9945_reset.c"))
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
    return d / "Image", wdt, reason


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
    for name in REASONS:
        img, wdt, reason = build_one(out, Path(a.loader_source), name, a.deadline_s)
        d = img.read_bytes()
        assert d[56:60] == b"ARM\x64" and struct.unpack_from("<Q", d, 8)[0] == 0x80000
        assert len(d) == struct.unpack_from("<Q", d, 16)[0] and len(d) < 1 << 20
        pl = img.parent / "Image.payload"
        images[name] = {"path": str(img.relative_to(out)), "sha256": sha(img), "bytes": len(d)}
        payloads[name] = {"path": str(pl.relative_to(out)), "sha256": sha(pl), "bytes": pl.stat().st_size}
        meta[name] = {"reason": f"{reason:#010x}", "deadline_s": a.deadline_s, "wdt_s": wdt}
    if a.check_only:
        print("ok", {k: v["bytes"] for k, v in images.items()})
        return
    (out / "build.json").write_text(json.dumps({
        "kind": "host-test", "device_used": False, "flashed": False, "images": images, "image_payloads": payloads,
        "image_meta": meta,
        "nat042_module": {f: sha(N42 / f) for f in ("s5e9945_reset.h", "s5e9945_reset.c")},
        "nat044_sources": {f: sha(SRC44 / f) for f in ("reset44.h", "markerlib4.c")} | {"patch_loader4.py": sha(HERE / "patch_loader4.py")},
        "payload_fixes": b22.payload_fixes, "commands": b22.log}, indent=1))
    print(json.dumps({n: {"Image": images[n]["sha256"], "Image.payload": payloads[n]["sha256"]} for n in images}, indent=1))


if __name__ == "__main__":
    main()
