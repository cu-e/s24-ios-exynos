#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-075: the verdict of one native run of loader-diag-xnu-bigwin-md1, and what the kernel's own text says about the big window and the second ramdisk.

    analyze_nat075.py --archive RUN/archive --events RUN/usb-events.jsonl --report RUN/report.json [--out RUN/analysis.json] [--log-out RUN/kernel-log.txt]

NAT-065's analyser (the log chain judged by NAT-062's, plus `root`) is called under this image's name, as NAT-067's wrapper does. This module adds `bigwin`, a reading of
the delivered kernel text and of the USB return, fixed before the run (docs/procedures/nat-074/decision-draft.md, promoted to the NAT-075 decision file):

  md        every `Added memory device mdN/rmdN (...) at VA for SIZE` line; `md1_ok` = md1 present with SIZE == 0x93908000 (2,475,720,704 B, the reserve)
  vm        `vm_page_bootstrap: FREE free pages, WIRED wired pages`; total = FREE + WIRED; the page size is the one (4 KiB or 16 KiB) for which total * size is the 4096 MiB window
            within 2 %. For the NAT-068 run (512 MiB window, 4 KiB pages) the total was exactly window / 4096.
  return    the host's first return of the phone (usb.first_return), classified against the two clocks measured before this run:
            * NAT-068 (decision 0028): 1209:0001 enumerated at +26.7 s, the loader's 60 s software deadline reset the phone 57.2 s later, Download Mode `SAMSUNG USB` at +87.7 s
              (a loader second is 0.95..1.0 host seconds). With the cap at 150 s the same reset path is expected at +87.7 + 90 * (0.95..1.0) = +173.2 .. +177.7 s;
              `cap-reset` = a Download Mode return at +165 .. +195 s.
            * runs 001-009 (NAT-048): an unpetted 83 s hardware watchdog ends in SEC_UPLOAD at +95 s (+-10 s); `watchdog-upload` = an `upload` return in that window, i.e. the pet did
              not keep the watchdog from expiring.
            Everything else is named for what it is: download-other-early / download-other-late, upload-other (an upload return outside the +95 s window: a pet that worked for a
            while, or a different reset), not-download-<class>, no-return-seen.
  loader    from the loader's own text records of the archived boot: `window from DTB=... win=BASE win size=SIZE`, the last `zero_bytes=`, `clean_full_window_begin/end`, and any
            refusal text ("does not fit", "bad payload header"). Expected for this image: SIZE 4096 MiB, final zero_bytes 146,259,968 (the three-span clear, 139.48 MiB),
            a clean span of the whole window. Reported, not part of the rule: they say which step the loader reached when the kernel text is missing.
  pass      chain verdict PASS, root.outcome probe-ran-to-exit, md1_ok, return class cap-reset. The page size and the loader readings are reported, not part of the rule (the rule
            asks whether the kernel survives them, and root.outcome carries that).

It reads delivered text and a host-side observation and decides nothing about the phone."""
import importlib.util
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
IMAGE = "loader-diag-xnu-bigwin-md1"
WINDOW = 4096 << 20
RESERVE = 2475720704
CAP_S, WDT_S = 150, 83
CAP_RETURN = (165.0, 195.0)       # see the module docstring: NAT-068's +87.7 s for a 60 s deadline, scaled to 150 s, with margins
BASELINE_RETURN_S, BASELINE_DEADLINE_S = 87.72, 60
EXPECT_ZERO_BYTES = 146259968
WIN_LINE = re.compile(r"window from DTB=0x([0-9a-fA-F]+) win=0x([0-9a-fA-F]+) win size=0x([0-9a-fA-F]+)")
ZERO_LINE = re.compile(r"zero_bytes=0x([0-9a-fA-F]+)")
CLEAN_B = re.compile(r"clean_full_window_begin=0x([0-9a-fA-F]+)")
CLEAN_E = re.compile(r"clean_full_window_end=0x([0-9a-fA-F]+)")
REFUSALS = ("does not fit", "bad payload header")
MD_LINE = re.compile(r"Added memory device (md\d+)/rmd\d+ \(([0-9A-Fa-f]+)/([0-9A-Fa-f]+)\) at ([0-9A-Fa-f]+) for ([0-9A-Fa-f]+)")
VM_LINE = re.compile(r"vm_page_bootstrap: (\d+) free pages, (\d+) wired pages")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


A65 = _load("nat075_nat065_analyze", PROC / "nat-065" / "analyze_nat065.py")
classify_root = A65.classify_root
write_log = A65.write_log
_ANALYZE65 = A65.analyze


def read_md(text):
    return [dict(name=m.group(1), size=int(m.group(5), 16), base_field=m.group(2), size_field=m.group(3), va=m.group(4)) for m in MD_LINE.finditer(text)]


def read_loader(lines):
    """The loader's own readings from the text records of one archived boot (a list of strings)."""
    text = "\n".join(lines or [])
    w = WIN_LINE.search(text)
    zs = [int(m.group(1), 16) for m in ZERO_LINE.finditer(text)]
    cb, ce = CLEAN_B.search(text), CLEAN_E.search(text)
    span = int(ce.group(1), 16) - int(cb.group(1), 16) if cb and ce else None
    return dict(found=bool(lines), window_base=int(w.group(2), 16) if w else None, window_size=int(w.group(3), 16) if w else None,
                window_ok=bool(w) and int(w.group(3), 16) == WINDOW, zero_bytes_final=zs[-1] if zs else None, zero_ok=bool(zs) and zs[-1] == EXPECT_ZERO_BYTES,
                clean_span=span, clean_ok=span == WINDOW, refusals=[r for r in REFUSALS if r in text])


