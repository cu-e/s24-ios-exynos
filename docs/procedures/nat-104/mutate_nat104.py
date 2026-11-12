#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Mutation pass for NAT-104: mutate analyze_nat104.py, build.py, and derive104.py one line at a time and require test_nat104.py to kill every non-equivalent mutant. Host-only.

    TMPDIR=<dir off /tmp> artifacts/nat-065/venv/bin/python -B -I docs/procedures/nat-104/mutate_nat104.py --out artifacts/nat-104/mutation [--jobs 6]
"""
import argparse
import concurrent.futures as cf
import importlib.util
import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
REL = "docs/procedures/nat-104"
TARGETS = (("py", REL + "/analyze_nat104.py"), ("py", REL + "/build.py"), ("py", REL + "/derive104.py"))
TESTS = ("test_nat104.py",)
FIRST = {t: "test_nat104.py" for _, t in TARGETS}


def load_generators():
    path = os.path.join(ROOT, "docs", "procedures", "nat-076", "mutate_rx.py")
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("nat076_mutate_rx", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


G = load_generators()


def generate(path, kind):
    with open(path) as f:
        lines = f.read().split("\n")
    sel, in_doc, in_tq = [], False, False
    triple = "'" * 3
    for i, l in enumerate(lines):
        s = l.strip()
        if kind == "py":
            if l.count(triple) == 1:
                in_tq = not in_tq
                continue
            if in_tq or l.count(triple):
                continue
            if l.count('"""') == 1:
                in_doc = not in_doc
                continue
            if in_doc or l.count('"""') or not s or s.startswith("#"):
                continue
        else:
            if not s or s.startswith(("/*", "*", "//")) or (s.startswith("#") and not s.startswith("#define")) or s.startswith("__asm__"):
                continue
        sel.append(i)
    fn = G.c_line_mutants if kind == "c" else G.py_line_mutants
    muts = []
    for i in sel:
        for desc, new in fn(lines[i]):
            if new != lines[i]:
                muts.append(dict(line=i + 1, desc=desc, old=lines[i].strip(), new=new.strip(), text="\n".join(lines[:i] + [new] + lines[i + 1:])))
    return muts


def make_tree(dst, snapshot):
    proc = os.path.join(dst, REL)
    os.makedirs(os.path.dirname(proc))
    shutil.copytree(snapshot, proc)
    real = os.path.join(ROOT, "docs", "procedures")
    for name in os.listdir(real):
        if name != "nat-104":
            os.symlink(os.path.join(real, name), os.path.join(dst, "docs", "procedures", name))
    for top in ("artifacts", "tools", "references"):
        os.symlink(os.path.join(ROOT, top), os.path.join(dst, top))
    return dst


MEM_CAP = 1536 * 1024 * 1024


def _cap_memory():
    resource.setrlimit(resource.RLIMIT_AS, (MEM_CAP, MEM_CAP))


