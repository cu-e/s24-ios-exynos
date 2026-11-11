#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-059 mutation check: break the patch, the analyser or the driver in one way at a time and require that the tests fail. Evidence kind: host-test.

    <capture venv>/bin/python -W ignore -I docs/procedures/nat-059/mutants.py [--only M3,M5] [--json OUT]

Each mutant is a private copy of ONE file in a scratch directory, handed to the unchanged tests through NAT059_PATCH / NAT059_ANALYZE / NAT059_DRIVER;
nothing in the repository is modified. A control run without mutation must pass the same test selection. A mutant that survives is reported and
makes the exit code 1. Texts for patch_ckpt59.py are raw: the file holds the C text as Python string literals with backslash escapes."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRATCH = ROOT / "artifacts/nat-059/tmp"

P, A, D = "patch_ckpt59.py", "analyze_nat059.py", "session_nat059.py"
HOST = ("test_nat059.py", ["Derivation", "Words", "Host"])
VERD = ("test_nat059_run.py", ["Verdicts"])
FLOW = ("test_nat059_run.py", ["Derivation", "Flow"])
ENV = {P: "NAT059_PATCH", A: "NAT059_ANALYZE", D: "NAT059_DRIVER"}

MUTANTS = [
    # the patch: the C it derives (killed by the host build of the derived text, the payload words and the derivation checks)
    ("M1", P, r'"\tif (!NAT059_POST_VM(checkpoint)) {', r'"\tif (checkpoint < NAT059_FIRST_POST_VM) {', HOST, "the post-arm_vm_init test compares the id with 17 (30..44 are numerically above it)"),
    ("M2", P, r'\t\tt = st->kernel_ttbr0;\n\t} else {', r'\t\tt = st->kernel_ttbr0;\n\t} else if (0) {', HOST, "no stop is ever treated as post-arm_vm_init"),
    ("M3", P, r'(const volatile uint64_t *)(uintptr_t)st->ttep_pa & NAT059_TTBR0_MASK;', r'(const volatile uint64_t *)(uintptr_t)st->ttep_pa;', HOST, "the ASID-like bits of _invalid_ttep survive"),
    ("M4", P, r'\tif (d->action == NAT036_RESUME_C && !ok) {', r'\tif (d->action == NAT036_RESUME_C && !ok && 0) {', HOST, "an implausible TTBR0 is given to the kernel"),
    ("M5", P, r'\tst->ttep_pa = win_base + (uintptr_t)(NAT059_TTEP_VA - virt_base);\n', r'\tst->ttep_pa = win_base + (uintptr_t)(NAT059_TTEP_VA - virt_base) + 8;\n', HOST, "the stub reads the word after _invalid_ttep"),
    ("M6", P, r'\tif (NAT059_POST_VM(stops[nstops - 1]) &&\n', r'\tif (0 &&\n', HOST, "the arm_vm_init words are never checked"),
    ("M7", P, r'\tif (d->action != NAT036_RESUME_C && !d->final)\n\t\treturn;\n', r'\tif (d->action != NAT036_RESUME_C)\n\t\treturn;\n', HOST, "the final stop reports no TTBR0"),
    ("M8", P, r'\tif (rt)\n\t\tr.kttbr0 = rt;', r'\tif (0)\n\t\tr.kttbr0 = rt;', HOST, "the note does not show the TTBR0 the stub gives back"),
    ("M9", P, r'\t\tnat036_cres.ttbr0 = rt;\n', r'\t\tnat036_cres.ttbr0 = nat036_st.kernel_ttbr0;\n', HOST, "the resume gives back the checkpoint-5 table at every stop"),
    ("M10", P, "VMTTB_WORDS = (0xb0ffebd3,", "VMTTB_WORDS = (0xb0ffebd4,", HOST, "the pinned arm_vm_init word is not the payload's"),
    ("M11", P, r'NAT059_FIRST_POST_VM\t17u', r'NAT059_FIRST_POST_VM\t18u', HOST, "checkpoint 17 is treated as before arm_vm_init"),
    ("M12", P, "INVALID_TTEP_VA = 0xfffffff0071ac3e0", "INVALID_TTEP_VA = 0xfffffff0071ac3e8", HOST, "the pinned address of _invalid_ttep is wrong"),
    ("M13", P, r'NAT059_VMTTB_BAD = 8\t', r'NAT059_VMTTB_BAD = 0\t', HOST, "a wrong arm_vm_init returns the success code"),
    # the analyser
    ("M14", A, 'refused = [s for s in stops if s["mask"] & (D52.MASK_BAD_TTBR0 | D52.MASK_BAD_STATE)]', 'refused = [s for s in stops if s["mask"] & D52.MASK_BAD_STATE]', VERD, "the loader's TTBR0 refusal is not reported"),
    ("M15", A, 'refused = [s for s in stops if s["mask"] & (D52.MASK_BAD_TTBR0 | D52.MASK_BAD_STATE)]', 'refused = [s for s in stops if s["mask"] & D52.MASK_BAD_TTBR0]', VERD, "the loader's state refusal is not reported"),
    ("M16", A, "        if v == base:\n", "        if v == base and False:\n", VERD, "the old table after arm_vm_init passes"),
    ("M17", A, "if v == 0 or v & 0xfff or v >> 48:", "if v == 0 or v >> 48:", VERD, "an unaligned table base passes"),
    ("M18", A, "if v == 0 or v & 0xfff or v >> 48:", "if v & 0xfff or v >> 48:", VERD, "a zero table base passes"),
    ("M19", A, "if pre and len({s[\"kttbr0\"] for s in pre}) != 1:", "if pre and len({s[\"kttbr0\"] for s in pre}) > 1000:", VERD, "a table that changes before arm_vm_init passes"),
    ("M20", A, "        if len(values) != 1:\n", "        if len(values) > 1000:\n", VERD, "a table that changes after arm_vm_init passes"),
    ("M21", A, "PRE_VM_N = STOP_LIST.index(16) + 1", "PRE_VM_N = STOP_LIST.index(16)", VERD, "checkpoint 16's note is counted after arm_vm_init"),
    ("M22", A, "21)   # `last` of each arrival", "20)   # `last` of each arrival", VERD, "the list ends at 20"),
    ("M23", A, "why += ttbr0_problems(stops)\n", "", VERD, "the TTBR0 rules are not consulted"),
    # the driver
    ("M24", D, ",'NAT-058','NAT-059')", ",'NAT-059')", FLOW, "NAT-058 is not required done"),
    ("M25", D, "'artifacts/nat-059/native-attempt-%s-used.json'", "'artifacts/nat-057/native-attempt-%s-used.json'", FLOW, "the one-shot marker is in NAT-057's directory"),
    ("M26", D, "glob('*-nat059-%s-single-run-*.md'%image)", "glob('*-nat052-%s-single-run-*.md'%image)", FLOW, "the decision file of the previous image opens the gate"),
    ("M27", D, "PACKAGE=ROOT/'artifacts/nat-059/package-002'", "PACKAGE=ROOT/'artifacts/nat-052/package-002'", FLOW, "the driver reads the previous image's package"),
]


