#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-120 analyser (rule fixed by NAT-119 before the run): did the kernel trigger the panel while iOS ran?

    analyze120.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON [--owner-observation TEXT] [--out OUT_JSON]

Log verdict, first match:
  X-window       no timed return, a panic before it, or the pixel report incomplete
  D0-no-kick     no `e1s_decon: kick` line (boot-arg off, mapping failed, or `not kicked`; the line is quoted)
  D1-kick-frozen kicks happened but FRAME_COUNT did not advance between any two kicks
  D2-refreshing  FRAME_COUNT advanced between kicks: the panel was refreshing while iOS ran; the rate is reported
Plus, reported, not judged: SpringBoard aborts (analyze118 rule), new frames, panel non-black count.
The owner's observation is recorded verbatim next to the verdict and never changes it.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nat-117"))
import analyze118 as A118  # noqa: E402

RE_KICK = re.compile(r"^\[\s*([0-9.]+)\]: e1s_decon: kick (\d+) GLOBAL_CON 0x([0-9a-f]+) TRIG_CON 0x([0-9a-f]+) -> 0x([0-9a-f]+) "
                     r"FRAME_COUNT (\d+) \(\+(\d+)\)")
RE_NOT = re.compile(r"e1s_decon: (not kicked: .*|no mapping)")


def parse(text):
    kicks, nots = [], []
    for ln in text.splitlines():
        if (m := RE_KICK.search(ln)):
            kicks.append(dict(t=float(m.group(1)), n=int(m.group(2)), gc=int(m.group(3), 16), tc0=int(m.group(4), 16),
                              tc1=int(m.group(5), 16), fc=int(m.group(6)), delta=int(m.group(7))))
        elif (m := RE_NOT.search(ln)):
            nots.append(m.group(1).strip())
    return dict(kicks=kicks, not_kicked=nots)


def classify(text, pixels):
    r118 = A118.parse(text)
    base = A118.classify(r118, pixels)
    d = parse(text)
    out = dict(window=base["window"], ios=base["verdict"], kicks=len(d["kicks"]), not_kicked=d["not_kicked"], reasons=[])
    if base["window"] != "W-ok":
        out["verdict"] = "X-window"
        out["reasons"] += base["reasons"]
        return out
    if not d["kicks"]:
        out["verdict"] = "D0-no-kick"
        out["reasons"].append("no kick line; %r" % d["not_kicked"])
        return out
    rates = []
    for a, b in zip(d["kicks"], d["kicks"][1:]):
        dt = b["t"] - a["t"]
        if dt > 0:
            rates.append(((b["fc"] - a["fc"]) & 0xffffffff) / dt)
    out["frame_rates_hz"] = [round(x, 1) for x in rates]
    if not rates or max(rates) == 0:
        out["verdict"] = "D1-kick-frozen"
        out["reasons"].append("FRAME_COUNT constant across %d kicks (%r)" % (len(d["kicks"]), [k["fc"] for k in d["kicks"]][:6]))
        return out
    out["verdict"] = "D2-refreshing"
    out["reasons"].append("FRAME_COUNT advanced between kicks: median %.1f /s" % sorted(rates)[len(rates) // 2])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--kernel-text", required=True)
    ap.add_argument("--pixels", required=True)
    ap.add_argument("--owner-observation")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    res = classify(open(a.kernel_text, errors="replace").read(), json.load(open(a.pixels)))
    res["owner_observation"] = a.owner_observation
    if a.out:
        json.dump(res, open(a.out, "w"), indent=1)
    print(json.dumps({k: res[k] for k in ("window", "verdict", "ios", "kicks", "reasons")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
