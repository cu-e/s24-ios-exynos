#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-062 mutation check: break the patch, the build, the dump code, the analyser or the driver in one way at a time and require that the tests fail.
Evidence kind: host-test.

    <capture venv>/bin/python -W ignore -I docs/procedures/nat-062/mutants.py [--only M3,M5] [--json OUT] [--check-anchors]

Each mutant is a private copy of ONE file in a scratch directory, handed to the unchanged tests through NAT062_PATCH / NAT062_BUILD / NAT062_SRC (a directory
holding glue62.h and the mutated glue62_impl.h) / NAT062_ANALYZE / NAT062_DRIVER; nothing in the repository is modified. A mutant lists test selections;
they are tried in order (cheap first) and the mutant is killed by the first that fails. Mutants of the dump code, the analyser and the driver's
registry gates run with NAT062_BEHAVIOUR_ONLY=1 (the tests that only pin source text are skipped, so a kill is a behavioural one); mutants of the patch
and the build run without it, because the C they derive only exists on the aarch64 side and the Derivation layer's exact statements are the guard there.
A control run without mutation must pass the same selections. A survivor is reported and makes the exit code 1; the table below the mutants explains
why a survivor was rewritten or accepted. Texts for patch_run62.py are raw: the file holds the C text as Python string literals with backslash escapes."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
SCRATCH = ROOT / "artifacts/nat-062/tmp"

P, B, G, A, D = "patch_run62.py", "build.py", "src/glue62_impl.h", "analyze_nat062.py", "session_nat062.py"
ENV = {P: "NAT062_PATCH", B: "NAT062_BUILD", G: "NAT062_SRC", A: "NAT062_ANALYZE", D: "NAT062_DRIVER"}
HOST = ("test_nat062.py", ["Derivation", "Cmdline", "Host", "Parser", "Payload"])
PARSE = ("test_nat062.py", ["Parser", "Host"])
VERD = ("test_nat062_run.py", ["Verdicts"])
FLOW = ("test_nat062_run.py", ["Derivation", "Flow", "RealTreeGate"])
SRC_PIN = False         # the Derivation / Cmdline source-level checks are the guard (patch, build, driver pins)
BEH = True              # behavioural pass: source-pin tests skipped
EQUIVALENT = {      # survivors that change no observable behaviour; reported, not counted against the exit code
    "M32": "the escape form of a newline is not a contract: `\\x0a` decodes to the same byte, the analyser accepts both forms and NAT062_REC_MAX already allows four characters per byte; "
           "pinning the form would only mirror the implementation",
}
INVALID = ("SyntaxError", "IndentationError", ": error:", "-Werror")      # a mutant that breaks the build of the C harness or the parse of a script

