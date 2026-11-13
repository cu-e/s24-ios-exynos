#!/usr/bin/env python3
"""NAT-117 mutation pass: each mutant of analyze118.py / make_adt117.py must make test_nat117.py fail.
Run: python3 -B -I docs/procedures/nat-117/mutate_nat117.py"""
import json, shutil, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
MUTANTS = [
    ("analyze118.py", 'BOUNDING = "Failed to load bounding path bitmap data"', 'BOUNDING = "Failed to load bounding path bitmap"  # x\nBOUNDING = "zzz"'),
    ("analyze118.py", 'f.get("fnv") != LOGO_FNV and f.get("nzb", 0) > 0', 'f.get("nzb", 0) > 0'),
    ("analyze118.py", 'f.get("fnv") != LOGO_FNV and f.get("nzb", 0) > 0', 'f.get("fnv") != LOGO_FNV'),
    ("analyze118.py", 'ok = r["expired"] and not r["panic_before_return"] and pixels.get("complete") is True',
     'ok = r["expired"] and pixels.get("complete") is True'),
    ("analyze118.py", 'ok = r["expired"] and not r["panic_before_return"] and pixels.get("complete") is True',
     'ok = not r["panic_before_return"] and pixels.get("complete") is True'),
    ("analyze118.py", 'ok = r["expired"] and not r["panic_before_return"] and pixels.get("complete") is True',
     'ok = r["expired"] and not r["panic_before_return"]'),
    ("analyze118.py", 'if r["aborts"] or r["exits"] or r["exceptions"]:', 'if r["aborts"] or r["exceptions"]:'),
    ("analyze118.py", 'r["panic_before_return"] = idx_e < 0 or idx_p < idx_e', 'r["panic_before_return"] = True'),
    ("analyze118.py", 'if new:\n', 'if False:\n'),
    ("make_adt117.py", 'GAMUT if k == "artwork-display-gamut" else v', 'v'),
    ("make_adt117.py", 'if not f and k not in ("name", "AAPL,phandle")]', 'if k not in ("name", "AAPL,phandle")]'),
    ("make_adt117.py", 'ph = max_phandle(root) + 1', 'ph = 1'),
    ("make_adt117.py", 'root.children.append(node)', 'root.children.insert(0, node)'),
    ("make_adt117.py", 'if sha(im4p_bytes) != IM4P_SHA:', 'if False:'),
]


def main():
    res = []
    for fn, old, new in MUTANTS:
        with tempfile.TemporaryDirectory() as w:
            w = Path(w)
            for f in ("analyze118.py", "make_adt117.py", "test_nat117.py"):
                shutil.copy(HERE / f, w / f)
            src = (w / fn).read_text()
            assert src.count(old) == 1, (fn, old)
            (w / fn).write_text(src.replace(old, new))
            t = (w / "test_nat117.py").read_text().replace("HERE.parents[2]", "Path(%r)" % str(HERE.parents[2]))
            t = t.replace('BUILD = ROOT', 'BUILD = ROOT')
            (w / "test_nat117.py").write_text(t)
            # make_adt117 resolves ROOT from its own location: pin it
            m = (w / "make_adt117.py").read_text().replace("ROOT = HERE.parents[2]", "ROOT = Path(%r)" % str(HERE.parents[2]))
            (w / "make_adt117.py").write_text(m)
            r = subprocess.run([sys.executable, "-B", "-I", str(w / "test_nat117.py")], capture_output=True, text=True, timeout=300)
            res.append(dict(file=fn, old=old[:60], killed=r.returncode != 0))
    out = dict(total=len(res), killed=sum(x["killed"] for x in res), survived=[x for x in res if not x["killed"]])
    print(json.dumps(out))
    return 0 if not out["survived"] else 1


if __name__ == "__main__":
    sys.exit(main())
