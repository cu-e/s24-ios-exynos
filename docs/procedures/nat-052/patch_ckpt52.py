#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-052: derive the sources of an image that stops the payload kernel at its C checkpoints (NAT-036) and reports every stop over
the USB log engine (NAT-044 deadline/reset + NAT-047 transport), from a loader source tree that has been patched by
nat-036/patch_loader3.py, nat-044/patch_loader4.py and nat-047/patch_loader5.py in that order.

  patch_ckpt52.py SOURCE_ROOT

Writes into SOURCE_ROOT/shim/e1s-xnu: markerlib52.c (NAT-036's markerlib3.c with three changes), ckpt3.c (NAT-036's with the
VBAR swap and the stop note), and edits marker.h and loader.c in place. Exact-match replacements; each anchor must occur exactly
once or the script fails before writing anything.

  marker.h     MK_USB moves from frame kind 13 to 15: NAT-036 already uses 13 for MK_CKPT3, and a decoder cannot tell the two
               report families apart on one screen
  loader.c     declares and calls nat052_capture_vbar() right after nat047_bringup()
  markerlib52.c  includes markerlib47.c (instead of markerlib.c) and the glue; the pass uses nat052_service() instead of the
               1.2 s dwell; the final hold announces itself to the transport and shows the transport's frames
  ckpt3.c      nat036_ckpt_c installs the loader's vectors and notes the stop before it draws, and gives the kernel's vectors back
               before it returns"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROC = HERE.parent
SRC36 = PROC / "nat-036" / "src"
SRC52 = HERE / "src"

MARKERLIB52 = [
    ("include", '#include "markerlib.c"\n#include "marker3.h"\n',
     '#include "markerlib47.c"\n#include "marker3.h"\n#include "glue52.h"\n#include "glue52_impl.h"\n'),
    ("pass", "\tmk_draw(f, 0, 1);\t\t/* full redraw: whatever was on the bands before is not trusted */\n\tld_after_draw();\n}\n",
     "\tmk_draw(f, 0, 1);\t\t/* full redraw: whatever was on the bands before is not trusted */\n\tnat052_service();\n}\n"),
    ("hold-note", "\tmk_draw(prev, 0, 1);\n\tld_after_draw();\n\tfor (;;) {\n\t\tshow(&prev, mk_frame(MK_CKPT3, MK_C3_PASS, c3_pass(r)), &ld_k);\n",
     "\tmk_draw(prev, 0, 1);\n\tld_after_draw();\n\tnat047_hold(MK_ST_CKPT, r->mask);\n\tfor (;;) {\n"
     "\t\tshow(&prev, mk_frame(MK_CKPT3, MK_C3_PASS, c3_pass(r)), &ld_k);\n"),
    ("hold-show", "\t\tshow(&prev, mk_frame(MK_CKPT3, MK_C3_LIST, r->nstops), &ld_k);\n",
     "\t\tshow(&prev, mk_frame(MK_CKPT3, MK_C3_LIST, r->nstops), &ld_k);\n\t\tnat047_show(&prev, &ld_k);\n"),
]

CKPT3 = [
    ("include", '#include "ckpt3.h"\n', '#include "ckpt3.h"\n#include "glue52.h"\n'),
    ("enter", "\tnat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);\n\tif (d.action == NAT036_HOLD)\n",
     "\tnat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);\n\tkv = nat052_vbar_enter();\n\tnat052_note_stop(&r);\n\tif (d.action == NAT036_HOLD)\n"),
    ("decl", "\tstruct nat036_ret ret;\n\tuint64_t ttbr0, ttbr1, tcr, vbar;\n",
     "\tstruct nat036_ret ret;\n\tuint64_t ttbr0, ttbr1, tcr, vbar, kv;\n"),
    ("leave", "\t\tret.v = d.resume_pa;\n\t\tret.mode = 0;\n\t}\n\treturn ret;\n}\n",
     "\t\tret.v = d.resume_pa;\n\t\tret.mode = 0;\n\t}\n\tnat052_vbar_leave(kv);\n\treturn ret;\n}\n"),
]

MARKER_H = [
    ("usb", "\tMK_USB = 13,\t/* NAT-047 only:", "\tMK_USB = 15,\t/* NAT-047 only (moved from 13 by NAT-052: MK_CKPT3 is 13):"),
]

LOADER_C = [
    ("decl", '#include "usb47.h"\n/* Draw only on the validated framebuffer', '#include "usb47.h"\nvoid nat052_capture_vbar(void);\n/* Draw only on the validated framebuffer'),
    ("call", "\tnat047_bringup((const char *)loader_log.text, loader_log.length);\n",
     "\tnat047_bringup((const char *)loader_log.text, loader_log.length);\n\tnat052_capture_vbar();\n"),
]


def patch_text(label, text, hunks):
    for key, old, new in hunks:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{label}: anchor '{key}' occurs {n} times, expected exactly once")
        text = text.replace(old, new)
    return text


def nat047_hunks():
    """NAT-047's HUNKS with one anchor adapted: NAT-036's patch puts `#include "ckpt3.h"` between `#include "marker.h"` and the
    framebuffer comment of loader.c, where NAT-047's own anchor expects the comment right after marker.h. Everything else is
    NAT-047's, byte for byte (the test compares)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("nat047_patch_loader5", PROC / "nat-047" / "patch_loader5.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    h = {k: list(v) for k, v in m.HUNKS.items()}
    old = [i for i, (key, _, _) in enumerate(h["loader.c"]) if key == "include"]
    assert len(old) == 1
    h["loader.c"][old[0]] = ("include", '#include "marker.h"\n#include "ckpt3.h"\n/* Draw only on the validated framebuffer',
                             '#include "marker.h"\n#include "ckpt3.h"\n#include "usb47.h"\n/* Draw only on the validated framebuffer')
    return h, m.HUNKS


def apply_nat047(root):
    """patch_loader5.py's job over a tree that nat-036/patch_loader3.py has patched."""
    h, _ = nat047_hunks()
    e = Path(root) / "shim" / "e1s-xnu"
    new = {name: patch_text(name, (e / name).read_text(), hunks) for name, hunks in h.items()}
    for name, text in new.items():
        (e / name).write_text(text)
    return sorted(new)


def derive(e):
    """The four outputs as {path: text}; nothing is written here."""
    e = Path(e)
    return {
        e / "markerlib52.c": patch_text("markerlib3.c", (SRC36 / "markerlib3.c").read_text(), MARKERLIB52),
        e / "ckpt3.c": patch_text("ckpt3.c", (SRC36 / "ckpt3.c").read_text(), CKPT3),
        e / "marker.h": patch_text("marker.h", (e / "marker.h").read_text(), MARKER_H),
        e / "loader.c": patch_text("loader.c", (e / "loader.c").read_text(), LOADER_C),
    }


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    e = Path(argv[1]) / "shim" / "e1s-xnu"
    out = derive(e)
    for p, t in out.items():
        p.write_text(t)
    print("wrote", ", ".join(p.name for p in out))


if __name__ == "__main__":
    main(sys.argv)
