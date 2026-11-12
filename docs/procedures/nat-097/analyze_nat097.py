#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-097: the NAT-089 Stage A ladder (rows A1-A8) over the kernel text that reader v2 (kl_reader2.py) returns, so that a dump whose `KL begin` record was lost is read instead of
ending in A8 for want of a header. The row logic is NAT-089's `analyze_text`, imported and unchanged; only the reader differs. A dump read with an inferred geometry is marked in the
result (`dump.begin_inferred`) and in the reason text. Groups of records that could not be inferred are listed under `facts.unreadable` with the reason.

    analyze_nat097.py --archive ARCHIVE --jobs-dir DIR --out FILE.json

What it cannot show: what the holes, the unsent middle of the kernel buffer and a refused group contained; a row decided from a text with holes says so (hole_bytes, gap_bytes)."""
import argparse
import importlib.util
import json
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


R2 = _load("nat097_reader2", HERE / "kl_reader2.py")
A89 = _load("nat097_analyze89", PROC / "nat-089" / "analyze_nat089.py")
ROWS = A89.ROWS


def analyze(archive, jobs_dir):
    jobs = A89.read_jobs(jobs_dir)
    arch = R2.read_archive2(archive)
    finals = [d for d in arch["dumps"] if d["why"] == 2 and d["begin"]["len"] > 0]
    if not finals:
        reason = "no why=2 kernel-log dump with text in the archive"
        if arch["unreadable"]:
            reason += "; %d group(s) of records without a begin could not be inferred: %s" % (len(arch["unreadable"]), "; ".join(u["reason"] for u in arch["unreadable"]))
        return dict(row=8, name=ROWS[8], reason=reason, facts=dict(boots=len(arch["boots"]), dumps=len(arch["dumps"]), unreadable=arch["unreadable"]), table=[])
    d = max(finals, key=lambda x: len(x["bytes"]))
    r = A89.analyze_text(d["text"], jobs, hole_bytes=d["hole_bytes"], gap_bytes=d["begin"]["gap"])
    r["dump"] = dict(boots=[b[:6] for b in d["boots"]], records=len(d["bytes"]), closed=d["closed"], holes=d["holes"], conflicts=d["conflicts"], problems=d["problems"],
                     begin=d["begin"], begin_inferred=d["begin_inferred"])
    r["facts"]["unreadable"] = arch["unreadable"]
    if d["begin_inferred"]:
        r["reason"] += "; the dump's begin record was lost and its geometry was inferred from the end line and the received offsets (NAT-097 rules)"
    if d["conflicts"]:
        r["reason"] += "; WARNING: %d offsets have different bytes in different boots" % len(d["conflicts"])
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--archive", required=True, type=Path)
    ap.add_argument("--jobs-dir", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    r = analyze(a.archive, a.jobs_dir)
    a.out.write_text(json.dumps(r, indent=1, default=str) + "\n")
    print("row A%d %s: %s" % (r["row"], r["name"], r["reason"]))
    for t in r["table"]:
        print("  %-48s spawns %d alive %s exits %d" % (t["label"], t["spawns"], t["alive_in_last_list"], len(t["exits"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
