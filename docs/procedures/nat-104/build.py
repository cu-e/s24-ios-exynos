#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-104: build loader-diag-xnu-hb2-md1 on the host. Never opens a phone or writes a partition.

This is NAT-102's heartbeat image (`loader-diag-xnu-hb-md1`: quiet Stage A + NAT-101's `/redwood/bin/hb &` in `/etc/rc`,
same kernel, same ADT, same 4 MiB `md0` root, same cmdline structure) with one B8 log-window fix applied to the derived
build tree's `src/glue62_impl.h`:

  * `NAT062_BURST`: 8192u -> 4096u (smaller bursts relative to the 32 KiB USB ring)
  * `NAT062_TAIL_RETURN`: 32768u -> 262144u (256 KiB return tail, 262144 % 96 == 64; returns the entire ~116 KiB log with gap=0)
  * 10 * N62_WAIT() (5 s USB poll settle) at entry to `NAT062_WHY_RETURN` before emitting `KL begin` so the host collector
    reconnects and drains boot-1 ring backlog before records begin arriving.

Image name `loader-diag-xnu-hb2-md1` and tag `nat_attempt=NAT104-hb2` keep NAT-102's 18-byte tag length."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-hb2-md1"
NEW_TAG = "nat_attempt=NAT104-hb2"
MD0_BYTES = 4194304
MD0_SHA256 = "97f9b5d8a5c7d02ebf2d527dedddbc6a043d69a7191339d8d5dbe4fe7144e58c"
BURST_NEW = 4096
TAIL_RETURN_NEW = 262144
RETURN_SETTLE_WAITS = 10

PATCH_RULES = (
    ("burst", "#define NAT062_BURST\t\t8192u", "#define NAT062_BURST\t\t4096u"),
    ("tail_return", "#define NAT062_TAIL_RETURN\t32768u", "#define NAT062_TAIL_RETURN\t262144u"),
    (
        "return_settle",
        "\tN62_EMIT(b, p);\n\tn62_range(&o, x0, len - tail, len);",
        "\tif (why == NAT062_WHY_RETURN) {\n\t\tfor (uint32_t w = 0; w < 10u; w++)\n\t\t\tN62_WAIT();\n\t}\n\tN62_EMIT(b, p);\n\tn62_range(&o, x0, len - tail, len);",
    ),
)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b102 = _load("nat104_nat102_build", PROC / "nat-102" / "build.py")
b87 = b102.b87
b62 = b87.b85.b65.b62
sha = b102.sha
argv_value = b102.argv_value


def patch_glue104(path):
    """Apply the three B8 window/pacing replacements to the derived tree's `glue62_impl.h` and return its new SHA-256."""
    p = Path(path)
    text = p.read_text()
    for label, old, new in PATCH_RULES:
        count = text.count(old)
        if count != 1:
            raise SystemExit("patch_glue104 %s: expected 1 occurrence in %s, found %d" % (label, p, count))
        text = text.replace(old, new)
    p.write_text(text)
    return sha(text.encode())


def main():
    argv_saved = list(sys.argv)
    md0 = argv_value(argv_saved, "--ramdisk")
    if "--check-only" not in argv_saved:
        if md0 is None:
            raise SystemExit("--ramdisk is required: the NAT-101 small root")
        data = Path(md0).read_bytes()
        if len(data) != MD0_BYTES:
            raise SystemExit("the small root is %d bytes, not %d" % (len(data), MD0_BYTES))
        md0_sha = hashlib.sha256(data).hexdigest()
        if md0_sha != MD0_SHA256:
            raise SystemExit("the small root is sha256 %s, not the pinned %s" % (md0_sha, MD0_SHA256))
    saved = (b87.NAME, b87.NEW_TAG, b62.prepare_tree)
    orig_prepare = b62.prepare_tree
    patched_info = {}

    def prepare_tree104(src, deadline_s, final=True):
        wdt = orig_prepare(src, deadline_s, final)
        if final:
            patched_info["glue62_impl_sha256"] = patch_glue104(Path(src) / "shim" / "e1s-xnu" / "glue62_impl.h")
        return wdt

    b87.NAME, b87.NEW_TAG, b62.prepare_tree = NAME, NEW_TAG, prepare_tree104
    try:
        b87.main()
    finally:
        b87.NAME, b87.NEW_TAG, b62.prepare_tree = saved
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
        raise SystemExit("build.json records md0 %r, expected %s (%d bytes)" % (md0_rec, md0_sha, MD0_BYTES))
    change = d.get("nat087_changes") or {}
    if change.get("image_name") != NAME or change.get("cmdline_tag") != NEW_TAG:
        raise SystemExit("build.json does not carry this image's name and tag: %r" % (change,))
    if "glue62_impl_sha256" not in patched_info:
        raise SystemExit("glue62_impl.h hook never ran during prepare_tree")
    d["nat104_sources"] = {"build.py": sha((HERE / "build.py").read_bytes())}
    d["nat104_changes"] = {
        "image_name": NAME,
        "cmdline_tag": NEW_TAG,
        "md0_sha256": md0_sha,
        "md0_bytes": MD0_BYTES,
        "cmdline": change.get("cmdline"),
        "glue62_impl_sha256": patched_info["glue62_impl_sha256"],
        "burst_bytes": BURST_NEW,
        "tail_return_bytes": TAIL_RETURN_NEW,
        "return_settle_waits": RETURN_SETTLE_WAITS,
    }
    d["nat104_note"] = (
        "NAT-102's image with glue62_impl.h updated for B8 observability (TAIL_RETURN=262144, BURST=4096, 10x N62_WAIT before why=2 KL begin); nothing ran on a phone"
    )
    rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
