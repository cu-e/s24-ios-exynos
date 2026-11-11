#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-059: build loader-diag-xnu-ckpt4-usb on the host. Never opens a phone or writes a partition.

  build.py --out DIR --loader-source COPY_OF_build-003/source [--stops 11,30,...,21] [--deadline-s 60] [--service-tenths 3]
  build.py --check-only --loader-source COPY_OF_build-003/source

This is NAT-052's build (docs/procedures/nat-052/build.py: NAT-036 + NAT-044 + NAT-047 + the NAT-052 glue) with exactly two differences:
the image name, and one more patch step after NAT-052's own (patch_ckpt59.py: the stops 17..21 and the TTBR0 the stub gives back after
arm_vm_init). NAT-052's module is loaded and its `NAME`, `prepare_tree` and the default stop list are replaced for the duration of the
build, so that its code (compile flags, link, payload fix, append_payload) is used unchanged. The default list is the 17 NAT-052 stops
plus 17,18,19,20,21.

Output: DIR/loader-diag-xnu-ckpt4-usb/{Image,Image.payload,loader.elf,source/} and DIR/build.json."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
NAME = "loader-diag-xnu-ckpt4-usb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


b52 = _load("nat052_build", PROC / "nat-052" / "build.py")
p59 = _load("nat059_patch", HERE / "patch_ckpt59.py")
b36 = b52.b36
DEFAULT_STOPS = p59.STOPS
_prepare_tree52 = b52.prepare_tree


def prepare_tree(src, deadline_s, final=True):
    """NAT-052's prepare_tree, then patch_ckpt59.py over its ckpt3.c/ckpt3.h (final=True only, as NAT-052's own last patch)."""
    wdt = _prepare_tree52(src, deadline_s, final)
    if final:
        b52.b22.run([sys.executable, "-I", HERE / "patch_ckpt59.py", src])
    return wdt


def main():
    b52.NAME = NAME
    b52.prepare_tree = prepare_tree
    b36.DEFAULT_STOPS = DEFAULT_STOPS
    b52.b22.payload_fixes.clear()
    b52.main()
    # b52.main() recorded its own sources; add the NAT-059 ones next to them when a build record was written.
    argv = sys.argv
    if "--out" in argv and "--check-only" not in argv:
        import hashlib
        import json
        out = Path(argv[argv.index("--out") + 1])
        rec = out / "build.json"
        if rec.exists():
            d = json.loads(rec.read_text())
            d["nat059_sources"] = {"patch_ckpt59.py": hashlib.sha256((HERE / "patch_ckpt59.py").read_bytes()).hexdigest(),
                                   "build.py": hashlib.sha256((HERE / "build.py").read_bytes()).hexdigest()}
            d["nat052_sources_note"] = "the NAT-052 / NAT-036 hashes above are of the unpatched sources; patch_ckpt59.py rewrites ckpt3.c and ckpt3.h in the derived tree"
            rec.write_text(json.dumps(d, indent=1))


if __name__ == "__main__":
    main()
