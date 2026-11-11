#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-067 mutation check: break the build module, the derivation, the derived driver, the analyser or the built artifacts in one way at a time and require that
test_nat067.py fails. Evidence kind: host-test.

    <venv with pyusb>/bin/python -W ignore -I docs/procedures/nat-067/mutants.py [--only B1,D3] [--json OUT]

A source mutant is a private copy of ONE file in a scratch tree that mirrors docs/procedures (symlinks to the real sibling directories, a private nat-067/ with the
mutated copy and symlinks to the rest, a symlink to the real artifacts/), handed to the unchanged tests through NAT067_BUILD / NAT067_DERIVE / NAT067_DRIVER /
NAT067_ANALYZE. An artifact mutant is a private copy of artifacts/nat-067/build-001 with one byte range changed, handed through NAT067_BUILD1 and NAT067_BUILD2 (both, so
that the two-builds-agree test is not what kills it). A mutant lists the test classes it is tried against; it is killed when that run fails. A control run without
mutation must pass the same selections. A survivor makes the exit code 1 unless it is listed in EQUIVALENT with the reason. Nothing in the repository is modified.
NAT-062's and NAT-065's own loader, stub, dump, probe and analyser-root mutants are not repeated (their mutants.py cover them); the driver's behaviour is NAT-062's,
pinned here by the text equality with the derivation and by the gate tests."""
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
SCRATCH = ROOT / "artifacts/nat-067/tmp"
TEST = HERE / "test_nat067.py"

B, D, S, A = "build.py", "derive.py", "session_nat067.py", "analyze_nat067.py"
ENV = {B: "NAT067_BUILD", D: "NAT067_DERIVE", S: "NAT067_DRIVER", A: "NAT067_ANALYZE"}
ALL = []                                  # every class
BUILD_SEL = ["Build"]
DRV_SEL = ["Driver"]
ANA_SEL = ["Analyser"]
ART_SEL = ["Build", "Payload"]
EQUIVALENT = {
    "D9": "the docstring-shape assertion only guards a NAT-065 docstring that has already been derived once; the derived file's text is pinned by the committed-driver equality test",
}
INVALID = ("SyntaxError", "IndentationError")

# (id, file, old, new, selection, what the mutant breaks)
SRC = [
    ("B1", B, 'NEW_TAG = "nat_attempt=NAT067-md0"', 'NEW_TAG = "nat_attempt=NAT065-md0"', BUILD_SEL, "the attempt tag is NAT-065's: the two images are not told apart by the kernel's command line"),
    ("B2", B, "cs_enforcement_disable=1 e1stouch=0 e1sbattery=0\"", "cs_enforcement_disable=1 e1sbattery=0\"", BUILD_SEL, "e1stouch=0 is not appended: the NAT-066 abort would recur"),
    ("B3", B, "cs_enforcement_disable=1 e1stouch=0 e1sbattery=0\"", "cs_enforcement_disable=1 e1stouch=0\"", BUILD_SEL, "e1sbattery=0 is not appended: the battery thread would bit-bang GPIO"),
    ("B4", B, "e1stouch=0 e1sbattery=0\"", "e1stouch=1 e1sbattery=0\"", BUILD_SEL, "e1stouch=1 leaves the touch driver on"),
    ("B5", B, "e1stouch=0 e1sbattery=0\"", "e1sbattery=0 e1stouch=0\"", BUILD_SEL, "the boot-args are appended in another order"),
    ("B6", B, 'NAME = "loader-diag-xnu-ne1-usb"', 'NAME = "loader-diag-xnu-ne2-usb"', BUILD_SEL, "another image name"),
    ("B7", B, "    b65.APPEND = APPEND\n", "    pass\n", BUILD_SEL, "configure() does not hand the appended boot-args to NAT-065's build"),
    ("B8", B, "    b65.NAME = NAME\n", "    pass\n", BUILD_SEL, "configure() does not hand the image name to NAT-065's build"),
    ("B9", B, "    b65.NEW_TAG = NEW_TAG\n", "    pass\n", BUILD_SEL, "configure() does not hand the tag to NAT-065's build"),
    ("D1", D, 't = sub(t, "artifacts/nat-065/package-001", "artifacts/nat-067/package-001")', 't = sub(t, "artifacts/nat-065/package-001", "artifacts/nat-065/package-001")', DRV_SEL, "the driver reads NAT-065's package"),
    ("D2", D, 't = sub(t, "*-nat065-%s-single-run-*.md", "*-nat067-%s-single-run-*.md")', 't = sub(t, "*-nat065-%s-single-run-*.md", "*-nat065-%s-single-run-*.md")', DRV_SEL, "the driver looks for NAT-065's decision file"),
    ("D3", D, 't = sub(t, "artifacts/nat-065/native-attempt-%s-used.json", "artifacts/nat-067/native-attempt-%s-used.json")', 't = sub(t, "artifacts/nat-065/native-attempt-%s-used.json", "artifacts/nat-065/native-attempt-%s-used.json")', DRV_SEL, "the one-shot marker is NAT-065's (a second launch is not stopped by this image's own marker)"),
    ("D4", D, "'NAT-065','NAT-066','NAT-067')\"", "'NAT-065','NAT-066')\"", DRV_SEL, "NAT-067 is not a precondition of the launch"),
    ("D5", D, "'NAT-065','NAT-066','NAT-067')\"", "'NAT-065','NAT-067')\"", DRV_SEL, "NAT-066 is not a precondition of the launch"),
    ("D6", D, "return pkg[\"recovery_sha256\"], pkg[\"payload_sha256\"], pkg[\"payload_bytes\"]", "return pkg[\"payload_sha256\"], pkg[\"recovery_sha256\"], pkg[\"payload_bytes\"]", DRV_SEL, "the RECOVERY and Image.payload hashes are swapped"),
    ("D7", D, '    assert text.count(old) == count, "expected %d of %r, found %d" % (count, old, text.count(old))\n', "", DRV_SEL, "a substitution that finds nothing (a drifted driver) is not refused"),
    ("D8", D, 't = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=%d" % canary_len)', 't = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=21878704")', DRV_SEL, "the payload length is not taken from the package"),
    ("D9", D, '    assert old_doc.count("\\n") == 14 and "NAT-065 session driver" in old_doc, "the NAT-065 docstring has changed shape"\n', "", DRV_SEL, "a changed NAT-065 docstring is not noticed"),
    ("S1", S, "glob('*-nat067-%s-single-run-*.md'%image)", "glob('*-nat065-%s-single-run-*.md'%image)", DRV_SEL, "the gate looks for NAT-065's decision file"),
    ("S2", S, "'NAT-065','NAT-066','NAT-067')", "'NAT-065','NAT-067')", DRV_SEL, "NAT-066 is not required done"),
    ("S3", S, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'])", DRV_SEL, "the decision file need not cite decision 0019"),
    ("S4", S, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['NEW_SHA'],'decision 0019')", DRV_SEL, "the decision file need not name the Image.payload hash"),
    ("S5", S, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['CANARY_SHA'],'decision 0019')", DRV_SEL, "the decision file need not name the RECOVERY hash"),
    ("S6", S, "if state['project']['permissions'].get('native') is not True:return 'registry native permission is not set: no launch'", "if False:return ''", DRV_SEL, "the registry's native permission is not required"),
    ("S7", S, "native[-1].get('decision')!='docs/decisions/'+decision.name", "False", DRV_SEL, "the native permit need not cite this decision file"),
    ("S8", S, "assert len(found)==1,", "assert len(found)>=1,", DRV_SEL, "two decision files are accepted"),
    ("S9", S, "TARGET='/dev/block/sda18'", "TARGET='/dev/block/sda17'", DRV_SEL, "another partition"),
    ("S10", S, "STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'", "STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf68'", DRV_SEL, "another stock image hash"),
    ("S11", S, "marker=ROOT/('artifacts/nat-067/native-attempt-%s-used.json'%a.image)", "marker=ROOT/('artifacts/nat-065/native-attempt-%s-used.json'%a.image)", DRV_SEL, "the one-shot marker is NAT-065's (source-text pin: the marker is inside main())"),
    ("A1", A, 'IMAGE = "loader-diag-xnu-ne1-usb"', 'IMAGE = "loader-diag-xnu-md0-usb"', ANA_SEL, "the analyser expects NAT-065's boot id"),
    ("A2", A, "    finally:\n        A65.IMAGE = old\n", "    finally:\n        pass\n", ANA_SEL, "NAT-065's name is not restored after a call"),
    ("A3", A, "    A65.analyze = analyze              # main() of NAT-065 calls analyze() by module-global name\n", "", ANA_SEL, "the command-line tool runs NAT-065's analysis under NAT-065's name"),
    ("A4", A, "classify_root = A65.classify_root", "classify_root = lambda texts: dict(outcome='probe-ran-to-exit', exit_status=81, pid=1)", ANA_SEL, "root is always probe-ran-to-exit"),
]

# artifact mutants: (id, file under build-001/<image>/, offset_of what, replacement, selection, what the mutant breaks); the payload sits at LOADER_IMAGE_BYTES in Image.payload
LOADER = 307200
ART = [
    ("X1", "Image.payload", b" e1sbattery=0", b"\0" * 13, ["Build", "Payload"], "the built command line lacks e1sbattery=0"),
    ("X2", "Image.payload", b" e1stouch=0", b"\0" * 11, ["Build", "Payload"], "the built command line lacks e1stouch=0"),
    ("X3", "Image.payload", b"NAT067-md0", b"NAT065-md0", ["Build", "Payload"], "the built tag is NAT-065's"),
    ("X4", "Image.payload", b"e1stouch=0 e1sbattery", b"e1stouch=1 e1sbattery", ["Build", "Payload"], "the built command line leaves the touch driver on"),
]


def run_tests(selection, env, scratch_py=None):
    argv = [sys.executable, "-W", "ignore", "-I", str(TEST)] + selection
    e = dict(os.environ)
    e.update(env)
    e["TMPDIR"] = os.environ.get("TMPDIR", "/home/egor/.cache/nat059-tmp")
    r = subprocess.run(argv, capture_output=True, text=True, env=e)
    return r.returncode, r.stdout + r.stderr


def tree_for(file, text, work):
    """A scratch mirror of docs/procedures holding the mutated file as nat-067/<file>."""
    proc = work / "docs/procedures"
    proc.mkdir(parents=True)
    for p in PROC.iterdir():
        if p.name != "nat-067" and p.is_dir():
            (proc / p.name).symlink_to(p)
    (work / "artifacts").symlink_to(ROOT / "artifacts")
    (work / "references").symlink_to(ROOT / "references")
    nat = proc / "nat-067"
    nat.mkdir()
    for p in HERE.iterdir():
        if p.name not in (file, "__pycache__"):
            (nat / p.name).symlink_to(p)
    out = nat / file
    out.write_text(text)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--json")
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    SCRATCH.mkdir(parents=True, exist_ok=True)
    results, survivors, invalid = [], [], []
    t0 = time.time()
    sels = sorted({tuple(m[4]) for m in SRC} | {tuple(m[4]) for m in ART})
    for sel in sels:
        rc, out = run_tests(list(sel), {})
        print("control %s: %s" % ("+".join(sel), "pass" if rc == 0 else "FAIL"))
        if rc:
            print(out[-1500:])
            return 2
    for mid, file, old, new, sel, what in SRC:
        if only and mid not in only:
            continue
        src = (HERE / file).read_text()
        assert src.count(old) == 1, (mid, "anchor not unique/found: %r" % old[:60])
        work = Path(tempfile.mkdtemp(prefix="mut-", dir=SCRATCH))
        try:
            path = tree_for(file, src.replace(old, new), work)
            rc, out = run_tests(sel, {ENV[file]: str(path)})
        finally:
            shutil.rmtree(work, ignore_errors=True)
        bad = rc != 0 and any(k in out for k in INVALID)
        status = "invalid" if bad else ("killed" if rc else ("equivalent" if mid in EQUIVALENT else "SURVIVED"))
        print("%-4s %-10s %s" % (mid, status, what))
        results.append(dict(id=mid, file=file, what=what, selection=sel, killed=bool(rc) and not bad, status=status))
        if status == "SURVIVED":
            survivors.append(mid)
        if bad:
            invalid.append(mid)
    for mid, rel, old, new, sel, what in ART:
        if only and mid not in only:
            continue
        work = Path(tempfile.mkdtemp(prefix="mut-", dir=SCRATCH))
        try:
            b1 = ROOT / "artifacts/nat-067/build-001"
            shutil.copytree(b1, work / "build", symlinks=True)
            f = work / "build" / "loader-diag-xnu-ne1-usb" / rel
            data = bytearray(f.read_bytes())
            assert data.count(old) == 1, (mid, "pattern not unique/found")
            i = bytes(data).index(old)
            data[i:i + len(old)] = new
            f.write_bytes(bytes(data))
            rc, out = run_tests(sel, {"NAT067_BUILD1": str(work / "build"), "NAT067_BUILD2": str(work / "build")})
        finally:
            shutil.rmtree(work, ignore_errors=True)
        status = "killed" if rc else "SURVIVED"
        print("%-4s %-10s %s" % (mid, status, what))
        results.append(dict(id=mid, file=rel, what=what, selection=sel, killed=bool(rc), status=status))
        if not rc:
            survivors.append(mid)
    killed = sum(1 for r in results if r["killed"])
    print("%d mutants: %d killed, %d equivalent, %d survived, %d invalid; %.0f s" % (len(results), killed, sum(r["status"] == "equivalent" for r in results), len(survivors), len(invalid), time.time() - t0))
    if a.json:
        Path(a.json).write_text(json.dumps(dict(results=results, survivors=survivors, invalid=invalid, equivalent=EQUIVALENT), indent=1) + "\n")
    return 1 if survivors or invalid else 0


if __name__ == "__main__":
    sys.exit(main())
