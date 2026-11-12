#!/usr/bin/env python3
"""Mutation pass for NAT-076: break one place at a time in (a) the receive state machine of engine/usbmon.c and (b) the host
sender tools/ios/root_send.py, and require the host tests to fail. Host-only; writes under --out (which must not exist) and
a scratch directory, nowhere else.

    python3 -I docs/procedures/nat-076/mutate_rx.py --out artifacts/nat-076/mutation [--jobs 8]

Engine mutants run docs/procedures/nat-076/test_rx.py (fail-fast) in a scratch copy of the procedure tree; sender mutants run
tests/test_root_send.py and then the static checks of test_rx.py against the mutated sender. A mutant that compiles/parses but
is not killed is listed as a survivor; the exit status is non-zero while any survivor is not in docs/procedures/nat-076/
equivalent.json (survivors that were examined and judged equivalent, each with its reason).
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import modelhost  # noqa: E402  (the compile flags of the model build: a mutant must build exactly like the real engine)

CC_FLAGS = list(modelhost.CC_FLAGS)
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
ENGINE_REL = "docs/procedures/nat-076/engine/usbmon.c"
SENDER_REL = "tools/ios/root_send.py"
TYPES = ("uint8_t", "uint16_t", "uint32_t", "uint64_t", "int ", "unsigned", "struct ", "const ", "volatile", "size_t", "static ",
         "uintptr_t", "char ")
C_BINOPS = [(" == ", " != "), (" != ", " == "), (" < ", " <= "), (" <= ", " < "), (" > ", " >= "), (" >= ", " > "),
            (" && ", " || "), (" || ", " && "), (" + ", " - "), (" - ", " + "), (" | ", " & "), (" & ", " | "), (" % ", " * ")]
PY_BINOPS = [(" == ", " != "), (" != ", " == "), (" < ", " <= "), (" <= ", " < "), (" > ", " >= "), (" >= ", " > "),
             (" and ", " or "), (" or ", " and "), (" + ", " - "), (" - ", " + "), (" % ", " * "), (" in ", " not in "),
             (" is not ", " is "), (" is ", " is not ")]


def split_c(line):
    i = line.find("/*")
    j = line.find("//")
    cut = min([x for x in (i, j) if x >= 0] or [len(line)])
    return line[:cut], line[cut:]


def split_py(line):
    in_s, q = False, ""
    for i, ch in enumerate(line):
        if in_s:
            if ch == q and line[i - 1] != "\\":
                in_s = False
        elif ch in "'\"":
            in_s, q = True, ch
        elif ch == "#":
            return line[:i], line[i:]
    return line, ""


def occurrences(code, needle):
    k = 0
    while True:
        k = code.find(needle, k)
        if k < 0:
            return
        yield k
        k += 1


def mask_strings(code):
    """The same line with the inside of every string literal replaced by a filler byte (same length), so that operators and
    numbers inside messages are not mutated: those mutants only change prose."""
    out, in_s, q = [], False, ""
    for i, ch in enumerate(code):
        if in_s:
            if ch == q and code[i - 1] != "\\":
                in_s = False
                out.append(ch)
            else:
                out.append("\x01")
        else:
            if ch in "'\"":
                in_s, q = True, ch
            out.append(ch)
    return "".join(out)


def literal_mutants(code, masked=None):
    masked = code if masked is None else masked
    for m in re.finditer(r"(?<![\w.])(0[xX][0-9a-fA-F]+|\d+)(?![\w.])", masked):
        txt = m.group(1)
        val = int(txt, 0)
        for nv in {val + 1, 0 if val else 1}:
            if nv == val:
                continue
            new = hex(nv) if txt.lower().startswith("0x") else str(nv)
            yield "literal %s -> %s" % (txt, new), code[:m.start(1)] + new + code[m.end(1):]


def if_condition_span(code):
    m = re.search(r"\b(?:else )?if \(", code)
    if not m:
        return None
    start = m.end() - 1
    depth = 0
    for k in range(start, len(code)):
        if code[k] == "(":
            depth += 1
        elif code[k] == ")":
            depth -= 1
            if depth == 0:
                return start, k
    return None


def c_line_mutants(line):
    code, tail = split_c(line)
    out = []
    for a, b in C_BINOPS:
        for k in occurrences(code, a):
            out.append(("%s -> %s" % (a.strip(), b.strip()), code[:k] + b + code[k + len(a):]))
    out += list(literal_mutants(code))
    span = if_condition_span(code)
    if span:
        s0, e0 = span
        out.append(("condition forced false", code[:s0 + 1] + "0" + code[e0:]))
        out.append(("condition forced true", code[:s0 + 1] + "1" + code[e0:]))
        out.append(("condition negated", code[:s0 + 1] + "!(" + code[s0 + 1:e0] + ")" + code[e0:]))
    st = code.strip()
    if (st.endswith(";") and not st.startswith(("return", "break", "continue", "case", "default", "#", "}", "{", "goto"))
            and not st.startswith(TYPES) and not re.match(r"^(if|for|while|else|switch)\b", st) and "{" not in st):
        out.append(("statement deleted", re.sub(r"\S.*", ";", code, count=1)))
    if st.startswith("return ") and st.endswith(";"):
        out.append(("return value dropped", re.sub(r"return .*;", "return 0;", code, count=1)))
    return [(d, c + tail) for d, c in out]


def py_line_mutants(line):
    code, tail = split_py(line)
    if "log(" in code or code.strip().startswith(('"""', "'''", "if __name__", "sys.exit(main())")):
        return []
    masked = mask_strings(code)
    out = []
    for a, b in PY_BINOPS:
        for k in occurrences(masked, a):
            out.append(("%s -> %s" % (a.strip(), b.strip()), code[:k] + b + code[k + len(a):]))
    out += list(literal_mutants(code, masked))
    for a, b in ((" True", " False"), (" False", " True"), ("(True", "(False"), ("(False", "(True")):
        for k in occurrences(masked, a):
            out.append(("%s -> %s" % (a.strip(), b.strip()), code[:k] + b + code[k + len(a):]))
    for k in occurrences(masked, "not "):
        out.append(("not removed", code[:k] + code[k + 4:]))
    st = code.strip()
    m = re.match(r"^(\s*)(if|elif|while) (.*):\s*$", code)
    if m:
        out.append(("condition forced false", "%s%s False:" % (m.group(1), m.group(2))))
        out.append(("condition forced true", "%s%s True:" % (m.group(1), m.group(2))))
    elif (st and st != "pass" and not st.endswith((":", "(", ",", "\\", "[", "{")) and not st.startswith(
            ("def ", "class ", "try", "except", "else", "finally", "import ", "from ", "@", "elif", "if ", "while ", "for ", "with ",
             "assert", "global", "nonlocal", ")", "]", "}", "else:")) and st.count("(") == st.count(")") and st.count("[") == st.count("]")):
        out.append(("statement deleted", re.sub(r"\S.*", "pass", code, count=1)))
    return [(d, c + tail) for d, c in out]


