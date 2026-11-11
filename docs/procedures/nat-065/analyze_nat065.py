#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-065: the verdict of one native run of loader-diag-xnu-md0-usb, and what the kernel's own text says about the root device and PID 1.

    analyze_nat065.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json [--out RUN/analysis.json] [--log-out RUN/kernel-log.txt]

The log chain (27 stop notes, the dump at the last stop, the kernel's own return, the second dump, HOLD, no drop) is judged by NAT-062's analyser, called
unchanged under this image's name (its boot id is the FNV-1a-64 of the image name). This module adds `root`: a classification of what the delivered kernel
text shows about the step NAT-063 ended at (IOFindBSDRoot) and the NAT-065 probe init (docs/procedures/nat-065/src/probe-init.S):

  probe-ran-to-exit    the kernel panicked with "initproc failed to start ... exit status 80+N": the probe was exec'd as PID N, opened the console, slept 1 s and exited
  probe-no-console     exit status 96: the probe ran but could not open /dev/console
  init-exited-other    PID 1 ran and exited with another status (the number is reported)
  init-killed          PID 1 ended by a signal (the number is reported)
  root-device-missing  the NAT-063 panic again: md0 was not configured (the ramdisk did not reach the kernel)
  other-panic          another panic (its first line is reported)
  no-panic-text        no panic text arrived (a cut log, a run that never panicked, or a log that did not arrive)

`root` is a reading of the received text, nothing more: a PASS of the chain with `root.outcome` other than probe-ran-to-exit is a delivered log, not a working
PID 1. The kernel's microsecond field is inflated by 1.024 (rtclock_usec_divisor is the integer 25 for the 25.6 MHz timebase), so the stamps are normalised
here: kernel seconds = sec + field / 1,024,000 (NAT-064)."""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-md0-usb"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A62 = _load("nat065_nat062_analyze", PROC / "nat-062" / "analyze_nat062.py")
A59, D52, A49, STOP_LIST = A62.A59, A62.D52, A62.A49, A62.STOP_LIST
write_log = A62.write_log

STAMP = re.compile(r"^\[\s*(\d+)\.(\d+)\]:\s*(.*?)\r?$", re.M)
PANIC = re.compile(r"^panic\(cpu \d+ caller 0x[0-9a-f]+\): (.*?)\r?$", re.M)
INIT_EXIT = re.compile(r"initproc (?:exited|failed to start) -- no exit reason available -- \(signal (\d+), exit status (\d+)")
INIT_EXIT_PRINTF = re.compile(r"pid (\d+) exited -- no exit reason available -- \(signal (\d+), exit (\d+)\)")
BSD_ROOT = re.compile(r"BSD root: (md\d+), major (\d+), minor (\d+)")
BANNER = re.compile(r"SWEET userspace: init running as PID (\d)")
DONE = "SWEET probe: done, exiting"
USEC_PER_SEC_FIELD = 1024000            # NAT-064: the field runs to 1,024,000 per real second at the 25.6 MHz timebase


def kernel_seconds(sec, field):
    return int(sec) + int(field) / USEC_PER_SEC_FIELD


def stamp_of(text, needle):
    """Kernel seconds of the first stamped line containing needle (a str or a compiled regex), or None."""
    for m in STAMP.finditer(text):
        body = m.group(3)
        if (needle.search(body) if hasattr(needle, "search") else needle in body):
            return kernel_seconds(m.group(1), m.group(2))
    return None


def classify_root(texts):
    """`texts`: {key: reconstructed dump text} from kernel_log. -> dict, see the module docstring."""
    text = "\n".join(texts[k] for k in sorted(texts)) if texts else ""
    out = dict(outcome="no-panic-text", exit_status=None, signal=None, pid=None, panic=None, bsd_root=None, bang_bsd="!BSD" in text,
               banner_seen=False, done_seen=DONE in text, init_run_s=None, sleep_s=None, text_bytes=len(text))
    m = BSD_ROOT.search(text)
    if m:
        out["bsd_root"] = dict(device=m.group(1), major=int(m.group(2)), minor=int(m.group(3)))
    m = BANNER.search(text)
    if m:
        out["banner_seen"] = True
        out["pid"] = int(m.group(1))
    m = PANIC.search(text)
    if m:
        out["panic"] = m.group(1)
    mi = INIT_EXIT.search(out["panic"] or "")
    if mi:
        sig, status = int(mi.group(1)), int(mi.group(2))
        out["signal"], out["exit_status"] = sig, status
        if sig:
            out["outcome"] = "init-killed"
        elif status == 96:
            out["outcome"] = "probe-no-console"
        elif 0x50 < status <= 0x59:
            out["outcome"] = "probe-ran-to-exit"
            out["pid"] = status - 0x50
        else:
            out["outcome"] = "init-exited-other"
    elif out["panic"] is not None:
        out["outcome"] = "root-device-missing" if "specified root memory device" in out["panic"] else "other-panic"
    t_root = stamp_of(text, BSD_ROOT)
    t_exit = stamp_of(text, INIT_EXIT_PRINTF)
    if t_root is not None and t_exit is not None and t_exit >= t_root:
        out["init_run_s"] = round(t_exit - t_root, 6)
    t_b, t_d = stamp_of(text, BANNER), stamp_of(text, DONE)
    if t_b is not None and t_d is not None and t_d >= t_b:
        out["sleep_s"] = round(t_d - t_b, 6)
    return out


def analyze(root, events, report, allow_synthetic=False, deadline=A59.DEADLINE_S, wdt=A59.WDT_S):
    """NAT-062's analysis under this image's name, plus `root`."""
    old = A62.IMAGE
    A62.IMAGE = IMAGE
    try:
        out = A62.analyze(root, events, report, allow_synthetic, deadline, wdt)
    finally:
        A62.IMAGE = old
    out["image"] = IMAGE
    kl = out.get("kernel_log")
    out["root"] = classify_root((kl or {}).get("texts") or {})
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--events", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out")
    ap.add_argument("--log-out")
    ap.add_argument("--allow-synthetic", action="store_true", help="host tests: label the verdict simulated-* instead of refusing it")
    a = ap.parse_args(argv)
    events, _ = A49.read_jsonl(a.events)
    report = A49.read_json(a.report) or {}
    res = analyze(a.archive, events, report, a.allow_synthetic)
    text = json.dumps(res, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")
    if a.log_out:
        write_log(res, a.log_out)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
