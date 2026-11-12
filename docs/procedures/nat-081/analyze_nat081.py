#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-081: the NAT-080 analyser (pass table rows 1-10 of the NAT-078 run) with the boot selection of sessions.py: when the collector archive holds more than one boot of
the same device and each later one is an exact replay of the earlier one's ring records, the last boot is judged. Same arguments, same output as analyze_nat080.py plus a
`nat081` key that says which boots were superseded and which capture errors were accepted. The pass table is not edited; nothing here reads a phone.

    analyze_nat081.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json --delivery RUN/delivery --root PADDED_ROOT --size N --sha256 H [--out F] [--log-out F]
"""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


S = _load("nat081_sessions", HERE / "sessions.py")
A80 = _load("nat081_nat080_analyze", PROC / "nat-080" / "analyze_nat080.py")
_analyze80 = A80.analyze


def analyze(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic=False, **kw):
    S.LAST.clear()
    undo = S.install(A80.A65.A49)
    try:
        out = _analyze80(root, events, report, delivery_dir, image_path, size, sha256, allow_synthetic, **kw)
    finally:
        undo()
    out["nat081"] = S.LAST.get("info")
    return out


def main(argv=None):
    A80.analyze = analyze
    try:
        return A80.main(argv)
    finally:
        A80.analyze = _analyze80


if __name__ == "__main__":
    sys.exit(main())
