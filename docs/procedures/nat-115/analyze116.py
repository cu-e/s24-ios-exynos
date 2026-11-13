#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-116 analyser: applies the pass rule fixed in research/notes/NAT-115-post-logo-diagnosis.md to a run's kernel text and
pixel report. Pure function of its inputs; it does not read the phone.

    analyze116.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON [--out OUT_JSON]

KERNEL_TEXT is the why=2 KL dump as text (nat-089 kl_reader text_of); PIXELS_JSON is decode113.py's --json output.
Verdicts: P-window first (the run answers anything at all), then exactly one of H1-frame / H2-cpu / H3-wait / H4-display / X-none.
"""
import argparse
import json
import re
import sys

LOGO_FNV = 0xd5b719ed          # NAT-113's three recorded frames (the boot Apple logo)
SPRINGBOARD = "SpringBoard"
BACKBOARDD = "backboardd"
TH_WAIT, TH_RUN = 0x01, 0x04
HINT_PORT_RECEIVE, HINT_PORT_SEND = 0x02, 0x04
FB_HINTS = ("IOMobileFramebuffer", "MiniIOMobileFramebuffer", "IOSurface")

RE_FED = re.compile(r"e1s_wdt: fed every 10 s for (\d+) s")
RE_CUT = re.compile(r"e1s_wdt: loader_return_after (\d+) cut to (\d+) s")
RE_NOTFED = re.compile(r"e1s_wdt: not fed: (.*)")
RE_STOP = re.compile(r"e1s_wdt: no longer fed after (\d+) feeds")
RE_SWAP = re.compile(r"^\[\s*([0-9.]+)\]: MiniIOMobileFramebuffer: swap (\d+) \(#\d+\): surfaces ([0-9 ]+),")
RE_THREAD = re.compile(r"waitdump: (\S+)\[(\d+)\] t(\d+) tid (\d+) state 0x([0-9a-f]+) hint (\d+) pri (-?\d+) cpu (\d+)\.(\d+)\+(\d+)\.(\d+) "
                       r"pc 0x([0-9a-f]+) lr 0x([0-9a-f]+) owner (-?\d+) ctx 0x([0-9a-f]+) ts (\S) (\d+) hops (\d+) svc (.*)$")
RE_PROC = re.compile(r"waitdump: (\S+)\[(\d+)\] threads (\d+) slide")


def parse(text):
    lines = text.splitlines()
    r = dict(fed=None, cut=None, not_fed=[], stopped_after=None, expired=False, swaps=[], threads=[], procs={}, waitdump=False)
    for ln in lines:
        if (m := RE_FED.search(ln)):
            r["fed"] = int(m.group(1))
        if (m := RE_CUT.search(ln)):
            r["cut"] = (int(m.group(1)), int(m.group(2)))
        if (m := RE_NOTFED.search(ln)):
            r["not_fed"].append(m.group(1).strip())
        if (m := RE_STOP.search(ln)):
            r["stopped_after"] = int(m.group(1))
        if "--- loader_return_after expired ---" in ln:
            r["expired"] = True
        if (m := RE_SWAP.search(ln)):
            r["swaps"].append(dict(t=float(m.group(1)), n=int(m.group(2)), surfaces=m.group(3).split()))
        if "waitdump: begin" in ln:
            r["waitdump"] = True
        if (m := RE_PROC.search(ln)):
            r["procs"][int(m.group(2))] = dict(name=m.group(1), threads=int(m.group(3)))
        if (m := RE_THREAD.search(ln)):
            g = m.groups()
            r["threads"].append(dict(name=g[0], pid=int(g[1]), n=int(g[2]), tid=int(g[3]), state=int(g[4], 16), hint=int(g[5]),
                                     pri=int(g[6]), cpu=int(g[7]) + int(g[8]) / 100 + int(g[9]) + int(g[10]) / 100,
                                     owner=int(g[13]), ts=g[15], ts_ctx=int(g[16]), svc=g[18].strip()))
    return r


def name_of(pid, r):
    p = r["procs"].get(pid)
    return p["name"] if p else None


def classify(r, pixels):
    out = dict(p_window=False, verdict="X-none", reasons=[])
    # P-window: the feed ran, the timed return happened, the report arrived
    window_ok = r["fed"] is not None and r["cut"] is None and r["expired"] and pixels.get("complete") is True
    out["p_window"] = window_ok
    if not window_ok:
        out["reasons"].append("P-window not met: fed=%r cut=%r not_fed=%r expired=%r pixels_complete=%r"
                              % (r["fed"], r["cut"], r["not_fed"], r["expired"], pixels.get("complete")))
        out["verdict"] = "X-window"
        return out
    frames = pixels.get("frames") or []
    new = [f for f in frames if f.get("fnv") != LOGO_FNV and f.get("nzb", 0) > 0]
    out["frames"] = len(frames)
    out["new_frames"] = len(new)
    late_swaps = [s for s in r["swaps"] if s["n"] > 3]
    out["swaps"] = len(r["swaps"])
    if new:
        out["verdict"] = "H1-frame"
        out["reasons"].append("%d recorded frame(s) differ from the logo (fnv %s)" % (len(new), sorted({hex(f['fnv']) for f in new})))
        return out
    sb = sorted([t for t in r["threads"] if t["name"] == SPRINGBOARD], key=lambda t: t["n"])
    bb = sorted([t for t in r["threads"] if t["name"] == BACKBOARDD], key=lambda t: t["n"])
    if not r["waitdump"] or not sb:
        out["reasons"].append("no SpringBoard threads in the wait dump (waitdump=%r)" % r["waitdump"])
        return out
    main = sb[0]
    out["springboard_main"] = main
    if main["state"] & TH_RUN and not main["state"] & TH_WAIT:
        out["verdict"] = "H2-cpu"
        out["reasons"].append("SpringBoard's first thread is runnable (state 0x%x)" % main["state"])
        return out
    if main["state"] & TH_WAIT:
        owner = main["owner"] if main["hint"] in (HINT_PORT_RECEIVE, HINT_PORT_SEND) and main["owner"] > 0 else None
        if owner is None and main["ts"] == "P" and main["ts_ctx"] > 0:
            owner = main["ts_ctx"]
        oname = name_of(owner, r) if owner else None
        if owner is not None and (oname == BACKBOARDD or any(h in main["svc"] for h in FB_HINTS)):
            out["verdict"] = "H4-display"
            out["reasons"].append("SpringBoard waits on %s[%s] svc %r" % (oname, owner, main["svc"]))
            return out
        if owner is not None:
            out["verdict"] = "H3-wait"
            out["waits_on"] = dict(pid=owner, name=oname, svc=main["svc"], hint=main["hint"])
            out["reasons"].append("SpringBoard's first thread waits (hint %d) on pid %s %s svc %r" % (main["hint"], owner, oname, main["svc"]))
            return out
        if bb and bb[0]["state"] & TH_WAIT and any(h in bb[0]["svc"] for h in FB_HINTS):
            out["verdict"] = "H4-display"
            out["reasons"].append("backboardd waits on the framebuffer/IOSurface: svc %r" % bb[0]["svc"])
            return out
        out["reasons"].append("SpringBoard waits (hint %d) but no owner is readable: %r" % (main["hint"], main))
    out["late_swaps"] = len(late_swaps)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel-text", required=True)
    ap.add_argument("--pixels", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    r = parse(open(a.kernel_text, errors="replace").read())
    res = classify(r, json.load(open(a.pixels)))
    res["parsed"] = dict(fed=r["fed"], cut=r["cut"], not_fed=r["not_fed"], stopped_after=r["stopped_after"], expired=r["expired"],
                         swaps=r["swaps"], threads=len(r["threads"]), procs=r["procs"])
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("p_window", "verdict", "reasons")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
