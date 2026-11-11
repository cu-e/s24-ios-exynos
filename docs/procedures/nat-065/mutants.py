#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-065 mutation check: break the build, the probe init, the analyser or the driver in one way at a time and require that the tests fail.
Evidence kind: host-test.

    <capture venv>/bin/python -W ignore -I docs/procedures/nat-065/mutants.py [--only M3,M5] [--json OUT] [--check-anchors]

Each mutant is a private copy of ONE file in a scratch tree, handed to the unchanged tests through NAT065_BUILD / NAT065_PROBE / NAT065_ANALYZE /
NAT065_DRIVER; nothing in the repository is modified. For build.py and src/probe-init.S the scratch tree mirrors docs/procedures (symlinks to the real
sibling directories and a private nat-065/ with the mutated copy and src/), so the mutated build.py finds NAT-062's build and a mutated probe is the one
build_payload65 compiles. A mutant lists test selections; they are tried in order (cheap first) and the mutant is killed by the first that fails. Mutants of
the probe, the analyser and the driver run with NAT065_BEHAVIOUR_ONLY=1 (the tests that only pin source text are skipped, so a kill is a behavioural one).
A control run without mutation must pass the same selections. A survivor is reported and makes the exit code 1 unless it is listed in EQUIVALENT with the
reason it changes no observable behaviour. The NAT-062 loader, stub and dump code are NAT-062's (its own mutants.py covers them); the Verdicts layer of the
chain verdict is NAT-062's test re-targeted and is not re-run per mutant (it takes minutes)."""
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
PROC = HERE.parent
SCRATCH = ROOT / "artifacts/nat-065/tmp"

B, S, A, D = "build.py", "src/probe-init.S", "analyze_nat065.py", "session_nat065.py"
ENV = {B: "NAT065_BUILD", S: "NAT065_PROBE", A: "NAT065_ANALYZE", D: "NAT065_DRIVER"}
BUILD_SEL = ("test_nat065.py", ["Inputs", "Build", "Rebuild"])
PROBE_SEL = ("test_nat065.py", ["Ramdisk"])
ROOT_SEL = ("test_nat065_run.py", ["Root"])
DERIV_SEL = ("test_nat065_run.py", ["Derivation"])
THROUGH_SEL = ("test_nat065_run.py", ["RootThroughTheAnalyser"])
FLOW = ("test_nat065_run.py", ["Derivation", "Flow", "RealTreeGate"])
BEH = True
EQUIVALENT = {
    "M12": "the multiple-of-8 check on adt_off/adt_size guards a property of the pinned inputs, which the PIN check has already fixed; a payload that violates it cannot be "
           "made without changing a pinned input, and a test that feeds a bad value would only mirror the implementation",
    "M13": "mkpayload.py always writes SWEETXNU: the magic check cannot fire for the pinned inputs; the loader checks the magic again on the phone side (NAT-020)",
    "A10": "which of two dumps is read first only decides which duplicate wins: the ring is cumulative, so a line that appears in both dumps appears with the same stamp",
}
INVALID = ("SyntaxError", "IndentationError", "error: ", "probe build failed")      # a mutant that does not compile or parse is not a kill by a test

