#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-122 analyser (rule fixed by NAT-121 before the run): the touch bring-up steps 1-2 and the reader of /dev/hakios-touch.

    analyze122.py --kernel-text KERNEL_TEXT --pixels PIXELS_JSON [--owner-observation TEXT] [--out OUT_JSON]

Window first (analyze120: X-window when the timed return, the report or the absence of an earlier panic fails). Then, touch, first match:
  T0-fault        a kernel panic mentions e1s_touch, or no `e1s-touch: step 1` line and the window failed
  T0-no-step1     no `e1s-touch: step 1` line (driver did not run, or the line is in the log gap)
  T1-no-response  step 2 reached; device id all-zero / all-FF ("no response ...")
  T2-chip-answers step 2 reached; device id "ok" (bytes reported)
Reported beside it, not judged: the step-1 register words, `redwood-touch: opened by pid`, `hakios: input:` lines, the analyze120
verdict (display refresh) and analyze118's iOS verdict. A touch reaching iOS is not claimed from this run (no event thread at step 2).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nat-119"))
import analyze120 as A120  # noqa: E402

RE_STEP1 = re.compile(r"e1s-touch: step 1: (.*)")
RE_ID = re.compile(r"e1s-touch: device id: (.*?) \(([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2}) ([0-9a-f]{2})\)")
RE_STOP = re.compile(r"e1s-touch: stopped after step (\d)")
RE_OPEN = re.compile(r"redwood-touch: opened by pid (-?\d+) \(minor (\d+)\)")
RE_INPUT = re.compile(r"hakios: input: (.*)")
RE_PANIC = re.compile(r"^panic\(.*", re.M)


def parse(text):
    r = dict(step1=None, id=None, stopped=None, opens=[], input=[], panic=None)
    for ln in text.splitlines():
        if (m := RE_STEP1.search(ln)) and r["step1"] is None:
            r["step1"] = dict(re.findall(r"(\w+(?: \w+)?)=(0x[0-9a-f]+|0)", m.group(1)))
        if (m := RE_ID.search(ln)):
            r["id"] = dict(status=m.group(1), bytes=[m.group(i) for i in range(2, 7)])
        if (m := RE_STOP.search(ln)):
            r["stopped"] = int(m.group(1))
        if (m := RE_OPEN.search(ln)):
            r["opens"].append(dict(pid=int(m.group(1)), minor=int(m.group(2))))
        if (m := RE_INPUT.search(ln)):
            r["input"].append(m.group(1).strip()[:200])
    m = RE_PANIC.search(text)
    r["panic"] = m.group(0)[:300] if m else None
    return r


def classify(text, pixels):
    base = A120.classify(text, pixels)
    r = parse(text)
    out = dict(window=base["window"], display=base["verdict"], ios=base["ios"], touch=None, reasons=[], parsed=r)
    if r["panic"] and "e1s_touch" in r["panic"]:
        out["touch"] = "T0-fault"
        out["reasons"].append(r["panic"])
    elif r["step1"] is None:
        out["touch"] = "T0-fault" if base["window"] != "W-ok" else "T0-no-step1"
        out["reasons"].append("no 'e1s-touch: step 1' line")
    elif r["id"] is None:
        out["touch"] = "T0-no-step1" if r["stopped"] is None else "T1-no-response"
        out["reasons"].append("step 1 read; no device-id line (stopped=%r)" % r["stopped"])
    elif r["id"]["status"] == "ok":
        out["touch"] = "T2-chip-answers"
        out["reasons"].append("device id %s" % " ".join(r["id"]["bytes"]))
    else:
        out["touch"] = "T1-no-response"
        out["reasons"].append("device id: %s (%s)" % (r["id"]["status"], " ".join(r["id"]["bytes"])))
    out["reader_opened"] = bool(r["opens"])
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
    print(json.dumps({k: res[k] for k in ("window", "display", "ios", "touch", "reader_opened", "reasons")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
