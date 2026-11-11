#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-067: the verdict of one native run of loader-diag-xnu-ne1-usb.

    analyze_nat067.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json [--out RUN/analysis.json] [--log-out RUN/kernel-log.txt]

NAT-065's analyser (analyze_nat065.py: NAT-062's verdict on the log chain, plus `root` = what the kernel's own text says about the root device and PID 1) called under
this image's name: its module-level IMAGE is replaced for the call (boot id = FNV-1a-64 of the image name, banner `NAT047 <name> deadline_s=60 fault=0`).
Nothing else is changed; `root.outcome` still separates probe-ran-to-exit (PASS for the run's question), probe-no-console, init-exited-other, init-killed,
root-device-missing, other-panic and no-panic-text. It reads delivered text and decides nothing about the phone."""
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-ne1-usb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A65 = _load("nat067_nat065_analyze", PROC / "nat-065" / "analyze_nat065.py")
classify_root = A65.classify_root
write_log = A65.write_log
_ANALYZE65 = A65.analyze


def analyze(root, events, report, allow_synthetic=False, **kw):
    old = A65.IMAGE
    A65.IMAGE = IMAGE
    try:
        return _ANALYZE65(root, events, report, allow_synthetic, **kw)
    finally:
        A65.IMAGE = old


def main(argv=None):
    A65.analyze = analyze              # main() of NAT-065 calls analyze() by module-global name
    try:
        return A65.main(argv)
    finally:
        A65.analyze = _ANALYZE65


if __name__ == "__main__":
    sys.exit(main())