def engine_selected_lines(lines):
    start = next(i for i, l in enumerate(lines) if "bulk-OUT receive (NAT-076)" in l and "----" in l)
    end = next(i for i, l in enumerate(lines) if "descriptors and requests" in l and "----" in l)
    sel = set(range(start, end))
    for i, l in enumerate(lines):
        if i in sel:
            continue
        code, _ = split_c(l)
        if re.search(r"\brx_|USBMON_RX|out_kind|USBMON_REQ_(RX|GET_RX)", code) and not code.lstrip().startswith("#"):
            sel.add(i)
    return sorted(sel)


def generate(path, kind):
    with open(path) as f:
        lines = f.read().split("\n")
    if kind == "c":
        sel = engine_selected_lines(lines)
        fn = c_line_mutants
    else:
        sel = range(len(lines))
        fn = py_line_mutants
        in_doc = False
        keep = []
        for i, l in enumerate(lines):
            if l.count('"""') == 1:
                in_doc = not in_doc
                continue
            if not in_doc and l.count('"""') == 0:
                keep.append(i)
        sel = keep
    muts = []
    for i in sel:
        line = lines[i]
        if not line.strip() or line.lstrip().startswith(("/*", "*", "//", "#")):
            continue
        for desc, new in fn(line):
            if new == line:
                continue
            muts.append(dict(line=i + 1, desc=desc, old=line.strip(), new=new.strip(), text="\n".join(lines[:i] + [new] + lines[i + 1:])))
    return muts


