#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-093 post-hoc reader (NOT the pre-registered analysis): reassemble the kernel-log records of an archive's boot that carries a `KL end why=2` line but no `KL begin` line
(the begin record was lost to a ring-overrun drop, so NAT-089's kl_reader.py, which needs `begin` for the announced sizes, reports no dump).

    posthoc_boot2.py --archive ARCHIVE --boot-glob '000002-*' --out-text FILE --out-excerpt FILE --out-json FILE

It reads `KL <6 hex digits> <escaped text>` records of that boot by NAT-062's own unescape, sorts them by their offsets, derives the dump geometry from what NAT-062's format fixes
(head <= 8192 bytes from offset 0, tail <= 32768 bytes ending at the dump length L, records of 96 bytes) and from the `KL end` line (recs, bytes), lists the offsets that arrived and the
ranges that did not, and summarises the text: the kernel clock range of the surviving tail, the lines that are not the repeating `denied attempt to escape CPU monitor` message, and the pids
that memorystatus_update lines name. Nothing here is a verdict row: the ladder rows A1-A8 stay those of analyze_nat089.py, which reports A8 for this archive.

--out-text is the full reassembled text and contains the host's user name (the kernel version line): it stays under artifacts/. --out-excerpt is the sanitized excerpt for the repository (the kernel
version line and the /dev listing removed, the repeated message reduced to a count and 3 samples)."""
import argparse
import importlib.util
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
RAW = 96
HEAD_MAX, TAIL_MAX = 8192, 32768
FLOOD = "denied attempt to escape CPU monitor"


def load_a62():
    spec = importlib.util.spec_from_file_location("nat093_a62", PROC / "nat-062" / "analyze_nat062.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["nat093_a62"] = m
    spec.loader.exec_module(m)
    return m


def read_boot(a62, boot_dir):
    rows = []
    for line in (Path(boot_dir) / "frames.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        f = json.loads(line)["frame"]
        if f.get("kind") == "log" and "dev_seq" in f and isinstance(f.get("text"), str):
            rows.append((f["dev_seq"], f["text"]))
    rows.sort()
    recs, end = {}, None
    for _, t in rows:
        m = re.match(r"^KL ([0-9a-f]{6}) (.*)$", t, re.S)
        if m:
            recs[int(m.group(1), 16)] = a62.unescape(m.group(2))
            continue
        m = a62.END.match(t)
        if m:
            end = {k: int(v) for k, v in m.groupdict().items()}
    return recs, end


def runs_of(recs):
    runs = []
    for o in sorted(recs):
        n = len(recs[o])
        if runs and runs[-1][1] == o:
            runs[-1][1] = o + n
        else:
            runs.append([o, o + n])
    return runs


def geometry(recs, end):
    """-> dict: the dump length L (end of the last record), tail start, expected record count and the missing ranges."""
    offs = sorted(recs)
    length = offs[-1] + len(recs[offs[-1]])
    head_n = min(HEAD_MAX, length)
    tail_lo = max(head_n, length - TAIL_MAX)
    want = []
    for lo, hi in ((0, head_n), (tail_lo, length)):
        o = lo
        while o < hi:
            want.append((o, min(RAW, hi - o)))
            o += RAW
    missing = sorted((o, o + n) for o, n in want if o not in recs or len(recs[o]) != n)
    merged = []
    for lo, hi in missing:
        if merged and merged[-1][1] == lo:
            merged[-1][1] = hi
        else:
            merged.append([lo, hi])
    return dict(length=length, head=head_n, tail_start=tail_lo, tail=length - tail_lo, expected_records=len(want), records=len(recs),
                end_line_records=(end or {}).get("recs"), end_line_bytes=(end or {}).get("bytes"), missing=merged,
                missing_bytes=sum(h - l for l, h in merged), unexpected_offsets=sorted(o for o in recs if o not in dict(want)))


def text_of(recs, runs):
    parts = []
    for a, b in runs:
        parts.append("\n#### offsets 0x%x-0x%x (%d bytes)\n" % (a, b, b - a))
        parts += [recs[o].decode("utf-8", "replace") for o in sorted(recs) if a <= o < b]
    return "".join(parts)


def summarise(text, geom):
    ts = [float(m.group(1)) for m in re.finditer(r"\[\s*(\d+\.\d+)\]: ", text)]
    lines = text.split("\n")
    flood = [l for l in lines if FLOOD in l]
    procs = Counter(re.findall(r"process (\S+?)\[(\d+)\] denied", text))
    pids = sorted({int(p) for p in re.findall(r"memorystatus_update\(enter\): pid (\d+)", text)})
    stamp = re.compile(r"^\[\s*\d+\.\d+\]: ")
    other = [re.sub(r"\[\s*\d+\.\d+\]", "[T]", l) for l in lines if stamp.match(l) and FLOOD not in l]
    mem = [l for l in lines if "]: memory: free" in l]
    return dict(kernel_clock_first=min(ts) if ts else None, kernel_clock_last=max(ts) if ts else None, timestamped_lines=len(ts), flood_lines=len(flood),
                flood_processes=[dict(name=n, pid=int(p), lines=c) for (n, p), c in procs.most_common(5)], memorystatus_pids=pids,
                non_flood_timestamped_lines=Counter(other).most_common(12), memory_line=mem[-1][mem[-1].index("memory:"):] if mem else None)


def excerpt(text, summary):
    head = text.split("\n#### offsets")[1].split("\n", 1)[1]            # the first run: the head, offsets 0.. (the marker line itself dropped)
    keep = []
    skip_dev = False
    for l in head.split("\n"):
        if l.startswith("Darwin Kernel Version"):
            continue
        if l.startswith("-- devices --"):
            skip_dev = True
            keep.append(l)
            keep.append("  (the /dev listing is omitted here)")
            continue
        if skip_dev:
            if l.startswith("[ ok ] devfs is mounted"):
                skip_dev = False
                keep.append(l)
            continue
        keep.append(l)
    out = "\n".join(keep) + "\n"
    out += "\n#### the surviving tail, reduced (offsets and the missing ranges: posthoc.json)\n"
    out += "kernel clock %s s .. %s s; %d timestamped lines, %d of them `process lsd[21] denied attempt to escape CPU monitor (missing required entitlement).`\n" % (
        summary["kernel_clock_first"], summary["kernel_clock_last"], summary["timestamped_lines"], summary["flood_lines"])
    for l, c in summary["non_flood_timestamped_lines"]:
        out += "%3d x %s\n" % (c, l)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", required=True)
    ap.add_argument("--boot-glob", required=True)
    ap.add_argument("--out-text", required=True)
    ap.add_argument("--out-excerpt", required=True)
    ap.add_argument("--out-json", required=True)
    a = ap.parse_args(argv)
    boots = sorted((Path(a.archive) / "boots").glob(a.boot_glob))
    if len(boots) != 1:
        raise SystemExit("--boot-glob matches %d boots, need exactly 1" % len(boots))
    a62 = load_a62()
    recs, end = read_boot(a62, boots[0])
    if not recs:
        raise SystemExit("no KL records in %s" % boots[0].name)
    geom = geometry(recs, end)
    text = text_of(recs, runs_of(recs))
    summary = summarise(text, geom)
    for p in (a.out_text, a.out_excerpt, a.out_json):
        if Path(p).exists():
            raise SystemExit("refusing to overwrite %s" % p)
    Path(a.out_text).write_text(text)
    Path(a.out_excerpt).write_text(excerpt(text, summary))
    Path(a.out_json).write_text(json.dumps(dict(boot=boots[0].name, geometry=geom, summary=summary, note="post-hoc reading; not a ladder row"), indent=1) + "\n")
    print(json.dumps(dict(boot=boots[0].name, geometry=dict(geom, missing=[[hex(l), hex(h)] for l, h in geom["missing"]]), summary=summary), indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
