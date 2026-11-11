#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-062: derive the sources of loader-diag-xnu-run-usb: the NAT-059 image (loader-diag-xnu-ckpt4-usb) whose stub, at the last stop
(C checkpoint 21), sends the payload kernel's own console log over the USB engine and then RESUMES the kernel with no further stop
(instead of holding), and which, when the kernel returns by itself (reason 0), sends the log again and holds as before.

  patch_run62.py SOURCE_ROOT        (a tree already prepared by nat-059/build.py's prepare_tree)

Exact-match hunks over SOURCE_ROOT/shim/e1s-xnu/ckpt3.c (the stop handler) and markerlib52.c (the include of the dump code); each
anchor must occur exactly once or nothing is written. glue62.h / glue62_impl.h (src/) are copied next to them. The NAT-036 stub
assembly, the stop list, the resume rules of NAT-059 and every other file are untouched.

Why it is safe to resume after the last stop: the stub already resumes every earlier stop by giving the kernel back its TTBR0, SP, SCTLR
and registers; the last stop differs only in `slot[2]`, which is set to 0 -- loader_checkpoint(n) compares slot[2] with n, and 0 is no
checkpoint id (the ids are 1..5, 10..16, 17..21, 30..35, 40..44) -- so the kernel never stops again by itself. loader_return_entered
is cleared by the same code as for every resumed stop, so a later loader_return() (the boot-arg timer, a panic) can still hand control back."""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "src"

CKPT3_C = [
    ("include", '#include "glue52.h"\n', '#include "glue52.h"\n#include "glue62.h"\n'),
    ("stop-handler",
     "\tnat052_note_stop(&r);\n\tif (d.action == NAT036_HOLD)\n\t\tmk_ckpt3_hold(&r);\n",
     "\tnat052_note_stop(&r);\n"
     "\tif (d.final && rt && ttbr0_ok(rt)) {\t/* NAT-062: the last stop: send the kernel's log so far, then let the kernel run on */\n"
     "\t\tnat062_dump_log(f->x[0], f->x[1], nat036_st.s.pa_minus_va, NAT062_WHY_FINAL);\n"
     "\t\td.action = NAT036_RESUME_C;\n"
     "\t\td.next = 0;\t\t\t/* slot[2] = 0: no checkpoint id is 0, the kernel does not stop again */\n"
     "\t} else if ((f->x[2] & 0xff) == 0) {\t/* NAT-062: the kernel's own return: send the log it hands over, then hold as before */\n"
     "\t\tnat062_dump_log(f->x[0], f->x[1], nat036_st.s.pa_minus_va, NAT062_WHY_RETURN);\n"
     "\t}\n"
     "\tif (d.action == NAT036_HOLD)\n\t\tmk_ckpt3_hold(&r);\n"),
]

MARKERLIB52_C = [
    ("include", '#include "glue52_impl.h"\n', '#include "glue52_impl.h"\n#include "glue62_impl.h"\n'),
]


def patch_text(label, text, hunks):
    for key, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{label}: anchor '{key}' occurs {n} times, expected exactly once")
        text = text.replace(old, new)
    return text


def derive(e):
    """{path: text} for ckpt3.c and markerlib52.c of the tree at e (= SOURCE_ROOT/shim/e1s-xnu); nothing is written here."""
    e = Path(e)
    return {
        e / "ckpt3.c": patch_text("ckpt3.c", (e / "ckpt3.c").read_text(), CKPT3_C),
        e / "markerlib52.c": patch_text("markerlib52.c", (e / "markerlib52.c").read_text(), MARKERLIB52_C),
    }


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    e = Path(argv[1]) / "shim" / "e1s-xnu"
    for f in ("glue62.h", "glue62_impl.h"):
        if (e / f).exists():
            raise SystemExit(f"refusing to overwrite {e / f}")
    out = derive(e)
    for p, t in out.items():
        p.write_text(t)
    for f in ("glue62.h", "glue62_impl.h"):
        shutil.copy(SRC / f, e / f)
    print("wrote", ", ".join(p.name for p in out), "and copied glue62.h, glue62_impl.h")


if __name__ == "__main__":
    main(sys.argv)