def run(cmd, cwd, env, timeout):
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True, preexec_fn=_cap_memory)
    try:
        out, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        p.communicate()
        return "timeout", ""
    try:
        os.killpg(p.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return p.returncode, out[-1500:]


def first_failures(text):
    return [l for l in text.splitlines() if l.startswith(("FAIL:", "ERROR:"))][:3]


def worker(args):
    idx, mut, tmp, timeout, base_env = args
    tree = make_tree(os.path.join(tmp, "m%04d" % idx), os.path.join(tmp, "snapshot"))
    env = dict(base_env, TMPDIR=os.path.join(tmp, "t%04d" % idx))
    os.makedirs(env["TMPDIR"])
    py = sys.executable
    try:
        target = os.path.join(tree, mut["file"])
        if mut["kind"] == "py":
            try:
                compile(mut["text"], "mutant", "exec")
            except SyntaxError as e:
                return idx, "invalid", [str(e)]
        with open(target, "w") as f:
            f.write(mut["text"])
        proc = os.path.join(tree, REL)
        order = [FIRST[mut["file"]]] + [t for t in TESTS if t != FIRST[mut["file"]]]
        for name in order:
            rc, out = run([py, "-B", "-W", "ignore", "-I", os.path.join(proc, name), "-f"], tree, env, timeout)
            if rc != 0:
                return idx, "killed", (name, rc, first_failures(out))
        return idx, "survived", None
    finally:
        shutil.rmtree(tree, ignore_errors=True)
        shutil.rmtree(env["TMPDIR"], ignore_errors=True)


def load_equivalent():
    path = os.path.join(HERE, "equivalent.json")
    if not os.path.exists(path):
        return {}
    with open(path) as f:
        return {(e["file"], e["line"], e["desc"]): e["reason"] for e in json.load(f)}


def annotate(src, out):
    with open(src) as f:
        doc = json.load(f)
    equivalent = load_equivalent()
    results = []
    for r in doc["results"]:
        r = dict(r)
        if r["outcome"] == "survived":
            r["reason"] = equivalent.get((r["file"], r["line"], r["desc"]))
        results.append(r)
    for r in doc["invalid"]:
        results.append(dict(r, outcome="invalid", code=None, mutated=None, reason=None))
    unknown = set(equivalent) - {(r["file"], r["line"], r["desc"]) for r in results if r["outcome"] == "survived"}
    for k in sorted(unknown):
        print("equivalent.json entry matches no survivor: %s" % (k,), file=sys.stderr)
    rc = finish(results, out)
    return rc or (3 if unknown else 0)


def finish(results, out):
    results.sort(key=lambda r: (r["file"], r["line"], r["desc"]))
    summary = {}
    for r in results:
        s = summary.setdefault(r["file"], dict(total=0, killed=0, survived=0, survived_unexplained=0, invalid=0, timeout=0))
        s["total"] += 1
        if r["outcome"] == "killed":
            s["killed"] += 1
            if isinstance(r["detail"], (list, tuple)) and len(r["detail"]) > 1 and r["detail"][1] == "timeout":
                s["timeout"] += 1
        elif r["outcome"] == "invalid":
            s["invalid"] += 1
        else:
            s["survived"] += 1
            if not r["reason"]:
                s["survived_unexplained"] += 1
    os.makedirs(out)
    scrub = lambda x: json.loads(json.dumps(x).replace(os.environ.get("TMPDIR", "\0"), "$TMPDIR").replace(ROOT, "$REPO"))
    with open(os.path.join(out, "mutation.json"), "w") as f:
        json.dump(
            scrub(
                dict(
                    summary=summary,
                    results=[r for r in results if r["outcome"] != "invalid"],
                    invalid=[dict(file=r["file"], line=r["line"], desc=r["desc"], detail=r["detail"]) for r in results if r["outcome"] == "invalid"],
                )
            ),
            f,
            indent=1,
        )
    for f_, s in summary.items():
        print("%-45s total %d killed %d survived %d (unexplained %d) invalid %d" % (f_, s["total"], s["killed"], s["survived"], s["survived_unexplained"], s["invalid"]))
    for r in results:
        if r["outcome"] == "survived":
            print("SURVIVED %s:%d  %s   |  %s   ->  %s%s" % (r["file"], r["line"], r["desc"], r["code"], r["mutated"], "   [%s]" % r["reason"] if r["reason"] else ""))
    return 0 if all(s["survived_unexplained"] == 0 for s in summary.values()) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--only")
    ap.add_argument("--annotate", metavar="MUTATION_JSON")
    a = ap.parse_args()
    if os.path.exists(a.out):
        print("refusing: --out exists", file=sys.stderr)
        return 2
    if a.annotate:
        return annotate(a.annotate, a.out)
    equivalent = load_equivalent()
    jobs = []
    for kind, rel in TARGETS:
        if a.only and a.only not in rel:
            continue
        muts = generate(os.path.join(ROOT, rel), kind)
        if a.limit:
            muts = muts[:a.limit]
        for m in muts:
            m["file"], m["kind"] = rel, kind
            jobs.append(m)
    print("%d mutants" % len(jobs), flush=True)
    base_env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="nat104-mut-", dir=os.environ.get("TMPDIR")) as tmp:
        shutil.copytree(HERE, os.path.join(tmp, "snapshot"), ignore=shutil.ignore_patterns("__pycache__", "evidence.json", "mutation*.json", "equivalent.json", "task.json", "tmp"))
        tree = make_tree(os.path.join(tmp, "base"), os.path.join(tmp, "snapshot"))
        env = dict(base_env, TMPDIR=os.path.join(tmp, "tbase"))
        os.makedirs(env["TMPDIR"])
        for name in TESTS:
            rc, out = run([sys.executable, "-B", "-W", "ignore", "-I", os.path.join(tree, REL, name)], tree, env, 600)
            if rc != 0:
                print("baseline %s fails; refusing to judge mutants:\n%s" % (name, out[-800:]))
                return 2
        shutil.rmtree(tree)
        results = []
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = [ex.submit(worker, (i, m, tmp, a.timeout, base_env)) for i, m in enumerate(jobs)]
            for n, fu in enumerate(cf.as_completed(futs), 1):
                idx, outcome, detail = fu.result()
                m = jobs[idx]
                key = (m["file"], m["line"], m["desc"])
                results.append(dict(file=m["file"], line=m["line"], desc=m["desc"], code=m["old"], mutated=m["new"], outcome=outcome, detail=detail if outcome != "survived" else None, reason=equivalent.get(key) if outcome == "survived" else None))
                if n % 25 == 0:
                    print("%d/%d done" % (n, len(jobs)), flush=True)
    return finish(results, a.out)


if __name__ == "__main__":
    sys.exit(main())
