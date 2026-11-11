#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-069 mutation check: break the build module, the derivation, the derived driver, the analyser, the pinned display patch (a private copy) or the built artifacts
in one way at a time and require that test_nat069.py fails. Evidence kind: host-test.

    <venv with pyusb>/bin/python -W ignore -I docs/procedures/nat-069/mutants.py [--only B1,D3] [--json OUT]

A source mutant is a private copy of ONE file in a scratch tree that mirrors docs/procedures (symlinks to the real sibling directories, a private nat-069/ with the
mutated copy and symlinks to the rest, a symlink to the real artifacts/ and references/), handed to the unchanged tests through NAT069_BUILD / NAT069_DERIVE /
NAT069_DRIVER / NAT069_ANALYZE. A patch mutant is a private copy of the pinned 0010-e1s-display.patch handed through NAT069_PATCH. An artifact mutant is a private copy of
artifacts/nat-069/build-001 with one byte range changed, handed through NAT069_BUILD1 and NAT069_BUILD2 (both, so that the two-builds-agree test is not what kills it).
A mutant lists the test classes it is tried against; it is killed when that run fails. A control run without mutation must pass the same selections. A survivor makes the
exit code 1 unless it is listed in EQUIVALENT with the reason. Nothing in the repository is modified.
NAT-062's, NAT-065's and NAT-067's own loader, stub, dump, probe and analyser-root mutants are not repeated (their mutants.py cover them); the driver's behaviour is
NAT-062's, pinned here by the text equality with the derivation and by the gate tests."""
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
SCRATCH = ROOT / "artifacts/nat-069/tmp"
TEST = HERE / "test_nat069.py"
PATCH = ROOT / "references/s24-port/xnu/e1s/patches/0010-e1s-display.patch"

B, D, S, A = "build.py", "derive.py", "session_nat069.py", "analyze_nat069.py"
ENV = {B: "NAT069_BUILD", D: "NAT069_DERIVE", S: "NAT069_DRIVER", A: "NAT069_ANALYZE"}
BUILD_SEL = ["Build"]
DRV_SEL = ["Driver"]
ANA_SEL = ["Analyser", "Display"]
DISP_SEL = ["Display"]
ART_SEL = ["Build", "Payload"]
PATCH_SEL = ["Kernel", "Display"]
EQUIVALENT = {
    "D9": "the docstring-shape assertion only guards a NAT-067 docstring that has already been derived once; the derived file's text is pinned by the committed-driver equality test",
    "M10": "when no e1s-display line is present the later branches return the same fork (framebuffer-only needs a framebuffer line, otherwise no-display-text): the early return is redundant",
}
INVALID = ("SyntaxError", "IndentationError")

