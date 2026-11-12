#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-101: join the results of two mutation passes into one file that `mutate_nat101.py --annotate` can read (host only, reads and writes JSON).

    merge_mutation.py --take PASS1/mutation.json:src/hb.c --take PASS2/mutation.json:build_hb --out DIR

The first pass ran every target against the first test file; the builders' tests then had gaps (185 survivors, 142 of them in build_hb_root.py because no test ran build() to the end), tests were added, and
the second pass re-ran only the two builders. `--take FILE:SUBSTRING` keeps the rows of FILE whose `file` field contains SUBSTRING, so the merged file holds each target exactly once, from the pass that is
current for it. The merge is checked: a target may not come from two passes, and the output records which pass file (by sha256) each target's rows came from. Nothing is judged here: outcomes are copied."""
import argparse
import hashlib
import json
import sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--take", action="append", required=True, metavar="FILE:SUBSTRING")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    if a.out.exists():
        raise SystemExit("--out exists: %s" % a.out)
    results, invalid, summary, sources, seen = [], [], {}, [], set()
    for spec in a.take:
        path, _, sub = spec.rpartition(":")
        if not path or not sub:
            raise SystemExit("--take needs FILE:SUBSTRING, got %r" % spec)
        raw = Path(path).read_bytes()
        doc = json.loads(raw)
        files = sorted({r["file"] for r in doc["results"]} | {r["file"] for r in doc["invalid"]})
        keep = [f for f in files if sub in f]
        if not keep:
            raise SystemExit("%s holds no target matching %r" % (path, sub))
        for f in keep:
            if f in seen:
                raise SystemExit("target %s is taken twice" % f)
            seen.add(f)
            summary[f] = doc["summary"][f]
        results += [r for r in doc["results"] if r["file"] in keep]
        invalid += [r for r in doc["invalid"] if r["file"] in keep]
        sources.append({"pass_file_sha256": hashlib.sha256(raw).hexdigest(), "targets": keep})
    args_out = a.out
    args_out.mkdir(parents=True)
    (args_out / "mutation.json").write_text(json.dumps(dict(summary=summary, results=results, invalid=invalid, merged_from=sources), indent=1) + "\n")
    for f in sorted(summary):
        s = summary[f]
        print("%-52s total %3d killed %3d survived %3d invalid %2d" % (f, s["total"], s["killed"], s["survived"], s["invalid"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