def run(test, classes, env_extra, py):
    env = dict(os.environ, TMPDIR=str(SCRATCH), NAT059_BEHAVIOUR_ONLY="0")
    env.update(env_extra)
    r = subprocess.run([py, "-W", "ignore", "-I", str(HERE / test), *classes], capture_output=True, text=True, env=env, timeout=1800)
    return r.returncode, (r.stderr or r.stdout)[-300:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--json")
    a = ap.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    results, survivors = [], []
    controls = {}
    for key in {m[4][0] for m in MUTANTS if only is None or m[0] in only}:
        sel = [m[4] for m in MUTANTS if m[4][0] == key][0]
        rc, tail = run(sel[0], sel[1], {}, sys.executable)
        controls[key] = rc
        print("control %s %s: %s" % (sel[0], sel[1], "PASS" if rc == 0 else "FAIL\n" + tail), flush=True)
        if rc:
            return 1
    for mid, fname, old, new, sel, why in MUTANTS:
        if only and mid not in only:
            continue
        text = (HERE / fname).read_text()
        if text.count(old) != 1:
            print("%s: the text to mutate occurs %d times in %s" % (mid, text.count(old), fname))
            return 2
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            f = Path(d) / fname
            f.write_text(text.replace(old, new))
            t0 = time.time()
            rc, tail = run(sel[0], sel[1], {ENV[fname]: str(f)}, sys.executable)
        killed = rc != 0
        results.append(dict(id=mid, file=fname, killed=killed, tests=sel[0] + ":" + ",".join(sel[1]), breaks=why, seconds=round(time.time() - t0, 1)))
        print("%-4s %-8s %s  (%s)" % (mid, "KILLED" if killed else "SURVIVED", why, fname), flush=True)
        if not killed:
            survivors.append(mid)
    print("%d/%d killed; survivors: %s" % (len(results) - len(survivors), len(results), ", ".join(survivors) or "none"))
    if a.json:
        Path(a.json).write_text(json.dumps(dict(results=results, survivors=survivors, controls=controls), indent=1) + "\n")
    return 1 if survivors else 0


if __name__ == "__main__":
    sys.exit(main())
