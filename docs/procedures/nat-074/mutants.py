#!/usr/bin/env python3
"""NAT-074: mutation run over the window hunks of make_variant.py. Each mutant edits one literal in a temporary copy of this directory
(links to the real nat-006, artifacts and devices) and the test file must fail. A mutant that survives is listed, not hidden.

  mutants.py --json PATH"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
M = [
    ("cap-2048", "(4096UL << 20)\\t/* NAT-074", "(2048UL << 20)\\t/* NAT-074"),
    ("cap-8192", "(4096UL << 20)\\t/* NAT-074", "(8192UL << 20)\\t/* NAT-074"),
    ("cap-4095", "(4096UL << 20)\\t/* NAT-074", "(4095UL << 20)\\t/* NAT-074"),
    ("touch-not-merged", "r[i].base <= r[out - 1].base + r[out - 1].size", "r[i].base < r[out - 1].base + r[out - 1].size"),
    ("overlap-grows-wrong", "r[out - 1].size = end - r[out - 1].base;", "r[out - 1].size += r[i].size;"),
    ("no-sort", "ranges_sort(mem, nmem);\\n\\tnmem = ranges_merge", "nmem = ranges_merge"),
    ("no-merge", "\\tnmem = ranges_merge(mem, nmem);\\n\\tif (nmem <= 0)\\n\\t\\treturn 0;\\n", ""),
    ("out-not-advanced", "r[out++] = r[i];", "r[out] = r[i];"),
    ("merge-everything", "if (out > 0 && r[i].base <=", "if (out > 0 || r[i].base <="),
    ("drop-first-node", "int out = 0;", "int out = 1;"),
]


# Mutants judged equivalent by reasoning, with the reason; they must still survive (a "killed" equivalent would mean the reasoning is wrong).
EQUIVALENT = {
    "drop-first-node": "starting out at 1 makes element 0 merge into itself (base <= base + size) and stay; the only input where it differs "
                       "is a zero-size first node, which fdt.c range_reg never returns (it skips size 0)",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", type=Path, required=True)
    a = ap.parse_args()
    results = []
    for name, old, new in M:
        with tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR")) as t:
            t = Path(t)
            (t / "docs/procedures").mkdir(parents=True)
            os.symlink(ROOT / "artifacts", t / "artifacts")
            os.symlink(ROOT / "devices", t / "devices")
            os.symlink(ROOT / "docs/procedures/nat-006", t / "docs/procedures/nat-006")
            d = t / "docs/procedures/nat-074"
            d.mkdir()
            for f in HERE.glob("*.py"):
                (d / f.name).write_text(f.read_text())
            src = (d / "make_variant.py").read_text()
            if src.count(old) != 1:
                results.append(dict(mutant=name, outcome="invalid", reason=f"pattern found {src.count(old)} times"))
                continue
            (d / "make_variant.py").write_text(src.replace(old, new))
            r = subprocess.run([sys.executable, "-I", str(d / "test_nat074.py")], capture_output=True, text=True, cwd=t)
            survived = r.returncode == 0
            if name in EQUIVALENT:
                outcome = "equivalent" if survived else "EQUIVALENT-WAS-KILLED"
            else:
                outcome = "SURVIVED" if survived else "killed"
            results.append(dict(mutant=name, outcome=outcome, exit=r.returncode, **({"reason": EQUIVALENT[name]} if name in EQUIVALENT else {})))
    summary = {k: sum(1 for r in results if r["outcome"] == k) for k in ("killed", "equivalent", "SURVIVED", "EQUIVALENT-WAS-KILLED", "invalid")}
    a.json.write_text(json.dumps(dict(summary=summary, results=results), indent=1) + "\n")
    print(json.dumps(summary))
    return 1 if summary["SURVIVED"] or summary["invalid"] or summary["EQUIVALENT-WAS-KILLED"] else 0


if __name__ == "__main__":
    sys.exit(main())
