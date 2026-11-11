#!/usr/bin/env python3
"""Verify docs/procedures/nat-042/plan.json against the pinned vendor kernel (and the local runtime DTB when present).

    python3 -I docs/procedures/nat-042/verify_plan.py [--require-runtime-dtb] [--plan PATH] [--json OUT]

Checks, each independent of the others:
  1. the pin exists in references/s24-linux;
  2. every citation: line N of `git show PIN:file` contains the cited text;
  3. every number in `values` is re-derived from the cited source lines (not copied from the plan);
  4. the absence claims (git grep at the pin);
  5. the runtime DTB values, when devices/e1s-fdt/2026-11-10/runtime.dtb is present with the recorded hash.
Exit 0 only if all run checks pass; a skipped runtime-DTB check is reported as skipped.
"""
import argparse, hashlib, json, os, re, struct, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))


def git_show(repo, sha, path):
    return subprocess.check_output(["git", "-C", repo, "show", "%s:%s" % (sha, path)], text=True, stderr=subprocess.DEVNULL).split("\n")


def norm(s):
    return re.sub(r"\s+", " ", s).strip()


def num(text):
    m = re.search(r"0[xX][0-9a-fA-F]+", text)
    return int(m.group(0), 16) if m else None


def derive(cites):
    """Numbers computed from the cited lines only."""
    c = {k: v["text"] for k, v in cites.items()}
    d = {}
    d["reboot"] = num(c["R02"]); d["reboot_trigger"] = num(c["R03"]); d["reboot_cmd"] = num(c["R04"])
    d["inform2"] = num(c["R08"]); d["inform3"] = num(c["R09"])
    prefix = num(c["S01"])
    for key, cid in (("reason_normal", "S02"), ("reason_download", "S03"), ("reason_recovery", "S04"), ("reason_bootloader", "S05")):
        d[key] = prefix | num(c[cid].split("|", 1)[1])
    d["inform2_normal"] = num(c["S06"])
    d["inform2_byte_mask"] = int(re.search(r"(0[xX][0-9a-fA-F]+)\);", c["S08"]).group(1), 16)
    d["inform2_byte_shift"] = int(re.search(r"\((\d+)\)", c["S07"]).group(1))
    m = re.search(r"\(\(1 << (\d+)\) - 1\)", c["E03"])
    d["mode_mask"] = (1 << int(m.group(1))) - 1
    d["mode_normal"] = num(c["E01"]); d["mode_recovery"] = num(c["E02"]); d["mode_fastboot"] = num(c["E13"])
    return d


def parse_fdt(path):
    with open(path, "rb") as f:
        b = f.read()
    magic, total, off_struct, off_str, _r, _v, _l, _b, sz_str, _s = struct.unpack(">10I", b[:40])
    if magic != 0xD00DFEED:
        raise ValueError("not an FDT")
    strs = b[off_str:off_str + sz_str]
    p, stack, props = off_struct, [], {}
    while True:
        t = struct.unpack(">I", b[p:p + 4])[0]; p += 4
        if t == 1:
            e = b.index(b"\0", p); stack.append(b[p:e].decode()); p = (e + 4) & ~3
        elif t == 2:
            stack.pop()
        elif t == 3:
            ln, no = struct.unpack(">II", b[p:p + 8]); p += 8
            v = b[p:p + ln]; p = (p + ln + 3) & ~3
            name = strs[no:strs.index(b"\0", no)].decode()
            props[("/".join(stack) or "/", name)] = v
        elif t == 9:
            break
    return props