# (id, file, old, new, selection, what the mutant breaks)
SRC = [
    ("B1", B, 'NEW_TAG = "nat_attempt=NAT069-md0"', 'NEW_TAG = "nat_attempt=NAT067-md0"', BUILD_SEL, "the attempt tag is NAT-067's: the two images are not told apart by the kernel's command line"),
    ("B2", B, 'APPEND = APPEND_NAT067 + " e1sdisp=2"', "APPEND = APPEND_NAT067", BUILD_SEL, "e1sdisp=2 is not appended: the pipeline would not be read"),
    ("B3", B, 'APPEND = APPEND_NAT067 + " e1sdisp=2"', 'APPEND = APPEND_NAT067 + " e1sdisp=1"', BUILD_SEL, "e1sdisp=1 prints the framebuffer only"),
    ("B4", B, 'APPEND = APPEND_NAT067 + " e1sdisp=2"', 'APPEND = APPEND_NAT067 + " e1sdisp=0"', BUILD_SEL, "e1sdisp=0 turns the probe off"),
    ("B5", B, 'NAME = "loader-diag-xnu-ne2-usb"', 'NAME = "loader-diag-xnu-ne1-usb"', BUILD_SEL, "NAT-067's image name"),
    ("B6", B, "    b65.APPEND = APPEND\n", "    pass\n", BUILD_SEL, "configure() does not hand the appended boot-args to NAT-065's build"),
    ("B7", B, "    b65.NAME = NAME\n", "    pass\n", BUILD_SEL, "configure() does not hand the image name to NAT-065's build"),
    ("B8", B, "    b65.NEW_TAG = NEW_TAG\n", "    pass\n", BUILD_SEL, "configure() does not hand the tag to NAT-065's build"),
    ("B9", B, 'e1stouch=0 e1sbattery=0"\nAPPEND =', 'e1stouch=0"\nAPPEND =', BUILD_SEL, "e1sbattery=0 is dropped: the battery thread would bit-bang GPIO again"),
    ("B10", B, 'cs_enforcement_disable=1 e1stouch=0', 'e1stouch=0', BUILD_SEL, "cs_enforcement_disable=1 is dropped: the probe would not be allowed to exec"),
    ("D1", D, 't = sub(t, "artifacts/nat-067/package-001", "artifacts/nat-069/package-001")', 't = sub(t, "artifacts/nat-067/package-001", "artifacts/nat-067/package-001")', DRV_SEL, "the driver reads NAT-067's package"),
    ("D2", D, 't = sub(t, "*-nat067-%s-single-run-*.md", "*-nat069-%s-single-run-*.md")', 't = sub(t, "*-nat067-%s-single-run-*.md", "*-nat067-%s-single-run-*.md")', DRV_SEL, "the driver looks for NAT-067's decision file"),
    ("D3", D, 't = sub(t, "artifacts/nat-067/native-attempt-%s-used.json", "artifacts/nat-069/native-attempt-%s-used.json")', 't = sub(t, "artifacts/nat-067/native-attempt-%s-used.json", "artifacts/nat-067/native-attempt-%s-used.json")', DRV_SEL, "the one-shot marker is NAT-067's"),
    ("D4", D, "'NAT-067','NAT-068','NAT-069')\"", "'NAT-067','NAT-068')\"", DRV_SEL, "NAT-069 is not a precondition of the launch"),
    ("D5", D, "'NAT-067','NAT-068','NAT-069')\"", "'NAT-067','NAT-069')\"", DRV_SEL, "NAT-068 is not a precondition of the launch"),
    ("D6", D, "return pkg[\"recovery_sha256\"], pkg[\"payload_sha256\"], pkg[\"payload_bytes\"]", "return pkg[\"payload_sha256\"], pkg[\"recovery_sha256\"], pkg[\"payload_bytes\"]", DRV_SEL, "the RECOVERY and Image.payload hashes are swapped"),
    ("D7", D, '    assert text.count(old) == count, "expected %d of %r, found %d" % (count, old, text.count(old))\n', "", DRV_SEL, "a substitution that finds nothing (a drifted driver) is not refused"),
    ("D8", D, 't = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=%d" % canary_len)', 't = sub(t, "CANARY_LEN=21878704", "CANARY_LEN=21878704")', DRV_SEL, "the payload length is not taken from the package"),
    ("D9", D, '    assert old_doc.count("\\n") == 13 and "NAT-067 session driver" in old_doc, "the NAT-067 docstring has changed shape"\n', "", DRV_SEL, "a changed NAT-067 docstring is not noticed"),
    ("S1", S, "glob('*-nat069-%s-single-run-*.md'%image)", "glob('*-nat067-%s-single-run-*.md'%image)", DRV_SEL, "the gate looks for NAT-067's decision file"),
    ("S2", S, "'NAT-065','NAT-066','NAT-067','NAT-068'", "'NAT-065','NAT-067','NAT-068'", DRV_SEL, "NAT-066 is not required done"),
    ("S3", S, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'])", DRV_SEL, "the decision file need not cite decision 0019"),
    ("S4", S, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['NEW_SHA'],'decision 0019')", DRV_SEL, "the decision file need not name the Image.payload hash"),
    ("S5", S, "for need in (cfg['NEW_SHA'],cfg['CANARY_SHA'],'decision 0019')", "for need in (cfg['CANARY_SHA'],'decision 0019')", DRV_SEL, "the decision file need not name the RECOVERY hash"),
    ("S6", S, "if state['project']['permissions'].get('native') is not True:return 'registry native permission is not set: no launch'", "if False:return ''", DRV_SEL, "the registry's native permission is not required"),
    ("S7", S, "native[-1].get('decision')!='docs/decisions/'+decision.name", "False", DRV_SEL, "the native permit need not cite this decision file"),
    ("S8", S, "assert len(found)==1,", "assert len(found)>=1,", DRV_SEL, "two decision files are accepted"),
    ("S9", S, "TARGET='/dev/block/sda18'", "TARGET='/dev/block/sda17'", DRV_SEL, "another partition"),
    ("S10", S, "STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67'", "STOCK_SHA='96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf68'", DRV_SEL, "another stock image hash"),
    ("S11", S, "marker=ROOT/('artifacts/nat-069/native-attempt-%s-used.json'%a.image)", "marker=ROOT/('artifacts/nat-067/native-attempt-%s-used.json'%a.image)", DRV_SEL, "the one-shot marker is NAT-067's (source-text pin: the marker is inside main())"),
    ("A1", A, 'IMAGE = "loader-diag-xnu-ne2-usb"', 'IMAGE = "loader-diag-xnu-ne1-usb"', ANA_SEL, "the analyser expects NAT-067's boot id"),
    ("A2", A, "    finally:\n        A65.IMAGE = old\n", "    finally:\n        pass\n", ANA_SEL, "NAT-065's name is not restored after a call"),
    ("A3", A, "    A65.analyze = analyze              # main() of NAT-065 calls analyze() by module-global name\n", "", ANA_SEL, "the command-line tool runs NAT-065's analysis under NAT-065's name"),
    ("A4", A, "classify_root = A65.classify_root", "classify_root = lambda texts: dict(outcome='probe-ran-to-exit', exit_status=81, pid=1)", ANA_SEL, "root is always probe-ran-to-exit"),
    ("A5", A, 'out["display"] = parse_display(text)', 'out["display"] = parse_display("")', ANA_SEL, "the display reading ignores the kernel log"),
    ("A6", A, 'text = "\\n".join(texts[k] for k in sorted(texts)) if texts else ""', 'text = texts[sorted(texts)[0]] if texts else ""', ANA_SEL, "only the first dump is read"),
    ("M1", A, 'if any(lo <= r["addr"] < hi for r in on):', 'if any(lo <= r["addr"] <= hi for r in on):', DISP_SEL, "the end of the framebuffer is inclusive: one row past it counts as the loader's buffer"),
    ("M2", A, 'fb["phys"] + fb["stride"] * fb["height"]', 'fb["phys"] + fb["width"] * fb["height"]', DISP_SEL, "the framebuffer size ignores the stride"),
    ("M3", A, 'running = any(x["run"] for x in d["decon"]) or any(w["on"] for w in d["windows"])', 'running = any(x["run"] for x in d["decon"])', DISP_SEL, "a window that is on does not count as running"),
    ("M4", A, 'return "decon-running-no-enabled-rdma" if any(x["run"] for x in d["decon"]) else "pipeline-idle"', 'return "pipeline-idle" if any(x["run"] for x in d["decon"]) else "decon-running-no-enabled-rdma"', DISP_SEL, "idle and running are swapped when no RDMA is enabled"),
    ("M5", A, 'and len(d["rdma"]) == N_RDMA and', 'and len(d["rdma"]) >= 0 and', DISP_SEL, "a pipeline with missing RDMA lines is complete"),
    ("M6", A, ' and d["dcphy"] is not None and d["dpu_mipi_phy_con"] is not None)', ' and d["dcphy"] is not None)', DISP_SEL, "a pipeline cut before the last line is complete"),
    ("M7", A, ' or (d["cannot_map_dsim1"] and len(d["dsim"]) == 1)', "", DISP_SEL, "a refused DSIM1 mapping makes the reading partial"),
    ("M8", A, '    if d["cannot_map"]:\n        return "cannot-map"\n', "", DISP_SEL, "a refused mapping is read as the framebuffer only"),
    ("M10", A, '    if d["lines"] == 0:\n        return "no-display-text"\n', "", DISP_SEL, "the early no-text return is removed"),
    ("M11", A, 'if fb is None:\n        return "scans-other-buffer"', 'if fb is None:\n        return "scans-loader-framebuffer"', DISP_SEL, "without a framebuffer report an enabled RDMA is taken for the loader's buffer"),
    ("M12", A, 'run=m.group(5) == "run"', "run=True", DISP_SEL, "every DECON is running"),
    ("M13", A, 'width=int(m.group(5)), height=int(m.group(6)),', 'width=int(m.group(6)), height=int(m.group(5)),', DISP_SEL, "RDMA width and height are swapped"),
    ("M14", A, 'addr=_i(m.group(8)))', 'addr=_i(m.group(7)))', DISP_SEL, "the RDMA address is the stride"),
    ("M15", A, 'if out["fork"] in ("scans-loader-framebuffer", "rdma-reads-framebuffer-decon-idle", "scans-other-buffer", "pipeline-idle", "decon-running-no-enabled-rdma"):', 'if False:', DISP_SEL, "no reading carries the caveat"),
    ("M16", A, 'out["fb_sum"] = _i(m.group(1))', 'out["fb_sum"] = None', DISP_SEL, "the framebuffer sample sum is not read"),
    ("M17", A, 'phys=_i(m.group(5)), virt=_i(m.group(6)))', 'phys=_i(m.group(6)), virt=_i(m.group(5)))', DISP_SEL, "framebuffer physical and virtual addresses are swapped"),
    ("M18", A, 'on=m.group(3) == "on", fmt=int(m.group(4))', 'on=m.group(3) == "off", fmt=int(m.group(4))', DISP_SEL, "RDMA on and off are swapped"),
]

# patch mutants: (id, old, new, what the mutant breaks); the patch is handed to the unchanged tests through NAT069_PATCH
PATCHM = [
    ("P1", "+\tdma = (volatile uint32_t *)ml_io_map(E1S_DMA0_PA, E1S_DMA0_SIZE);", "+\tdma = (volatile uint32_t *)ml_io_map(E1S_DMA0_PA, E1S_DMA0_SIZE);\n+\tdma[0] = 0;", "the pipeline function writes a mapped register"),
    ("P2", "+\tfor (i = 0; i < 2; i++) {\n+\t\tvolatile uint32_t *d = dsim;", "+\tdelay(1);\n+\tfor (i = 0; i < 2; i++) {\n+\t\tvolatile uint32_t *d = dsim;", "the pipeline function calls something other than the three whitelisted functions"),
    ("P3", "#define E1S_DECON0_MAIN_SIZE    0x4000U", "#define E1S_DECON0_MAIN_SIZE    0x2000U", "the DECON window is smaller than the offsets read from it"),
    ("P4", "e1s-display: DECON%u version", "e1s-display: DECON%u ver", "the DECON line has another format (the analyser would read nothing)"),
    ("P5", "uint32_t mode = 1;", "uint32_t mode = 2;", "the pipeline is read by default, without the boot-arg"),
    ("P6", "+\t\te1s_display_probe();            /* framebuffer and, opt-in, DECON/DSIM */", "+\t\t;", "bsd_init does not call the probe"),
    ("P7", "if (mode >= 2) {", "if (mode >= 1) {", "mode 1 reads the pipeline too"),
    ("P8", "+\treturn base[offset / 4];", "+\tbase[offset / 4] = 0;\n+\treturn 0;", "the read helper writes"),
]

# artifact mutants: (id, file under build-001/<image>/, pattern, replacement, selection, what the mutant breaks); the payload sits at LOADER_IMAGE_BYTES in Image.payload
ART = [
    ("X1", "Image.payload", b" e1sdisp=2", b"\0" * 10, ART_SEL, "the built command line lacks e1sdisp=2"),
    ("X2", "Image.payload", b"NAT069-md0", b"NAT067-md0", ART_SEL, "the built tag is NAT-067's"),
    ("X3", "Image.payload", b"e1sdisp=2", b"e1sdisp=1", ART_SEL, "the built command line only prints the framebuffer"),
    ("X4", "Image.payload", b"e1stouch=0 e1sbattery", b"e1stouch=1 e1sbattery", ART_SEL, "the built command line leaves the touch driver on"),
]


def run_tests(selection, env, scratch_py=None):
    argv = [sys.executable, "-W", "ignore", "-I", str(TEST)] + selection
    e = dict(os.environ)
    e.update(env)
    e["TMPDIR"] = os.environ.get("TMPDIR", "/home/egor/.cache/nat059-tmp")
    r = subprocess.run(argv, capture_output=True, text=True, env=e)
    return r.returncode, r.stdout + r.stderr


def tree_for(file, text, work):
    """A scratch mirror of docs/procedures holding the mutated file as nat-069/<file>."""
    proc = work / "docs/procedures"
    proc.mkdir(parents=True)
    for p in PROC.iterdir():
        if p.name != "nat-069" and p.is_dir():
            (proc / p.name).symlink_to(p)
    (work / "artifacts").symlink_to(ROOT / "artifacts")
    (work / "references").symlink_to(ROOT / "references")
    nat = proc / "nat-069"
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
    sels = sorted({tuple(m[4]) for m in SRC} | {tuple(m[4]) for m in ART} | {tuple(PATCH_SEL)})
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
    for mid, old, new, what in PATCHM:
        if only and mid not in only:
            continue
        src = PATCH.read_text()
        assert src.count(old) == 1, (mid, "anchor not unique/found: %r" % old[:60])
        work = Path(tempfile.mkdtemp(prefix="mut-", dir=SCRATCH))
        try:
            mp = work / "0010-e1s-display.patch"
            mp.write_text(src.replace(old, new))
            rc, out = run_tests(PATCH_SEL, {"NAT069_PATCH": str(mp)})
        finally:
            shutil.rmtree(work, ignore_errors=True)
        status = "killed" if rc else "SURVIVED"
        print("%-4s %-10s %s" % (mid, status, what))
        results.append(dict(id=mid, file="0010-e1s-display.patch", what=what, selection=PATCH_SEL, killed=bool(rc), status=status))
        if not rc:
            survivors.append(mid)
    for mid, rel, old, new, sel, what in ART:
        if only and mid not in only:
            continue
        work = Path(tempfile.mkdtemp(prefix="mut-", dir=SCRATCH))
        try:
            b1 = ROOT / "artifacts/nat-069/build-001"
            shutil.copytree(b1, work / "build", symlinks=True)
            f = work / "build" / "loader-diag-xnu-ne2-usb" / rel
            data = bytearray(f.read_bytes())
            assert data.count(old) == 1, (mid, "pattern not unique/found")
            i = bytes(data).index(old)
            data[i:i + len(old)] = new
            f.write_bytes(bytes(data))
            rc, out = run_tests(sel, {"NAT069_BUILD1": str(work / "build"), "NAT069_BUILD2": str(work / "build")})
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
