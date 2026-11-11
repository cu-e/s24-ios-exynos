#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-052 mutation check: break the glue or its patch in one way at a time, in a private copy of the procedures tree, and require that the
tests of the layers named for the mutant fail. A control run with no mutation must pass the same layers. Evidence kind: host-test.

    capvenv/bin/python -I docs/procedures/nat-052/mutants.py [--only M3,M5] [--json OUT]

The copy is  TMP/docs/procedures/nat-052  (real files, the mutation applied) next to symlinks to every other procedure directory and to the
repository's other top-level entries, so that nothing of the repository is modified. A mutant is KILLED when the named layers fail with the
mutation in and the same layers passed in the control. A mutant that survives is reported and makes the exit code 1."""
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
PROC = HERE.parent
ROOT = HERE.parents[2]

# (id, file under nat-052, old text, new text, test classes that must fail, what it breaks). Each old text must occur exactly once in
# the file. Texts for patch_ckpt52.py are raw strings: the file holds them as Python string literals with backslash escapes.
MUTANTS = [
    ("M1", "src/glue52_impl.h", r'__asm__ volatile("msr vbar_el1, %0\n\tisb" :: "r"(saved) : "memory");',
     '__asm__ volatile("nop" :: "r"(saved) : "memory");', ["UsbFull", "UsbEngineDown"], "vbar_leave does not give the kernel's vectors back"),
    ("M2", "src/glue52_impl.h", r'__asm__ volatile("msr vbar_el1, %0\n\tisb" :: "r"(g_nat052_loader_vbar) : "memory");',
     '__asm__ volatile("nop" :: "r"(g_nat052_loader_vbar) : "memory");', ["UsbFull", "UsbEngineDown"], "vbar_enter does not install the loader's vectors"),
    ("M3", "patch_ckpt52.py", r"\tnat052_vbar_leave(kv);\n", "", ["Patch", "Chain"], "nat036_ckpt_c never leaves the loader's vectors"),
    ("M4", "patch_ckpt52.py", r"\tkv = nat052_vbar_enter();\n\tnat052_note_stop(&r);\n", r"\tnat052_note_stop(&r);\n\tkv = nat052_vbar_enter();\n",
     ["Patch", "Chain"], "the note is written before the loader's vectors are in place"),
    ("M5", "patch_ckpt52.py", r"\tMK_USB = 15,", r"\tMK_USB = 13,", ["Patch"], "the USB report family keeps the frame kind of the checkpoint family"),
    ("M6", "patch_ckpt52.py", r"\tnat047_hold(MK_ST_CKPT, r->mask);\n", "", ["Patch", "UsbFull"], "the final hold is not announced to the host"),
    ("M7", "src/glue52_impl.h", 'p = n47_s(p, " x3=");', 'p = n47_s(p, " x4=");', ["Patch", "UsbFull"], "a label of the note is changed (writer and decoder disagree)"),
    ("M8", "src/glue52_impl.h", "\tmk_wait_tenths(NAT052_SERVICE_TENTHS);", "\t(void)0;", ["UsbFull"], "a pass has no service window"),
    ("M9", "patch_ckpt52.py", r'\n\tnat052_capture_vbar();\n"', r'\n"', ["Patch", "UsbFull"], "the loader's VBAR is never captured"),
    ("M10", "src/glue52_impl.h", "\tg_nat052_notes++;\n\tif (!n->up)\n\t\treturn;", "\tif (!n->up)\n\t\treturn;\n\tg_nat052_notes++;", ["UsbEngineDown", "UsbFull"],
     "the stop counter only counts while the engine is up"),
    ("M11", "patch_ckpt52.py", r"\t\tnat047_show(&prev, &ld_k);\n", "", ["Patch"], "the hold does not show the transport's frames"),
    ("M12", "src/glue52_impl.h", "\treturn cur;\n}\n\nvoid nat052_vbar_leave", "\treturn g_nat052_loader_vbar;\n}\n\nvoid nat052_vbar_leave", ["UsbFull"],
     "vbar_enter returns the loader's vectors as the value to restore"),
    ("M13", "src/glue52_impl.h", "\tif (!n->up)\n\t\treturn;\n\tsetups = n->m.setups;", "\tif (n->up)\n\t\treturn;\n\tsetups = n->m.setups;", ["UsbFull"],
     "a note is written only when the engine is down"),
    ("M14", "src/glue52_impl.h", "\tif ((r->x2 & 0xff) == 1) {", "\tif (0) {", ["UsbException"], "an early exception is reported without esr/elr/far"),
    ("M15", "src/glue52_impl.h", "\tg_nat052_last_setups = setups;\n", "", ["UsbFull"], "setups= is cumulative instead of the delta since the previous note"),
]

# Mutants that no test can tell from the original because no reachable state distinguishes them. They are reported and do not fail the run;
# a surviving mutant that is not listed here does.
EQUIVALENT = {
    "M10": "n->up is 0 until nat047_bringup (loader_main, before the kernel starts), becomes 1 once, and can only go back to 0 (poll fault); "
           "a note is written only while it is 1, so the counter reads the same in every note either way",
}


def make_tree(tmp, mutant):
    t = Path(tmp)
    (t / "docs/procedures").mkdir(parents=True)
    for e in (ROOT / "docs").iterdir():
        if e.name != "procedures":
            (t / "docs" / e.name).symlink_to(e)
    for e in ROOT.iterdir():
        if e.name not in ("docs", ".git") and not (t / e.name).exists():
            (t / e.name).symlink_to(e)
    for e in PROC.iterdir():
        if e.name != "nat-052":
            (t / "docs/procedures" / e.name).symlink_to(e)
    d = t / "docs/procedures/nat-052"
    shutil.copytree(HERE, d, ignore=shutil.ignore_patterns("__pycache__"))
    if mutant:
        _, rel, old, new, _, _ = mutant
        f = d / rel
        text = f.read_text()
        if text.count(old) != 1:
            raise SystemExit("%s: the text to mutate occurs %d times in %s" % (mutant[0], text.count(old), rel))
        f.write_text(text.replace(old, new))
    return d


def run_layers(d, layers):
    r = subprocess.run([sys.executable, "-W", "ignore", "-I", str(d / "test_nat052.py"), *layers], capture_output=True, text=True,
                       env=dict(os.environ, TMPDIR=os.environ.get("TMPDIR", "/tmp")))
    return r.returncode, r.stderr[-600:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    ap.add_argument("--json")
    a = ap.parse_args()
    only = set(filter(None, a.only.split(",")))
    results, t0 = [], time.time()
    layers_all = sorted({l for m in MUTANTS for l in m[4]})
    with tempfile.TemporaryDirectory() as tmp:
        d = make_tree(Path(tmp) / "control", None)
        rc, tail = run_layers(d, layers_all)
        results.append(dict(id="control", layers=layers_all, rc=rc, killed=None, ok=rc == 0))
        print("control", "passes" if rc == 0 else "FAILS\n" + tail, flush=True)
        if rc:
            sys.exit(2)
        for m in MUTANTS:
            if only and m[0] not in only:
                continue
            d = make_tree(Path(tmp) / m[0], m)
            rc, tail = run_layers(d, m[4])
            killed = rc != 0
            results.append(dict(id=m[0], what=m[5], layers=m[4], rc=rc, killed=killed))
            eq = EQUIVALENT.get(m[0]) if not killed else None
            results[-1]["equivalent"] = eq
            print(m[0], "KILLED" if killed else "SURVIVED (documented equivalent)" if eq else "SURVIVED", "-", m[5], "(%s)" % ",".join(m[4]), flush=True)
    survived = [r["id"] for r in results if r.get("killed") is False and not r.get("equivalent")]
    equivalent = [r["id"] for r in results if r.get("killed") is False and r.get("equivalent")]
    print("%d mutants, %d killed, %d documented equivalent, survived: %s, %.0f s" % (len(results) - 1, len(results) - 1 - len(survived) - len(equivalent),
                                                                              len(equivalent), survived or "none", time.time() - t0))
    if a.json:
        Path(a.json).write_text(json.dumps(dict(results=results, survived=survived, equivalent=equivalent), indent=1) + "\n")
    sys.exit(1 if survived else 0)


if __name__ == "__main__":
    main()
