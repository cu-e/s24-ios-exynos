#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-047: package the loader-diag-usbmon images into RECOVERY candidates.

    package.py --build artifacts/nat-047/build-002 --out artifacts/nat-047/package-001 [--only loader-diag-usbmon]

This is NAT-044's package.py, called unchanged: it reads only the build record's `image_payloads` and `images` tables, which NAT-047's
build.py writes in the same form. Host only: reads the pinned stock RECOVERY, writes new files, never opens a phone, refuses an
existing output directory. What goes into the RECOVERY image is `Image.payload` (the loader followed by the XNU payload and its ADT),
never the loader-only `Image`; the checks (payload hash equals the build record, payload verbatim at the recorded offset of the RECOVERY
image, record hash equals file hash) are NAT-044's. Output: <out>/<image>/{recovery.img,package.json} and <out>/package.json.
Hashes only are committed; the images stay under artifacts/ (gitignored)."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None):
    spec = importlib.util.spec_from_file_location("nat044_package", HERE.parent / "nat-044" / "package.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.main(argv)


if __name__ == "__main__":
    sys.exit(main())