def make_tree(dst):
    """A scratch repository root: the procedure tree, the sender, a link to the pinned vendor tree."""
    proc = os.path.join(dst, "docs", "procedures", "nat-076")
    shutil.copytree(HERE, proc, ignore=shutil.ignore_patterns("__pycache__", "evidence.json", "mutation*.json", "equivalent.json"))
    os.makedirs(os.path.join(dst, "tools", "ios"))
    shutil.copy(os.path.join(ROOT, SENDER_REL), os.path.join(dst, SENDER_REL))
    os.makedirs(os.path.join(dst, "tests"))
    shutil.copy(os.path.join(ROOT, "tests", "test_root_send.py"), os.path.join(dst, "tests", "test_root_send.py"))
    refs = os.path.join(ROOT, "references")
    if os.path.isdir(refs):
        os.symlink(refs, os.path.join(dst, "references"))
    return dst


def run(cmd, cwd, env, timeout):
    try:
        r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    return r.returncode, (r.stdout + r.stderr)[-1500:]


def first_failures(text):
    keep = [l for l in text.splitlines() if l.startswith(("FAIL:", "ERROR:")) or "Error" in l[:40]]
    return keep[:3]


def check_c(tree, text, timeout, env):
    target = os.path.join(tree, ENGINE_REL)
    with open(target, "w") as f:
        f.write(text)
    proc = os.path.join(tree, "docs", "procedures", "nat-076")
    # the same compile as modelhost.build(strict=True): a mutant that does not build cleanly is invalid, not "killed"
    r = subprocess.run(["cc"] + CC_FLAGS + ["-I", os.path.join(proc, "engine"), "-I", os.path.join(proc, "model"),
                                         target, os.path.join(proc, "model", "model.c"), "-o", os.path.join(env["TMPDIR"], "probe.so")],
                       capture_output=True, text=True)
    if r.returncode != 0 or r.stderr.strip():
        return "invalid", r.stderr.strip().splitlines()[-1:]
    rc, out = run([sys.executable, "-I", os.path.join(tree, "docs/procedures/nat-076/test_rx.py"), "-f"], tree, env, timeout)
    return ("survived" if rc == 0 else "killed"), (rc, first_failures(out))


def check_py(tree, text, timeout, env):
    target = os.path.join(tree, SENDER_REL)
    try:
        compile(text, "mutant", "exec")
    except SyntaxError as e:
        return "invalid", [str(e)]
    with open(target, "w") as f:
        f.write(text)
    env = dict(env, ROOT_SEND_UNDER_TEST=target)
    rc, out = run([sys.executable, "-m", "unittest", "discover", "-s", os.path.join(tree, "tests"), "-p", "test_root_send.py", "-f"],
                  tree, env, timeout)
    if rc != 0:
        return "killed", (rc, first_failures(out))
    rc, out = run([sys.executable, "-I", os.path.join(tree, "docs/procedures/nat-076/test_rx.py"), "-f", "StaticTests"], tree, env, timeout)
    return ("survived" if rc == 0 else "killed"), (rc, first_failures(out))