# (id, file, old, new, [selections], behavioural?, what the mutant breaks)
MUTANTS = [
    # ---- the build: the command line, the pins, the inputs
    ("M1", B, 'OLD_TAG = "nat_attempt=NAT020-83s"', 'OLD_TAG = "nat_attempt=NAT020-83x"', [BUILD_SEL], False, "the tag to replace is not the one in the NAT-020 command line"),
    ("M2", B, 'NEW_TAG = "nat_attempt=NAT065-md0"', 'NEW_TAG = "nat_attempt=NAT065-md1"', [BUILD_SEL], False, "the attempt tag is not the pinned one"),
    ("M3", B, 'APPEND = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1"', 'APPEND = " loader_return_after=8 cs_enforcement_disable=1"', [BUILD_SEL], False, "the init is not told which launchd variant to run"),
    ("M4", B, 'APPEND = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1"', 'APPEND = " loader_return_after=0 launchdsuffix=release cs_enforcement_disable=1"', [BUILD_SEL], False, "the kernel is told to return at once"),
    ("M5", B, 'APPEND = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1"', 'APPEND = " loader_return_after=8 launchdsuffix=release cs_enforcement_disable=0"', [BUILD_SEL], False, "code-signing enforcement stays on for the ad-hoc-signed init"),
    ("M6", B, "    if len(new) >= 256:", "    if len(new) >= 4096:", [BUILD_SEL], False, "a command line the kernel would cut is accepted"),
    ("M7", B, '    if not text.startswith("rd=md0 "):', "    if False:", [BUILD_SEL], False, "a NAT-020 line that no longer starts with rd=md0 is accepted"),
    ("M8", B, '"--cmdline", cmd, "--ramdisk", work / "probe-init"])', '"--cmdline", cmd])', [BUILD_SEL], False, "the payload is built without the ramdisk"),
    ("M9", B, '"--cmdline", cmd, "--ramdisk", work / "probe-init"])', '"--cmdline", data[CMDLINE_OFF:CMDLINE_OFF + CMDLINE_LEN].rstrip(b"\\0").decode(), "--ramdisk", work / "probe-init"])', [BUILD_SEL], False, "the NAT-020 command line is used as it is"),
    ("M10", B, '"e1s.adt": "1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e",', '"e1s.adt": "0ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e",', [BUILD_SEL], False, "the pinned device tree is not the one in artifacts/nat-020"),
    ("M11", B, '    if sha(data) != PIN["payload.bin"]:', "    if False:", [BUILD_SEL], False, "a payload that is not the pinned NAT-020 one is accepted"),
    ("M12", B, "    if adt_size & 7 or adt_off & 7:", "    if False:", [BUILD_SEL], False, "an ADT size that is not a multiple of 8 is accepted (the loader would refuse the payload on the phone)"),
    ("M13", B, '    if payload[:8] != b"SWEETXNU":', "    if False:", [BUILD_SEL], False, "a payload without the SWEETXNU magic is accepted"),
    ("M14", B, '    run([sys.executable, "-I", B3 / "source/tools/e1s/mkinit.py", obj, init])', '    run([sys.executable, "-I", B3 / "source/tools/e1s/mkinit.py", obj, init])\n    init.write_bytes(init.read_bytes() + b"\\0")', [BUILD_SEL], False, "the ramdisk gets a stray byte"),
    # ---- the probe init
    ("P1", S, "\tadd\tx0, x20, #0x50\t\t/* exit status 0x50 + PID: 81 for PID 1 */", "\tadd\tx0, x20, #0x51\t\t/* exit status 0x50 + PID: 81 for PID 1 */", [PROBE_SEL], BEH, "the exit status of PID 1 is 82"),
    ("P2", S, "\tmov\tx0, #0x60\t\t/* exit status 96: /dev/console could not be opened */", "\tmov\tx0, #0x61\t\t/* exit status 96: /dev/console could not be opened */", [PROBE_SEL], BEH, "the no-console exit status is 97"),
    ("P3", S, "\t.quad\t1\t\t\t/* tv_sec */", "\t.quad\t2\t\t\t/* tv_sec */", [PROBE_SEL], BEH, "the sleep is 2 s"),
    ("P4", S, "\tmov\tx16, #SYS_select\n\tsvc\t#0x80\n", "", [PROBE_SEL], BEH, "the init does not sleep"),
    ("P5", S, "write_console:\n\tmov\tx0, x19\n", "write_console:\n\tmov\tx0, #1\n", [PROBE_SEL], BEH, "the text goes to descriptor 1, not the console that was opened"),
    ("P6", S, "\tand\tx9, x9, #~15\n", "\tand\tx9, x9, #~7\n", [PROBE_SEL], BEH, "the stack is only 8-byte aligned"),
    ("P7", S, "\tmov\tx1, #O_RDWR\n", "\tmov\tx1, #0\n", [PROBE_SEL], BEH, "the console is opened read-only"),
    ("P8", S, "\tb.cs\tnoconsole\n", "\tb.cc\tnoconsole\n", [PROBE_SEL], BEH, "the carry test of the open() result is inverted"),
    ("P9", S, "\tadd\tw0, w0, #'0'\t\t/* PID 1 expected: one digit */", "\tadd\tw0, w0, #'1'\t\t/* PID 1 expected: one digit */", [PROBE_SEL], BEH, "the PID digit is off by one"),
    ("P10", S, "\tmov\tx20, x0\t\t\t/* the PID, for the exit status */", "\tmov\tx20, #1\t\t\t/* the PID, for the exit status */", [PROBE_SEL], BEH, "the exit status does not carry the PID"),
    ("P11", S, '\t.asciz\t"/dev/console"', '\t.asciz\t"/dev/consolx"', [PROBE_SEL], BEH, "another device node is opened"),
    ("P12", S, '\t.ascii\t"SWEET probe: done, exiting\\n"', '\t.ascii\t"SWEET probe: finished\\n"', [PROBE_SEL], BEH, "the closing line is not the one the analyser looks for"),
    ("P13", S, '\t.ascii\t"\\n*** SWEET userspace: init running as PID "', '\t.ascii\t"\\n*** SWEET userland: init running as PID "', [PROBE_SEL], BEH, "the banner is not the one the analyser looks for"),
    # ---- the analyser: what the kernel's text is read as
    ("A1", A, "        elif status == 96:", "        elif status == 95:", [ROOT_SEL], BEH, "the no-console exit status is not the probe's"),
    ("A2", A, "        elif 0x50 < status <= 0x59:", "        elif 0x50 <= status <= 0x59:", [ROOT_SEL], BEH, "status 80 (PID 0) counts as the probe"),
    ("A3", A, "        elif 0x50 < status <= 0x59:", "        elif 0x50 < status <= 0x5a:", [ROOT_SEL], BEH, "status 90 counts as the probe"),
    ("A4", A, '            out["pid"] = status - 0x50', '            out["pid"] = status - 0x51', [ROOT_SEL], BEH, "the PID is read wrongly from the status"),
    ("A5", A, "        if sig:\n", "        if False:\n", [ROOT_SEL], BEH, "an init killed by a signal is not named"),
    ("A6", A, '"root-device-missing" if "specified root memory device" in out["panic"] else "other-panic"', '"other-panic"', [ROOT_SEL], BEH, "the NAT-063 panic is not recognised"),
    ("A7", A, "USEC_PER_SEC_FIELD = 1024000", "USEC_PER_SEC_FIELD = 1000000", [ROOT_SEL], BEH, "the stamp is read as a decimal fraction"),
    ("A8", A, "    if t_root is not None and t_exit is not None and t_exit >= t_root:", "    if t_root is not None and t_exit is not None:", [ROOT_SEL], BEH, "a negative time from the root to the init's exit is reported"),
    ("A9", A, "    if t_b is not None and t_d is not None and t_d >= t_b:", "    if t_b is not None and t_d is not None:", [ROOT_SEL], BEH, "a negative sleep is reported"),
    ("A10", A, 'text = "\\n".join(texts[k] for k in sorted(texts)) if texts else ""', 'text = "\\n".join(texts[k] for k in reversed(sorted(texts))) if texts else ""', [ROOT_SEL], BEH, "the dumps are read in the other order"),
    ("A11", A, "    A62.IMAGE = IMAGE\n    try:", "    try:", [THROUGH_SEL], BEH, "NAT-062's image name is used for the boot lookup"),
    ("A12", A, "    finally:\n        A62.IMAGE = old\n", "    finally:\n        pass\n", [DERIV_SEL], BEH, "NAT-062's analyser keeps this image's name after an analysis"),
    ("A13", A, '    out["image"] = IMAGE\n', "", [THROUGH_SEL], BEH, "the verdict does not name this image"),
    ("A14", A, '    out["root"] = classify_root((kl or {}).get("texts") or {})', '    out["root"] = classify_root({})', [THROUGH_SEL], BEH, "the root reading ignores the delivered text"),
    ("A15", A, '^panic\\(cpu \\d+ caller 0x[0-9a-f]+\\): (.*?)\\r?$', 'panic\\(cpu \\d+ caller 0x[0-9a-f]+\\): (.*?)\\r?$', [ROOT_SEL], BEH, "a panic( in the middle of another line counts as the panic"),
    ("A16", A, "initproc (?:exited|failed to start) -- no exit reason", "initproc failed to start -- no exit reason", [ROOT_SEL], BEH, "one spelling of the init's end is not read"),
    ("A17", A, "        out[\"pid\"] = int(m.group(1))\n", "        out[\"pid\"] = 1\n", [ROOT_SEL], BEH, "the PID in the banner is not read"),
    ("A18", A, '    if m:\n        out["panic"] = m.group(1)', '    if m:\n        out["panic"] = m.group(1)[:20]', [ROOT_SEL], BEH, "the panic text is cut"),
    # ---- the driver (NAT-062's with these changes; the pins and gates are checked by the Derivation, Flow and RealTreeGate layers)
    ("D1", D, "'NAT-060','NAT-062','NAT-063',", "'NAT-060','NAT-063',", [FLOW], BEH, "NAT-062 is not required done"),
    ("D2", D, "'NAT-062','NAT-063','NAT-064',", "'NAT-062','NAT-064',", [FLOW], BEH, "NAT-063 (the first native run of the loader) is not required done"),
    ("D3", D, "'NAT-063','NAT-064','NAT-065')", "'NAT-063','NAT-065')", [FLOW], BEH, "NAT-064 (the ramdisk review) is not required done"),
    ("D4", D, "'NAT-064','NAT-065')", "'NAT-064')", [FLOW], BEH, "NAT-065 (this image) is not required done"),
    ("D5", D, "'NAT-058','NAT-059','NAT-060',", "'NAT-058','NAT-060',", [FLOW], BEH, "NAT-059 is not required done"),
    ("D6", D, "'artifacts/nat-065/native-attempt-%s-used.json'", "'artifacts/nat-062/native-attempt-%s-used.json'", [FLOW], BEH, "the one-shot marker is in NAT-062's directory"),
    ("D7", D, "glob('*-nat065-%s-single-run-*.md'%image)", "glob('*-nat062-%s-single-run-*.md'%image)", [FLOW], BEH, "the decision file of the previous run opens the gate"),
    ("D8", D, "PACKAGE=ROOT/'artifacts/nat-065/package-001'", "PACKAGE=ROOT/'artifacts/nat-062/package-001'", [FLOW], BEH, "the driver reads NAT-062's package"),
    ("D9", D, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA']):", [FLOW], BEH, "the decision file need not cite decision 0019"),
    ("D10", D, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['CANARY_SHA'],'decision 0019'):", [FLOW], BEH, "the decision file need not name the RECOVERY hash"),
    ("D11", D, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019'):", "for need in (cfg['NEW_SHA'],'decision 0019'):", [FLOW], BEH, "the decision file need not name the payload hash"),
    ("D12", D, "NEW_SHA='c6f4a6e45806edf211ce7de16bf0882268b3f8d22f065a21e575bdb66b06f34d',", "NEW_SHA='c6f4a6e45806edf211ce7de16bf0882268b3f8d22f065a21e575bdb66b06f34e',", [FLOW], BEH, "the pinned RECOVERY hash is wrong"),
    ("D13", D, "CANARY_LEN=21878704)", "CANARY_LEN=21878703)", [FLOW], BEH, "the pinned payload length is wrong"),
]


def run(test, classes, env_extra, py, beh):
    env = dict(os.environ, TMPDIR=str(SCRATCH), NAT065_BEHAVIOUR_ONLY="1" if beh else "0")
    env.update(env_extra)
    r = subprocess.run([py, "-W", "ignore", "-I", str(HERE / test), "-f", *classes], capture_output=True, text=True, env=env, timeout=1800)
    return r.returncode, (r.stderr or "") + (r.stdout or "")


def mutate(fname, old, new, d):
    """Write the mutated copy under d; -> {env var: path}. build.py and the probe go into a mirror of docs/procedures with a private nat-065/."""
    text = (HERE / fname).read_text()
    if text.count(old) != 1:
        return None
    if fname in (B, S):
        mirror = Path(d) / "procedures"
        mirror.mkdir()
        for sib in PROC.iterdir():
            if sib.is_dir() and sib.name != "nat-065":
                (mirror / sib.name).symlink_to(sib)
        mine = mirror / "nat-065"
        (mine / "src").mkdir(parents=True)
        for f in (HERE / "src").iterdir():
            shutil.copy(f, mine / "src" / f.name)
        shutil.copy(HERE / B, mine / B)
        target = mine / fname
        target.write_text(text.replace(old, new))
        return {"NAT065_BUILD": str(mine / B), "NAT065_PROBE": str(mine / S)}
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
                    if any(k in tail for k in INVALID):
                        invalid.append(mid)
                        break
                    killed_by = sel[0] + ":" + ",".join(sel[1])
                    break
        results.append(dict(id=mid, file=fname, killed=killed_by is not None, killed_by=killed_by, behavioural=beh, breaks=why, seconds=round(time.time() - t0, 1)))
        print("%-4s %-10s %s  (%s%s)" % (mid, "KILLED" if killed_by else ("EQUIVALENT" if mid in EQUIVALENT else "SURVIVED"), why, fname, "" if killed_by is None else "; " + killed_by), flush=True)
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
