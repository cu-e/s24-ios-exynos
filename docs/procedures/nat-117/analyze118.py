#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-118 analyser (rule fixed by NAT-117 before the run): what SpringBoard does after the /product node was added.

    analyze118.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON [--out OUT_JSON]

KERNEL_TEXT is the why=2 KL dump as text (nat-089 kl_reader text_of); PIXELS_JSON is decode113.py's --json output.
Pure function of its inputs; it does not read the phone.

Window: `W-ok` when the timed return happened (`--- loader_return_after expired ---`), no kernel panic text precedes the return,
and the pixel report is complete; otherwise `X-window` (nothing below is judged). The watchdog-feed line is reported but not
required (NAT-116: it can fall into the log gap between head and tail).

Then the first matching verdict:
  F1-new-frame     a recorded frame differs from the boot logo (FNV 0xd5b719ed) and has non-zero bytes  -> look at the thumbnail
  A1-same-abort    SpringBoard still aborts on the bounding-path bitmap                                   -> /product hypothesis refuted
  A2-other-abort   SpringBoard aborts (userabort / SIGABRT / uncaught exception) for another reason       -> that reason is next
  S1-alive-no-frame SpringBoard never aborts and no new frame                                             -> wait states next
"""
import argparse
import json
import re
import sys

LOGO_FNV = 0xd5b719ed
BOUNDING = "Failed to load bounding path bitmap data"
RE_ABORT = re.compile(r"userabort: SpringBoard\[(\d+)\] aborts")
RE_EXC = re.compile(r"SpringBoard\[(\d+):\d+\] \*\*\* Terminating app due to uncaught exception '([^']+)', reason: '(.*)")
RE_ASSERT = re.compile(r"SpringBoard\[(\d+):\d+\] \*\*\* Assertion failure in (.*)")
RE_SIGABRT = re.compile(r"com\.apple\.SpringBoard \[(\d+)\]\) <Notice>: exited due to (SIG\w+)")
RE_FED = re.compile(r"e1s_wdt: fed every 10 s for (\d+) s")
RE_CUT = re.compile(r"e1s_wdt: loader_return_after (\d+) cut to (\d+) s")
RE_SWAP = re.compile(r"MiniIOMobileFramebuffer: swap (\d+) \(#\d+\): surfaces ([0-9 ]+),")


def parse(text):
    r = dict(expired=False, panic_before_return=False, panic=None, fed=None, cut=None, aborts=[], exceptions=[], asserts=[],
             exits=[], swaps=[])
    seen_expired = False
    for ln in text.splitlines():
        if "--- loader_return_after expired ---" in ln:
            r["expired"] = seen_expired = True
        if ln.startswith("panic(") and r["panic"] is None:
            r["panic"] = ln.strip()
        if (m := RE_FED.search(ln)):
            r["fed"] = int(m.group(1))
        if (m := RE_CUT.search(ln)):
            r["cut"] = (int(m.group(1)), int(m.group(2)))
        if (m := RE_ABORT.search(ln)):
            r["aborts"].append(int(m.group(1)))
        if (m := RE_EXC.search(ln)):
            r["exceptions"].append(dict(pid=int(m.group(1)), type=m.group(2), reason=m.group(3)))
        if (m := RE_ASSERT.search(ln)):
            r["asserts"].append(dict(pid=int(m.group(1)), where=m.group(2).strip()))
        if (m := RE_SIGABRT.search(ln)):
            r["exits"].append(dict(pid=int(m.group(1)), signal=m.group(2)))
        if (m := RE_SWAP.search(ln)):
            r["swaps"].append(dict(n=int(m.group(1)), surfaces=m.group(2).split()))
    # A panic string printed before the timed return means the kernel died on its own (the panic buffer section follows the
    # kernel message buffer, so look for the banner of a timed return in the text before the first "panic(" of the buffer).
    if r["panic"] is not None:
        idx_p = text.find(r["panic"])
        idx_e = text.find("--- loader_return_after expired ---")
        r["panic_before_return"] = idx_e < 0 or idx_p < idx_e
    return r


def classify(r, pixels):
    out = dict(window=None, verdict=None, reasons=[])
    ok = r["expired"] and not r["panic_before_return"] and pixels.get("complete") is True
    out["window"] = "W-ok" if ok else "X-window"
    out["feed"] = dict(fed=r["fed"], cut=r["cut"])
    if not ok:
        out["verdict"] = "X-window"
        out["reasons"].append("expired=%r panic_before_return=%r panic=%r pixels_complete=%r"
                              % (r["expired"], r["panic_before_return"], r["panic"], pixels.get("complete")))
        return out
    frames = pixels.get("frames") or []
    new = [f for f in frames if f.get("fnv") != LOGO_FNV and f.get("nzb", 0) > 0]
    out.update(frames=len(frames), new_frames=len(new), panel_nonzero=pixels.get("panel_nonzero"), swaps=len(r["swaps"]),
               springboard_aborts=len(set(r["aborts"]) | {e["pid"] for e in r["exits"]}))
    if new:
        out["verdict"] = "F1-new-frame"
        out["reasons"].append("%d recorded frame(s) differ from the logo: %s" % (len(new), sorted({hex(f["fnv"]) for f in new})))
        return out
    bounding = [e for e in r["exceptions"] if BOUNDING in e["reason"]]
    if bounding:
        out["verdict"] = "A1-same-abort"
        out["reasons"].append("%d SpringBoard exception(s) still on the bounding-path bitmap: %s" % (len(bounding), bounding[0]["reason"][:160]))
        return out
    if r["aborts"] or r["exits"] or r["exceptions"]:
        out["verdict"] = "A2-other-abort"
        first = r["exceptions"][0] if r["exceptions"] else None
        out["first_exception"] = first
        out["first_assert"] = r["asserts"][0] if r["asserts"] else None
        out["reasons"].append("SpringBoard aborts %d time(s); first exception %r" % (out["springboard_aborts"], first))
        return out
    out["verdict"] = "S1-alive-no-frame"
    out["reasons"].append("no SpringBoard abort and no frame other than the logo")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel-text", required=True)
    ap.add_argument("--pixels", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    r = parse(open(a.kernel_text, errors="replace").read())
    res = classify(r, json.load(open(a.pixels)))
    if a.out:
        json.dump(dict(res, parsed=r), open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("window", "verdict", "reasons")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