def worker(args):
    idx, kind, mut, tmp, timeout, base_env = args
    tree = make_tree(os.path.join(tmp, "m%04d" % idx))
    try:
        env = dict(base_env, TMPDIR=os.path.join(tmp, "t%04d" % idx))
        os.makedirs(env["TMPDIR"])
        outcome, detail = (check_c if kind == "c" else check_py)(tree, mut["text"], timeout, env)
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    return idx, outcome, detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--only", choices=("engine", "sender"))
    ap.add_argument("--limit", type=int, help="run only the first N mutants of each kind (smoke)")
    a = ap.parse_args()
    if os.path.exists(a.out):
        print("refusing: --out exists", file=sys.stderr)
        return 2
    base_env = dict(os.environ)
    equivalent = {}
    eq_path = os.path.join(HERE, "equivalent.json")
    if os.path.exists(eq_path):
        with open(eq_path) as f:
            equivalent = {(e["file"], e["line"], e["desc"]): e["reason"] for e in json.load(f)}
    jobs = []
    for kind, rel, label in (("c", ENGINE_REL, "engine"), ("py", SENDER_REL, "sender")):
        if a.only and a.only != label:
            continue
        muts = generate(os.path.join(ROOT, rel), kind)
        if a.limit:
            muts = muts[:a.limit]
        for m in muts:
            m["file"], m["kind"] = rel, kind
            jobs.append(m)
    print("%d mutants" % len(jobs), flush=True)
    with tempfile.TemporaryDirectory(prefix="nat076-mut-", dir=os.environ.get("TMPDIR")) as tmp:
        # baseline: the unmutated copy must pass both suites
        tree = make_tree(os.path.join(tmp, "base"))
        env = dict(base_env, TMPDIR=os.path.join(tmp, "tbase"))
        os.makedirs(env["TMPDIR"])
        rc1, out1 = run([sys.executable, "-I", os.path.join(tree, "docs/procedures/nat-076/test_rx.py")], tree, env, 600)
        rc2, out2 = run([sys.executable, "-m", "unittest", "discover", "-s", os.path.join(tree, "tests"), "-p", "test_root_send.py"],
                        tree, dict(env, ROOT_SEND_UNDER_TEST=os.path.join(tree, SENDER_REL)), 600)
        if rc1 != 0 or rc2 != 0:
            print("baseline fails; refusing to judge mutants:\n%s\n%s" % (out1[-600:], out2[-600:]))
            return 2
        shutil.rmtree(tree)
        results = []
        with cf.ThreadPoolExecutor(max_workers=a.jobs) as ex:
            futs = [ex.submit(worker, (i, m["kind"], m, tmp, a.timeout, base_env)) for i, m in enumerate(jobs)]
            for n, fu in enumerate(cf.as_completed(futs), 1):
                idx, outcome, detail = fu.result()
                m = jobs[idx]
                key = (m["file"], m["line"], m["desc"])
                results.append(dict(file=m["file"], line=m["line"], desc=m["desc"], code=m["old"], mutated=m["new"], outcome=outcome,
                                    detail=detail if outcome != "survived" else None,
                                    reason=equivalent.get(key) if outcome == "survived" else None))
                if n % 25 == 0:
                    print("%d/%d done" % (n, len(jobs)), flush=True)
    results.sort(key=lambda r: (r["file"], r["line"], r["desc"]))
    summary = {}
    for r in results:
        s = summary.setdefault(r["file"], dict(total=0, killed=0, survived=0, survived_unexplained=0, invalid=0, timeout=0))
        s["total"] += 1
        if r["outcome"] == "killed":
            s["killed"] += 1
            if isinstance(r["detail"], (list, tuple)) and r["detail"] and r["detail"][0] == "timeout":
                s["timeout"] += 1
        elif r["outcome"] == "invalid":
            s["invalid"] += 1
        else:
            s["survived"] += 1
            if not r["reason"]:
                s["survived_unexplained"] += 1
    os.makedirs(a.out)
    with open(os.path.join(a.out, "mutation.json"), "w") as f:
        json.dump(dict(summary=summary, results=[r for r in results if r["outcome"] != "invalid"],
                       invalid=[dict(file=r["file"], line=r["line"], desc=r["desc"]) for r in results if r["outcome"] == "invalid"]),
                  f, indent=1)
    for f_, s in summary.items():
        print("%-45s total %d killed %d survived %d (unexplained %d) invalid %d" % (f_, s["total"], s["killed"], s["survived"],
                                                                                   s["survived_unexplained"], s["invalid"]))
    for r in results:
        if r["outcome"] == "survived":
            print("SURVIVED %s:%d  %s   |  %s   ->  %s%s" % (r["file"], r["line"], r["desc"], r["code"], r["mutated"],
                                                           "   [%s]" % r["reason"] if r["reason"] else ""))
    return 0 if all(s["survived_unexplained"] == 0 for s in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
