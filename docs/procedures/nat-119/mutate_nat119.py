#!/usr/bin/env python3
"""NAT-119 mutation pass over analyze120.py: each mutant must make test_nat119.py fail. Run: python3 -B -I docs/procedures/nat-119/mutate_nat119.py"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MUTANTS = [
    ('if base["window"] != "W-ok":', 'if False:'),
    ('if not d["kicks"]:', 'if False:'),
    ('if not rates or max(rates) == 0:', 'if not rates:'),
    ('if not rates or max(rates) == 0:', 'if max(rates or [0]) < 0:'),
    ('((b["fc"] - a["fc"]) & 0xffffffff) / dt', '(b["fc"] / dt)'),
    ('elif (m := RE_NOT.search(ln)):', 'elif False:'),
    ('out["verdict"] = "D2-refreshing"', 'out["verdict"] = "D1-kick-frozen"'),
]


def main():
    res = []
    for old, new in MUTANTS:
        with tempfile.TemporaryDirectory() as w:
            w = Path(w)
            (w / "nat-119").mkdir(); shutil.copytree(ROOT / "docs/procedures/nat-117", w / "nat-117")
            for f in ("analyze120.py", "test_nat119.py", "kernel-combined.patch"):
                shutil.copy(HERE / f, w / "nat-119" / f)
            src = (w / "nat-119/analyze120.py").read_text()
            assert src.count(old) == 1, old
            (w / "nat-119/analyze120.py").write_text(src.replace(old, new))
            t = (w / "nat-119/test_nat119.py").read_text().replace("HERE.parents[2]", "Path(%r)" % str(ROOT))
            t = t.replace('(ROOT / "docs/procedures/nat-115/kernel-combined.patch")', '(ROOT / "docs/procedures/nat-115/kernel-combined.patch")')
            (w / "nat-119/test_nat119.py").write_text(t)
            r = subprocess.run([sys.executable, "-B", "-I", str(w / "nat-119/test_nat119.py")], capture_output=True, text=True, timeout=300)
            res.append(dict(old=old, killed=r.returncode != 0))
    out = dict(total=len(res), killed=sum(x["killed"] for x in res), survived=[x for x in res if not x["killed"]])
    print(json.dumps(out))
    return 0 if not out["survived"] else 1


if __name__ == "__main__":
    sys.exit(main())