# (id, file, old, new, [selections], behavioural?, what the mutant breaks)
MUTANTS = [
    # ---- the patch: the C it derives into ckpt3.c / markerlib52.c (aarch64-only; guarded by the Derivation layer's exact statements)
    ("M1", P, r"if (d.final && rt && ttbr0_ok(rt)) {", r"if (d.final && rt) {", [HOST], SRC_PIN, "the last stop is resumed without checking the TTBR0 it gives back"),
    ("M2", P, r"if (d.final && rt && ttbr0_ok(rt)) {", r"if (rt && ttbr0_ok(rt)) {", [HOST], SRC_PIN, "every C stop dumps and resumes as if it were the last one"),
    ("M3", P, r"\t\td.action = NAT036_RESUME_C;\n", r"\t\td.action = NAT036_HOLD;\n", [HOST], SRC_PIN, "the last stop holds after the dump instead of resuming the kernel"),
    ("M4", P, r"\t\td.next = 0;\t\t\t/* slot[2] = 0", r"\t\td.next = 21;\t\t\t/* slot[2] = 0", [HOST], SRC_PIN, "the kernel is told to stop at checkpoint 21 again"),
    ("M5", P, r"} else if ((f->x[2] & 0xff) == 0) {", r"} else if ((f->x[2] & 0xff) != 2) {", [HOST], SRC_PIN, "the return dump is taken for every arrival that is not a checkpoint"),
    ("M6", P, r"nat036_st.s.pa_minus_va, NAT062_WHY_FINAL);", r"nat036_st.s.pa_minus_va, NAT062_WHY_RETURN);", [HOST], SRC_PIN, "the last stop's dump is labelled as the return dump"),
    ("M7", P, r"nat062_dump_log(f->x[0], f->x[1], nat036_st.s.pa_minus_va, NAT062_WHY_FINAL);", r"nat062_dump_log(f->x[0], f->x[1], 0, NAT062_WHY_FINAL);", [HOST], SRC_PIN, "the PA-VA delta is not given to the dump"),
    ("M8", P, r"nat062_dump_log(f->x[0], f->x[1], nat036_st.s.pa_minus_va, NAT062_WHY_RETURN);", r"(void)0;", [HOST], SRC_PIN, "the kernel's return sends no log"),
    ("M9", P, """'#include "glue52_impl.h"\\n#include "glue62_impl.h"\\n'),""", """'#include "glue52_impl.h"\\n'),""", [HOST], SRC_PIN, "the dump code is not compiled into the loader"),
    ("M10", P, '     "\\tnat052_note_stop(&r);\\n"\n', "", [HOST], SRC_PIN, "the stop's own note is no longer sent before the dump"),
    # ---- the build: the kernel command line
    ("M11", B, 'APPEND = b" loader_return_after=8"', 'APPEND = b" loader_return_after=0"', [HOST], SRC_PIN, "the kernel is told to return at once (the boot-arg is not the planned 8 s)"),
    ("M12", B, 'APPEND = b" loader_return_after=8"', 'APPEND = b" loader_return_aft=8"', [HOST], SRC_PIN, "the boot-arg name is not the one the kernel parses"),
    ("M13", B, "CMDLINE_OFF = 0x48", "CMDLINE_OFF = 0x4c", [HOST], SRC_PIN, "a different byte range of the payload is patched"),
    ("M14", B, 'NEW_TAG = b"nat_attempt=NAT062-run"', 'NEW_TAG = b"nat_attempt=NAT062-rux"', [HOST], SRC_PIN, "the attempt tag in the command line is not the pinned one"),
    # ---- the dump code (host build of glue62_impl.h and a C harness)
    ("M15", G, "return x0 == NAT062_LOG_VA + pa_minus_va && x1 <= NAT062_LOG_MAX;", "return x0 == x0 + 0 * pa_minus_va && x1 <= NAT062_LOG_MAX;", [HOST], BEH, "any address is read, not only loader_log"),
    ("M16", G, "return x0 == NAT062_LOG_VA + pa_minus_va && x1 <= NAT062_LOG_MAX;", "return x0 == NAT062_LOG_VA + pa_minus_va && x1 <= NAT062_LOG_MAX + 0x1000000ULL;", [HOST], BEH, "a length beyond the array is accepted"),
    ("M17", G, "return x0 == NAT062_LOG_VA + pa_minus_va && x1 <= NAT062_LOG_MAX;", "return x0 == NAT062_LOG_VA + pa_minus_va && x1 < NAT062_LOG_MAX;", [HOST], BEH, "the largest legal length is refused"),
    ("M18", G, "#define NAT062_HEAD_FINAL\t8192u", "#define NAT062_HEAD_FINAL\t4096u", [HOST], BEH, "the final dump sends half the head"),
    ("M19", G, "#define NAT062_TAIL_RETURN\t32768u", "#define NAT062_TAIL_RETURN\t16384u", [HOST], BEH, "the return dump sends half the tail"),
    ("M20", G, "tmax = why == NAT062_WHY_FINAL ? NAT062_TAIL_FINAL : NAT062_TAIL_RETURN;", "tmax = why == NAT062_WHY_FINAL ? NAT062_TAIL_RETURN : NAT062_TAIL_FINAL;", [HOST], BEH, "the final and return tails are swapped"),
    ("M21", G, "tail = len - head < tmax ? len - head : tmax;", "tail = len < tmax ? len : tmax;", [HOST], BEH, "the tail may overlap the head"),
    ("M22", G, "head = len < hmax ? len : hmax;", "head = len < hmax + 0x1000000u ? len : hmax;", [HOST], BEH, "the whole log is sent as head"),
    ("M23", G, "\tn62_range(&o, x0, len - tail, len);\t/* the newest text first */\n\tn62_range(&o, x0, 0, head);\n", "\tn62_range(&o, x0, 0, head);\n\tn62_range(&o, x0, len - tail, len);\n", [HOST], BEH, "the oldest text is sent first (a deadline reset cuts the newest)"),
    ("M24", G, "p = n47_d(p, (int32_t)(len - head - tail));", "p = n47_d(p, (int32_t)(len - head));", [HOST], BEH, "the begin record's gap is wrong"),
    ("M25", G, "\tif (!N62_UP())\n\t\treturn;\n", "\tif (0 && !N62_UP())\n\t\treturn;\n", [HOST], BEH, "records are sent while the engine is down"),
    ("M26", G, "\t\tN62_EMIT(b, p);\n\t\tN62_WAIT();\n\t\treturn;\n", "\t\tN62_EMIT(b, p);\n\t\treturn;\n", [HOST], BEH, "the refusal record is not polled out"),
    ("M27", G, "if (o->sent >= NAT062_BURST) {", "if (o->sent >= NAT062_BURST * 4) {", [HOST], BEH, "the ring can wrap between two polls"),
    ("M28", G, "#define NAT062_RAW\t\t96u", "#define NAT062_RAW\t\t97u", [HOST], BEH, "the record stride is not the one the analyser expects"),
    ("M29", G, "for (int i = 20; i >= 0; i -= 4)", "for (int i = 16; i >= 0; i -= 4)", [HOST], BEH, "offsets are printed with 5 hex digits"),
    ("M30", G, "\t} else if (c >= 0x20 && c < 0x7f) {", "\t} else if (c >= 0x20 && c <= 0x7f) {", [HOST], BEH, "DEL goes out raw"),
    ("M31", G, "\tif (c == '\\\\') {\n\t\t*p++ = '\\\\';\n\t\t*p++ = '\\\\';\n\t} else if (c == '\\n') {", "\tif (0) {\n\t\t*p++ = '\\\\';\n\t\t*p++ = '\\\\';\n\t} else if (c == '\\n') {", [HOST], BEH, "a backslash in the kernel text is not escaped"),
    ("M32", G, "\t} else if (c == '\\n') {\n\t\t*p++ = '\\\\';\n\t\t*p++ = 'n';", "\t} else if (c == '\\n' && 0) {\n\t\t*p++ = '\\\\';\n\t\t*p++ = 'n';", [HOST], BEH, "a newline is sent as \\x0a (still decodable: expected to be an equivalent mutant unless the form is pinned)"),
    ("M33", G, "p = n47_d(p, (int32_t)o.bytes);", "p = n47_d(p, (int32_t)o.recs);", [HOST], BEH, "the end record's byte count is the record count"),
    ("M34", G, "\tN62_EMIT(b, p);\n\tN62_WAIT();\t/* the end record", "\tN62_EMIT(b, p);\n\t/* the end record", [HOST], BEH, "the end record is not polled out before the kernel runs"),
    ("M35", G, "n62_range(&o, x0, 0, head);\n\tp = b;", "n62_range(&o, x0, 1, head);\n\tp = b;", [HOST], BEH, "the first log byte is never sent"),
    ("M36", G, "uint32_t n = to - off < NAT062_RAW ? to - off : NAT062_RAW;", "uint32_t n = NAT062_RAW;", [HOST], BEH, "the last record of a range reads past the range"),
    ("M37", G, "#define NAT062_WAIT_TENTHS\t5u", "#define NAT062_WAIT_TENTHS\t1u", [HOST], BEH, "the poll after a burst is 0.1 s"),
    ("M38", G, "#define N62_WAIT()\tmk_wait_tenths(NAT062_WAIT_TENTHS)", "#define N62_WAIT()\tmk_wait_tenths(0)", [HOST], BEH, "the loader does not wait after a burst"),
    # ---- the analyser
    ("M39", A, '    if e["why"] != b["why"]:\n', "    if False:\n", [PARSE], BEH, "an end record of another kind of dump is accepted"),
    ("M40", A, 'if b["head"] + b["tail"] + b["gap"] != b["len"]:', 'if b["head"] + b["tail"] + b["gap"] > b["len"] + 10 ** 9:', [PARSE], BEH, "a begin record whose parts do not add up is accepted"),
    ("M41", A, "        if (b[\"head\"], b[\"tail\"]) != (head, tail):\n", "        if False:\n", [PARSE, VERD], BEH, "a dump that sends less than the image sends passes"),
    ("M42", A, "    if got != expect:\n", "    if False:\n", [PARSE], BEH, "missing, extra or reordered records are accepted"),
    ("M43", A, '    if e["recs"] != len(d["records"]) or e["bytes"] != sum(len(r) for _, r in d["records"]):', "    if False:", [PARSE], BEH, "the end record's counts are not compared"),
    ("M44", A, 'for lo, hi in ((b["len"] - b["tail"], b["len"]), (0, b["head"])):', 'for lo, hi in ((0, b["head"]), (b["len"] - b["tail"], b["len"])):', [PARSE], BEH, "the order of the records (newest first) is not required"),
    ("M45", A, "    if len(final) != 1:\n", "    if len(final) > 1000:\n", [VERD], BEH, "a missing or doubled final dump is accepted"),
    ("M46", A, '        elif d["line"] < last_stop:\n', "        elif False:\n", [VERD], BEH, "the final dump may come before the last stop's note"),
    ("M47", A, "    if len(returns) != 1:\n", "    if len(returns) > 1000:\n", [VERD], BEH, "two or no return notes are accepted"),
    ("M48", A, '    if len(ret) != 1 or len(after) != 1:\n', "    if len(ret) != 1:\n", [VERD], BEH, "a return dump that arrived before the return note is accepted"),
    ("M49", A, '    elif ret and any(d["end_line"] is not None and hold < d["end_line"] for d in ret):\n', "    elif False:\n", [VERD], BEH, "the HOLD may arrive before the return dump ends"),
    ("M50", A, "    if hold is None:\n        why.append(\"no HOLD record after the kernel's return\")", "    if False:\n        why.append(\"no HOLD record after the kernel's return\")", [VERD], BEH, "a missing HOLD after the return is accepted"),
    ("M51", A, "n[\"last\"] == STOP_LIST[-1]), default=None)", "n[\"last\"] == STOP_LIST[0]), default=None)", [VERD], BEH, "the last stop is the first stop's note"),
    ("M52", A, '    stops = [n for n in p["stops"] if n["x2"] != 0]\n', '    stops = list(p["stops"])\n', [VERD], BEH, "the kernel's return arrival is counted as a stop"),
    ("M53", A, '    if prog["return_notes"] and not prog["stops"]:\n', "    if False:\n", [VERD], BEH, "a return before the first stop is not named"),
    ("M54", A, "TAIL_MAX = {1: 8192, 2: 32768}", "TAIL_MAX = {1: 8192, 2: 8192}", [PARSE, VERD], BEH, "the return dump's tail is judged against the wrong size"),
    ("M55", A, "LOG_MAX = 0x180000", "LOG_MAX = 0x200000", [PARSE, VERD], BEH, "a length beyond the array is accepted"),
    ("M56", A, "RAW = 96 ", "RAW = 97 ", [PARSE], BEH, "the record stride is not the sender's"),
    ("M57", A, "            if not 0x20 <= ord(ch) < 0x7f:\n                return None\n", "            if False:\n                return None\n", [PARSE], BEH, "raw bytes outside printable ASCII are accepted as text"),
    ("M58", A, "            if cur is None:\n                stray.append((i, line))\n                continue\n", "            if cur is None:\n                continue\n", [PARSE], BEH, "an end record that closes nothing is ignored"),
    ("M59", A, "                r[\"len\"], r[\"head\"], r[\"tail\"], r[\"recs\"], r[\"gap\"]))", "                r[\"len\"], r[\"head\"], r[\"tail\"], f[\"recs\"], r[\"gap\"]))", [VERD], BEH, "the PASS sentence reports the final dump's record count for the return dump"),
    ("M60", A, "    A59.IMAGE = IMAGE\n    A59.note_problems = note_problems62\n", "    A59.note_problems = note_problems62\n", [VERD], BEH, "the old image's name is used for the boot lookup"),
    ("M61", A, "        m = PASS59.search(out.get(\"why\") or \"\")\n        if m and", "        m = PASS59.search(out.get(\"why\") or \"\")\n        if False and m and", [VERD], BEH, "the PASS sentence stays NAT-059's"),
    ("M62", A, '    gap = b"" if not b["gap"] else', '    gap = b"" if True else', [PARSE, VERD], BEH, "the marker for the bytes not sent is not written in the text"),
    # ---- the driver (the NAT-059 driver with these changes; the registry gates and the pins are checked by the Derivation, Flow and RealTreeGate layers)
    ("M63", D, "'NAT-060','NAT-062')", "'NAT-062')", [FLOW], BEH, "NAT-060 is not required done"),
    ("M64", D, "'artifacts/nat-062/native-attempt-%s-used.json'", "'artifacts/nat-059/native-attempt-%s-used.json'", [FLOW], BEH, "the one-shot marker is in NAT-059's directory"),
    ("M65", D, "glob('*-nat062-%s-single-run-*.md'%image)", "glob('*-nat059-%s-single-run-*.md'%image)", [FLOW], BEH, "the decision file of the previous image opens the gate"),
    ("M66", D, "PACKAGE=ROOT/'artifacts/nat-062/package-001'", "PACKAGE=ROOT/'artifacts/nat-059/package-002'", [FLOW], BEH, "the driver reads the previous image's package"),
    ("M67", D, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA']):", [FLOW], BEH, "the decision file need not cite decision 0019"),
    ("M68", D, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['CANARY_SHA'],'decision 0019'):", [FLOW], BEH, "the decision file need not name the RECOVERY hash"),
    ("M69", D, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['NEW_SHA'],'decision 0019'):", [FLOW], BEH, "the decision file need not name the payload hash"),
]


def run(test, classes, env_extra, py, beh):
    env = dict(os.environ, TMPDIR=str(SCRATCH), NAT062_BEHAVIOUR_ONLY="1" if beh else "0")
    env.update(env_extra)
    r = subprocess.run([py, "-W", "ignore", "-I", str(HERE / test), "-f", *classes], capture_output=True, text=True, env=env, timeout=1800)
    return r.returncode, (r.stderr or "") + (r.stdout or "")


def mutate(fname, old, new, d):
    """Write the mutated copy under d; -> {env var: path}."""
    text = (HERE / fname).read_text()
    if text.count(old) != 1:
        return None
    if fname == G:
        sub = Path(d) / "src"
        sub.mkdir()
        shutil.copy(HERE / "src/glue62.h", sub / "glue62.h")
        (sub / "glue62_impl.h").write_text(text.replace(old, new))
        return {ENV[fname]: str(sub)}
    f = Path(d) / Path(fname).name
    f.write_text(text.replace(old, new))
    return {ENV[fname]: str(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--json")
    ap.add_argument("--check-anchors", action="store_true", help="only verify that every text to mutate occurs exactly once")
    a = ap.parse_args()
    SCRATCH.mkdir(parents=True, exist_ok=True)
    only = set(a.only.split(",")) if a.only else None
    bad = [(m[0], m[1], (HERE / m[1]).read_text().count(m[2])) for m in MUTANTS if (HERE / m[1]).read_text().count(m[2]) != 1]
    for mid, f, n in bad:
        print("%s: the text to mutate occurs %d times in %s" % (mid, n, f))
    if bad:
        return 2
    if a.check_anchors:
        print("%d mutants, every anchor occurs exactly once" % len(MUTANTS))
        return 0
    selected = [m for m in MUTANTS if only is None or m[0] in only]
    results, survivors, controls, invalid = [], [], {}, []
    for sel, beh in sorted({((s[0], tuple(s[1])), m[5]) for m in selected for s in m[4]}, key=lambda x: (x[0][0], x[0][1], x[1])):
        rc, tail = run(sel[0], sel[1], {}, sys.executable, beh)
        tail = tail[-300:]
        controls["%s:%s:%s" % (sel[0], ",".join(sel[1]), "behaviour" if beh else "all")] = rc
        print("control %s %s %s: %s" % (sel[0], sel[1], "behaviour-only" if beh else "all tests", "PASS" if rc == 0 else "FAIL\n" + tail), flush=True)
        if rc:
            return 1
    for mid, fname, old, new, sels, beh, why in selected:
        t0 = time.time()
        killed_by = None
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            env = mutate(fname, old, new, d)
            for sel in sels:
                rc, tail = run(sel[0], sel[1], env, sys.executable, beh)
                if rc != 0:
                    if any(k in tail for k in INVALID):      # the mutant does not compile / parse: that is not a kill by a test
                        invalid.append(mid)
                        break
                    killed_by = sel[0] + ":" + ",".join(sel[1])
                    break
        results.append(dict(id=mid, file=fname, killed=killed_by is not None, killed_by=killed_by, behavioural=beh, breaks=why, seconds=round(time.time() - t0, 1)))
        print("%-4s %-8s %s  (%s%s)" % (mid, "KILLED" if killed_by else ("EQUIVALENT" if mid in EQUIVALENT else "SURVIVED"), why, fname, "" if killed_by is None else "; " + killed_by), flush=True)
        if killed_by is None and mid not in invalid and mid not in EQUIVALENT:
            survivors.append(mid)
        if mid in invalid:
            print("%s: INVALID MUTANT (it does not compile or parse: not a kill)" % mid)
    print("%d/%d killed; survivors: %s; invalid: %s" % (sum(1 for r in results if r["killed"]), len(results), ", ".join(survivors) or "none", ", ".join(invalid) or "none"))
    if a.json:
        Path(a.json).write_text(json.dumps(dict(results=results, survivors=survivors, equivalent=EQUIVALENT, invalid=invalid, controls=controls), indent=1) + "\n")
    return 1 if survivors or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