def check(plan, root=ROOT, require_dtb=False):
    res, ok = [], True

    def rec(name, passed, detail=""):
        nonlocal ok
        ok = ok and passed
        res.append(dict(check=name, passed=passed, detail=detail))

    repo = os.path.join(root, plan["pin"]["repo_path"]); sha = plan["pin"]["sha"]
    try:
        subprocess.check_call(["git", "-C", repo, "cat-file", "-e", sha + "^{commit}"], stderr=subprocess.DEVNULL)
        rec("pin-exists", True, sha)
    except Exception as e:  # noqa
        rec("pin-exists", False, "%s not found in %s" % (sha, repo)); return ok, res

    cache, cites = {}, {}
    for c in plan["citations"]:
        cites[c["id"]] = c
        try:
            lines = cache.setdefault(c["file"], git_show(repo, sha, c["file"]))
            line = lines[c["line"] - 1] if 1 <= c["line"] <= len(lines) else ""
            rec("citation " + c["id"], norm(c["text"]) in norm(line), "%s:%d %r" % (c["file"], c["line"], norm(line)[:90]))
        except subprocess.CalledProcessError:
            rec("citation " + c["id"], False, "file %s not in the pin" % c["file"])
    if len(cites) != len(plan["citations"]):
        rec("citation-ids-unique", False, "duplicate ids")

    try:
        d = derive(cites)
        for k, v in d.items():
            want = plan["values"][k]
            want = int(want, 16) if isinstance(want, str) else want
            rec("value " + k, v == want, "derived %#x, plan %#x" % (v, want))
    except Exception as e:  # noqa
        rec("derive-values", False, repr(e))

    cited = {cid for step in plan["vendor_sequence_download"] for cid in step["cites"]}
    for cid in sorted(cited):
        rec("sequence-cites-exist " + cid, cid in cites)

    for ab in plan["absence_claims"]:
        r = subprocess.run(["git", "-C", repo, "grep", "-l", "-e", ab["pattern"], sha, "--"] + ab["pathspec"], capture_output=True, text=True)
        files = sorted(l.split(":", 1)[1] for l in r.stdout.split("\n") if ":" in l)
        rec("absence " + ab["id"], files == sorted(ab["expect_files"]), "found in %s" % files)

    dt = plan["runtime_dtb"]; path = os.path.join(root, dt["path"])
    if not os.path.exists(path):
        res.append(dict(check="runtime-dtb", passed=None, detail="skipped: %s is not present" % dt["path"]))
        if require_dtb:
            ok = False
    else:
        with open(path, "rb") as f:
            h = hashlib.sha256(f.read()).hexdigest()
        if h != dt["sha256"]:
            rec("runtime-dtb-hash", False, h)
        else:
            props = parse_fdt(path)
            rec("runtime-dtb-hash", True, h)
            for node, kv in dt["u32"].items():
                for k, v in kv.items():
                    got = props.get((node, k))
                    rec("dtb %s %s" % (node, k), got is not None and len(got) == 4 and struct.unpack(">I", got)[0] == int(v, 16),
                        "got %s" % (hex(struct.unpack(">I", got)[0]) if got and len(got) == 4 else got))
            for node, v in dt["reg"].items():
                got = props.get((node, "reg"))
                vals = [hex(x) for x in struct.unpack(">%dI" % (len(got) // 4), got)] if got else None
                rec("dtb %s reg" % node, vals == v, str(vals))
            for node, kv in dt["strings"].items():
                for k, v in kv.items():
                    got = props.get((node, k))
                    rec("dtb %s %s" % (node, k), got is not None and [s.decode() for s in got.rstrip(b"\0").split(b"\0")] == v, str(got))
    return ok, res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default=os.path.join(HERE, "plan.json"))
    ap.add_argument("--require-runtime-dtb", action="store_true")
    ap.add_argument("--json")
    a = ap.parse_args()
    with open(a.plan) as f:
        plan = json.load(f)
    ok, res = check(plan, require_dtb=a.require_runtime_dtb)
    failed = [r for r in res if r["passed"] is False]
    skipped = [r for r in res if r["passed"] is None]
    summary = dict(ok=ok, checks=len(res), passed=sum(1 for r in res if r["passed"]), failed=len(failed), skipped=len(skipped), results=res)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(summary, f, indent=1)
    for r in failed + skipped:
        print("%s %s: %s" % ("FAIL" if r["passed"] is False else "SKIP", r["check"], r["detail"]))
    print("%s: %d checks, %d passed, %d failed, %d skipped" % ("OK" if ok else "FAILED", len(res), summary["passed"], len(failed), len(skipped)))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