def read_vm(text):
    m = VM_LINE.search(text)
    if not m:
        return dict(found=False, free=None, wired=None, total=None, page_size=None)
    free, wired = int(m.group(1)), int(m.group(2))
    total = free + wired
    page = None
    for size in (4096, 16384):
        if abs(total * size - WINDOW) <= WINDOW // 50:
            page = size
    return dict(found=True, free=free, wired=wired, total=total, page_size=page, bytes_if_4k=total * 4096, bytes_if_16k=total * 16384)


def upload_window():
    ar = A65.A49.AR
    return ar.BASELINE_UPLOAD_S - ar.BASELINE_TOLERANCE_S, ar.BASELINE_UPLOAD_S + ar.BASELINE_TOLERANCE_S


def classify_return(first_return):
    if not first_return:
        return dict(klass=None, dt=None, cls="no-return-seen")
    dt, klass = first_return.get("dt"), first_return.get("klass")
    lo, hi = upload_window()
    if klass == "download":
        cls = "cap-reset" if CAP_RETURN[0] <= dt <= CAP_RETURN[1] else "download-other-early" if dt < CAP_RETURN[0] else "download-other-late"
    elif klass == "upload":
        cls = "watchdog-upload" if lo <= dt <= hi else "upload-other"
    else:
        cls = "not-download-" + str(klass)
    return dict(klass=klass, dt=dt, cls=cls)


def readings(text, usb, verdict, root_outcome):
    md = read_md(text)
    md1_ok = any(d["name"] == "md1" and d["size"] == RESERVE for d in md)
    ret = classify_return((usb or {}).get("first_return"))
    rule = dict(chain_pass=verdict == "PASS", probe_ran=root_outcome == "probe-ran-to-exit", md1_ok=md1_ok, cap_reset=ret["cls"] == "cap-reset")
    rule["pass"] = all(rule.values())
    return dict(md=md, md1_ok=md1_ok, vm=read_vm(text), **{"return": ret}, rule=rule)


def analyze(root, events, report, allow_synthetic=False, **kw):
    old = A65.IMAGE
    A65.IMAGE = IMAGE
    try:
        out = _ANALYZE65(root, events, report, allow_synthetic, **kw)
    finally:
        A65.IMAGE = old
    texts = (out.get("kernel_log") or {}).get("texts") or {}
    text = "\n".join(texts[k] for k in sorted(texts)) if texts else ""
    out["bigwin"] = readings(text, out.get("usb"), out.get("verdict"), (out.get("root") or {}).get("outcome"))
    lines = []
    boot = out.get("boot")
    if boot and boot.get("name"):
        lines = A65.A59.boot_texts(root, boot["name"])
    out["bigwin"]["loader"] = read_loader(lines)
    return out


def main(argv=None):
    A65.analyze = analyze              # main() of NAT-065 calls analyze() by module-global name
    try:
        return A65.main(argv)
    finally:
        A65.analyze = _ANALYZE65


if __name__ == "__main__":
    sys.exit(main())
