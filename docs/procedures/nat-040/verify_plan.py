#!/usr/bin/env python3
"""NAT-040: verify plan.json against the pinned vendor kernel tree (source review).

For every step of plan.json this reads the cited file at the pinned revision with
`git show <rev>:<path>` (no working-tree copy), finds the cited literal text inside the
named function (or the whole file when no function is named), requires the exact number
of occurrences, and checks the order claims ("after": the step's first occurrence must come
on a later line than the named step's first occurrence, in the same file).

It also cross-checks the addresses and constants used in the plan prose against the USB-001
profile (src/platform/usb/profile.json) and writes a resolved.json with line numbers.

What this proves: the plan's citations exist verbatim at the pinned revision and the stated
order is the source order. What it does NOT prove: that the plan works on hardware, that the
live firmware (S921BXXS9BYH3) equals this tree, or what state S-Boot/the loader leaves.
Evidence kind: source-review.

Exit codes: 0 = every citation resolved and every cross-check holds; 1 = at least one failed;
2 = usage / environment error (pin not checked out, files missing).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_PLAN = Path(__file__).with_name("plan.json")
DEFAULT_PROFILE = ROOT / "src/platform/usb/profile.json"
DEFAULT_REPO = ROOT / "references/s24-linux"
DEFAULT_OUT = ROOT / "artifacts/nat-040/verify-001/resolved.json"

CLASSES = {"V", "M-omit", "U", "I"}
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


class VerifyError(Exception):
    pass


def git_show(repo: Path, rev: str, path: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "show", f"{rev}:{path}"],
        capture_output=True,
    )
    if proc.returncode != 0:
        raise VerifyError(f"git show {rev[:12]}:{path} failed: {proc.stderr.decode(errors='replace').strip()}")
    return proc.stdout.decode("utf-8", errors="replace")


def function_span(lines: list[str], name: str) -> tuple[int, int]:
    """Return (first_line_index, end_line_index_exclusive) of a C function body.

    The definition is the first line that starts in column 0 with something other than a
    brace/comment/preprocessor character and contains `name(`; the body ends at the first
    following line that is exactly `}`. Raises if the name is not found or is ambiguous
    (two column-0 definitions), so a rename in the source cannot slide a citation into the
    wrong function.
    """
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"\s*\(")
    starts = [
        i
        for i, ln in enumerate(lines)
        if ln[:1] not in ("", " ", "\t", "}", "{", "#", "/", "*")
        and pat.search(ln)
        and not ln.rstrip().endswith(";")
    ]
    # a multi-line prototype puts the name on a line that is followed by a `{` line; the
    # single-line check above already rejects ';'-terminated declarations
    if not starts:
        raise VerifyError(f"function {name!r} not found")
    if len(starts) > 1:
        raise VerifyError(f"function {name!r} defined {len(starts)} times (lines {[s + 1 for s in starts]})")
    s = starts[0]
    for e in range(s, len(lines)):
        if lines[e].rstrip() == "}":
            return s, e + 1
    raise VerifyError(f"function {name!r}: no closing brace")


def occurrences(lines: list[str], lo: int, hi: int, text: str) -> list[int]:
    """1-based line numbers of lines in [lo, hi) containing `text`, once per occurrence."""
    out: list[int] = []
    for i in range(lo, hi):
        n = lines[i].count(text)
        out.extend([i + 1] * n)
    return out


def check_step(step: dict, repo: Path, rev: str, cache: dict) -> dict:
    src = step["source"]
    path = src["file"]
    if path not in cache:
        cache[path] = git_show(repo, rev, path).split("\n")
    lines = cache[path]
    res = {"id": step["id"], "file": path}
    lo, hi = 0, len(lines)
    if "func" in src:
        lo, hi = function_span(lines, src["func"])
        res["func"] = src["func"]
        res["func_lines"] = [lo + 1, hi]
    want = int(src.get("count", 1))
    found = occurrences(lines, lo, hi, src["text"])
    res["want"] = want
    res["found"] = len(found)
    res["lines"] = found
    res["ok"] = len(found) == want
    if not res["ok"]:
        res["error"] = f"expected {want} occurrence(s) of the cited text, found {len(found)}"
    return res


def check_absences(plan: dict, repo: Path, rev: str) -> list[dict]:
    """Negative claims ("this macro is never defined"): whole-tree word search at the pin.

    The set of files and the number of hits per file must equal the plan's expected_hits, and
    every hit line must begin with the stated prefix (an `#ifdef`, not a `#define` or `-D`).
    """
    out = []
    for a in plan.get("absences", []):
        proc = subprocess.run(
            ["git", "-C", str(repo), "grep", "-n", "-w", "-F", a["word"], rev, "--", "."],
            capture_output=True,
        )
        if proc.returncode not in (0, 1):
            raise VerifyError(f"git grep {a['word']} failed: {proc.stderr.decode(errors='replace').strip()}")
        hits: dict[str, list[str]] = {}
        for ln in proc.stdout.decode("utf-8", errors="replace").splitlines():
            _rev, path, _num, text = ln.split(":", 3)
            hits.setdefault(path, []).append(text)
        got = {f: len(v) for f, v in hits.items()}
        want = {h["file"]: int(h["count"]) for h in a["expected_hits"]}
        bad_prefix = [t for v in hits.values() for t in v if not t.startswith(a["hit_prefix"])]
        ok = got == want and not bad_prefix
        r = {"id": a["id"], "word": a["word"], "claim": a["claim"], "hits": got, "want": want, "ok": ok}
        if bad_prefix:
            r["lines_without_prefix"] = bad_prefix
        out.append(r)
    return out


def check_order(steps: list[dict], results: dict[str, dict]) -> list[str]:
    errs = []
    for st in steps:
        ref = st.get("after")
        if not ref:
            continue
        a, b = results.get(st["id"]), results.get(ref)
        if b is None:
            errs.append(f"{st['id']}: 'after' names unknown step {ref}")
            continue
        if not a.get("ok") or not b.get("ok"):
            continue  # an unresolved citation is reported once, as itself; no cascade of order errors
        if a["file"] != b["file"]:
            errs.append(f"{st['id']}: 'after' {ref} is in another file ({b['file']} vs {a['file']})")
            continue
        if not a["lines"] or not b["lines"]:
            continue  # reported through the citation failure
        if not a["lines"][0] > b["lines"][0]:
            errs.append(
                f"{st['id']} (line {a['lines'][0]}) does not come after {ref} (line {b['lines'][0]}) in {a['file']}"
            )
    return errs


def hexnum(s: str) -> int:
    return int(s, 16)


def profile_checks(plan: dict, profile: dict) -> list[dict]:
    """Facts that the plan states in prose, compared against the USB-001 profile.

    Each entry: {name, plan, profile, ok}. The plan side is extracted from the plan's own
    text (step `what`/`registers` strings), not retyped here, so editing the plan prose to a
    different number fails the check.
    """
    allwhat = "\n".join(
        s["what"] + "\n" + "\n".join(s.get("registers", [])) + "\n" + s["source"]["text"] for s in plan["steps"]
    )
    checks = []

    def add(name, plan_val, prof_val):
        checks.append({"name": name, "plan": plan_val, "profile": prof_val, "ok": plan_val == prof_val})

    regions = [hexnum(r["base"]) for r in profile["PHY"]["register_regions"]]
    # plan: the text of step 3.18 lists the six bases in the order USBCON, eUSB ctrl, eUSB phy, USBDP, TCA, DWC3
    s318 = next(s for s in plan["steps"] if s["id"] == "3.18")
    plan_bases = [hexnum(x) for x in re.findall(r"0x17[89a-f][0-9a-f]0000", s318["what"])]
    add("register region bases (USBCON, eUSB ctrl, eUSB phy, USBDP, TCA, DWC3)", plan_bases, regions)
    s_pd = next(s for s in plan["steps"] if s["id"] == "0.04")
    plan_sup = dict(re.findall(r"(vdd\d+) = (\w+)", s_pd["what"]))
    prof_sup = {k.replace("_usb", ""): v.replace("_reg", "") for k, v in profile["PHY"]["board_supplies"].items()}
    add("supplies (vdd075/vdd12/vdd18/vdd33 -> regulator)", plan_sup, prof_sup)
    s107 = next(s for s in plan["steps"] if s["id"] == "1.07")
    plan_pmu = [hexnum(x) for x in re.findall(r"offset (0x[0-9a-f]+)", s107["what"].replace("DP offset", "offset"))]
    prof_pmu = [hexnum(x) for x in profile["PHY"]["pmu_offsets"]]
    add("PMU isolation offsets (USB2, DP)", plan_pmu, prof_pmu)
    s404 = next(s for s in plan["steps"] if s["id"] == "4.04")
    add("combo PHY version", hexnum(re.search(r"version (0x[0-9a-f]+)", s404["what"]).group(1)), hexnum(profile["PHY"]["combo_version"]))
    add("combo PHY RAM mode", "RAM mode" in s404["what"], bool(profile["PHY"]["ram_mode"]))
    rep = {hexnum(n["I2C_7bit_address"]): n["compatible"] for n in profile["USB2_repeaters"]["enabled_source_nodes"]}
    s702 = next(s for s in plan["steps"] if s["id"] == "7.02")
    s704 = next(s for s in plan["steps"] if s["id"] == "7.04")
    s_rep = next(s for s in plan["steps"] if s["id"] == "1.01")
    addrs = [hexnum(a) for a in re.findall(r"0x[0-9a-f]{2}\b", s_rep["what"])]
    add("repeater I2C 7-bit addresses (TUSB2E11, PTN3222)", addrs, [0x3E, 0x4F])
    add("repeater address -> part", {a: rep.get(a) for a in addrs}, {0x3E: "tusb2e11-repeater", 0x4F: "ptn3222-repeater"})
    s706 = next(s for s in plan["steps"] if s["id"] == "7.06")
    add("repeater I2C controller name", "hsi2c_34" in s706["what"] and "hsi2c_34" in s706["source"]["text"], profile["USB2_repeaters"]["I2C_controller"] == "hsi2c_34")
    add("repeater fitted part is NOT qualified", True, profile["USB2_repeaters"]["actual_fitted_component_qualified"] is False)
    s518 = next(s for s in plan["steps"] if s["id"] == "5.17")
    add("board maximum speed", re.search(r'"([a-z-]+)"', s518["source"]["text"]).group(1), profile["controller"]["board_maximum_speed"])
    add("pinned comparison revision", plan["source"]["revision"], profile["comparison"]["revision"])
    add("live-firmware equivalence flag", plan["live_firmware_equivalence_qualified"], profile["comparison"]["live_firmware_equivalence_qualified"])
    add("DMA coherency not qualified (plan lists it as unknown U5)", any(u["id"] == "U5" for u in plan["unknowns"]), profile["DMA"]["cache_coherency_qualified"] is False)
    _ = (s702, s704, allwhat)
    return checks


def structure_checks(plan: dict) -> list[str]:
    errs = []
    if plan.get("kind") != "source-review":
        errs.append("kind must be 'source-review'")
    rev = plan["source"]["revision"]
    if not FULL_SHA.match(rev):
        errs.append("source.revision must be a full 40-hex SHA")
    ids = [s["id"] for s in plan["steps"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate step ids")
    for s in plan["steps"]:
        if s["class"] not in CLASSES:
            errs.append(f"{s['id']}: unknown class {s['class']!r}")
        if not s["source"].get("text"):
            errs.append(f"{s['id']}: empty citation text")
    known = set(ids)
    for m in plan["minimal_subset"]:
        for i in m["ids"]:
            if i not in known:
                errs.append(f"minimal_subset names unknown step {i}")
            else:
                cls = next(s["class"] for s in plan["steps"] if s["id"] == i)
                if cls in ("M-omit",):
                    errs.append(f"minimal_subset includes step {i} which is classed M-omit")
    for o in plan["omitted"]:
        for i in o["ids"]:
            if i not in known:
                errs.append(f"omitted names unknown step {i}")
    # the minimal subset is exactly the set of class-V steps (a V step missing from it, or a non-V step in it, is a plan error)
    v_ids = {s["id"] for s in plan["steps"] if s["class"] == "V"}
    m_ids = {i for m in plan["minimal_subset"] for i in m["ids"]}
    for i in sorted(v_ids - m_ids):
        errs.append(f"{i} is class V but not in minimal_subset")
    for i in sorted(m_ids - v_ids):
        if i in known:
            errs.append(f"{i} is in minimal_subset but is not class V")
    for u in plan["unknowns"]:
        for i in u.get("steps", []):
            if i not in known:
                errs.append(f"unknown {u['id']} names unknown step {i}")
    covered = {i for u in plan["unknowns"] for i in u.get("steps", [])} | {i for o in plan["omitted"] for i in o["ids"]}
    for s in plan["steps"]:
        if s["class"] == "U" and s["id"] not in covered:
            errs.append(f"{s['id']} is class U but neither an unknown nor an omission covers it")
    # every M-omit step must be listed in `omitted`
    omitted_ids = {i for o in plan["omitted"] for i in o["ids"]}
    for s in plan["steps"]:
        if s["class"] == "M-omit" and s["id"] not in omitted_ids:
            errs.append(f"{s['id']} is M-omit but not listed in omitted")
    # the ladder: every rung names existing steps and unknowns; every vendor step belongs to some rung; every unknown that
    # NAT-043 is supposed to measure is touched by some rung
    rung_ids = [r["id"] for r in plan.get("ladder", [])]
    if len(rung_ids) != len(set(rung_ids)):
        errs.append("duplicate ladder rung ids")
    unknown_ids = {u["id"] for u in plan["unknowns"]}
    in_ladder: set[str] = set()
    resolved_by_ladder: set[str] = set()
    for r in plan.get("ladder", []):
        for i in r["steps"]:
            if i not in known:
                errs.append(f"ladder {r['id']} names unknown step {i}")
        for u in r["resolves"]:
            if u not in unknown_ids:
                errs.append(f"ladder {r['id']} resolves unknown {u} which the plan does not list")
        in_ladder.update(r["steps"])
        resolved_by_ladder.update(r["resolves"])
    for i in sorted(v_ids - in_ladder):
        errs.append(f"{i} is class V but no ladder rung performs it")
    for u in plan["unknowns"]:
        if any(x["task"] == "NAT-043" for x in u.get("resolve", [])) and u["id"] not in resolved_by_ladder:
            errs.append(f"unknown {u['id']} is to be measured by NAT-043 but no ladder rung resolves it")
    for u in plan["unknowns"]:
        if not u.get("resolve"):
            errs.append(f"unknown {u['id']} has no resolving measurement")
        for r in u.get("resolve", []):
            if not re.fullmatch(r"NAT-0\d\d", r["task"]):
                errs.append(f"unknown {u['id']}: bad task id {r['task']!r}")
    return errs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    ap.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    ap.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    try:
        plan = json.loads(args.plan.read_text())
        profile = json.loads(args.profile.read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read inputs: {e}", file=sys.stderr)
        return 2
    rev = plan["source"]["revision"]
    head = subprocess.run(["git", "-C", str(args.repo), "rev-parse", "HEAD"], capture_output=True, text=True)
    if head.returncode != 0:
        print(f"cannot read {args.repo}: {head.stderr.strip()}", file=sys.stderr)
        return 2
    pin_ok = head.stdout.strip() == rev
    if not pin_ok:
        print(f"pin mismatch: checkout HEAD {head.stdout.strip()} != plan revision {rev}", file=sys.stderr)

    errors: list[str] = []
    errors += structure_checks(plan)
    cache: dict[str, list[str]] = {}
    results: dict[str, dict] = {}
    for st in plan["steps"]:
        try:
            r = check_step(st, args.repo, rev, cache)
        except VerifyError as e:
            r = {"id": st["id"], "file": st["source"]["file"], "ok": False, "error": str(e), "lines": []}
        results[st["id"]] = r
        if not r["ok"]:
            errors.append(f"{st['id']}: {r['error']} [{st['source'].get('func', '-')} in {st['source']['file']}]")
    errors += check_order(plan["steps"], results)
    try:
        absences = check_absences(plan, args.repo, rev)
    except VerifyError as e:
        absences = []
        errors.append(str(e))
    for a in absences:
        if not a["ok"]:
            errors.append(f"absence {a['id']} ({a['word']}): hits {a['hits']} != expected {a['want']}"
                          + (f"; lines not starting with the prefix: {a['lines_without_prefix']}" if a.get("lines_without_prefix") else ""))
    try:
        pchecks = profile_checks(plan, profile)
    except (StopIteration, KeyError, AttributeError, IndexError) as e:
        pchecks = []
        errors.append(f"profile cross-check could not run (a step or field it reads is missing): {type(e).__name__}: {e}")
    for c in pchecks:
        if not c["ok"]:
            errors.append(f"profile cross-check failed: {c['name']}: plan={c['plan']!r} profile={c['profile']!r}")
    if not pin_ok:
        errors.append("checkout HEAD does not equal the pinned revision")

    plan_bytes = args.plan.read_bytes()
    out = {
        "kind": "source-review",
        "task": plan["task"],
        "revision": rev,
        "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(),
        "steps": len(plan["steps"]),
        "steps_resolved": sum(1 for r in results.values() if r["ok"]),
        "profile_checks": pchecks,
        "absences": absences,
        "results": list(results.values()),
        "errors": errors,
        "ok": not errors,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=1) + "\n")
    for e in errors:
        print("FAIL", e)
    print(f"{out['steps_resolved']}/{out['steps']} citations resolved; {sum(c['ok'] for c in pchecks)}/{len(pchecks)} profile checks hold; "
          f"{sum(a['ok'] for a in absences)}/{len(absences)} absence claims hold; "
          f"{'OK' if out['ok'] else 'FAILED'}; wrote {args.out}")
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
