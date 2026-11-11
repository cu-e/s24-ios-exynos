#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-047: the source patch behind loader-diag-usbmon, applied to a loader source tree that nat-022/patch_loader.py (--trig-hold
--adt-aligned), NAT-022's marker.h / markerlib.c and nat-044/patch_loader4.py have already patched.

  patch_loader5.py SOURCE_ROOT

Exact-match replacements; each anchor must occur exactly once or the script fails before writing anything. What it does, and
nothing else:
  marker.h     one enumerator: MK_USB (frame kind 13)
  markerlib.c  includes usb47.h; mk_draw polls the engine once per band; mk_wait_tenths polls it in both loop forms; mk_stage
               announces the stage; mk_hold calls nat047_hold before its loop and shows nat047_show in it; mk_exception_loop
               records the fault first and shows nat047_show
  loader.c     includes usb47.h; log_char forwards each character; loader_main brings the transport up right after LOADER_MAIN
The new code is src/markerlib47.c (compiled instead of markerlib4.c); the engine and the ladder are not patched at all."""
import sys
from pathlib import Path

HUNKS = {
    "marker.h": [
        ("kind", "\tMK_RST = 14\t/* NAT-044 only: idx 0/1 INFORM3 hi/lo at entry, 2/3 INFORM2, 4/5 reboot-cmd, 6 status, 7 status drawn at once when the attempt failed (reset44.h) */\n",
         "\tMK_USB = 13,\t/* NAT-047 only: idx 0 status word, 1 ladder stop code, 2 its op, 3 record count, 5 engine bytes written (low 16) */\n"
         "\tMK_RST = 14\t/* NAT-044 only: idx 0/1 INFORM3 hi/lo at entry, 2/3 INFORM2, 4/5 reboot-cmd, 6 status, 7 status drawn at once when the attempt failed (reset44.h) */\n"),
    ],
    "markerlib.c": [
        ("include", "#include \"marker.h\"\n\n#ifndef MK_HOST\n",
         "#include \"marker.h\"\n#include \"usb47.h\"\n\n#ifndef MK_HOST\n"),
        ("draw", "\tfor (uint32_t b = 0; b < MK_BANDS; b++) {\n\t\tuint32_t v = mk_band_value(frame, b);\n",
         "\tfor (uint32_t b = 0; b < MK_BANDS; b++) {\n\t\tnat047_poll();\n\t\tuint32_t v = mk_band_value(frame, b);\n"),
        ("wait", "\twhile (mk_cnt() - s < t) { nat044_tick(); }\n#else\n\t(void)tenths;\n\tnat044_tick();\n#endif\n}\n",
         "\twhile (mk_cnt() - s < t) { nat044_tick(); nat047_poll(); }\n#else\n\t(void)tenths;\n\tnat044_tick();\n\tnat047_poll();\n#endif\n}\n"),
        ("stage", "__attribute__((noinline)) void mk_stage(uint32_t stage)\n{\n",
         "__attribute__((noinline)) void mk_stage(uint32_t stage)\n{\n\tnat047_stage(stage);\n"),
        ("hold", "\tmk_wait_tenths(MK_DWELL_TENTHS);\n\tfor (;;) {\n\t\tshow(&prev, mk_frame(MK_STAGE, 1, ld_mask), &ld_k);\n"
                 "\t\tshow(&prev, mk_frame(MK_STAGE, 2, code), &ld_k);\n\t\tnat044_show(&prev, &ld_k);\n",
         "\tmk_wait_tenths(MK_DWELL_TENTHS);\n\tnat047_hold(stage, code);\n\tfor (;;) {\n\t\tshow(&prev, mk_frame(MK_STAGE, 1, ld_mask), &ld_k);\n"
         "\t\tshow(&prev, mk_frame(MK_STAGE, 2, code), &ld_k);\n\t\tnat044_show(&prev, &ld_k);\n\t\tnat047_show(&prev, &ld_k);\n"),
        ("exc-record", "\tmk_draw(mk_frame(MK_STAGE, 0, MK_ST_EXC), 0, 1);\n",
         "\tnat047_fault(slot, esr, elr, far);\n\tmk_draw(mk_frame(MK_STAGE, 0, MK_ST_EXC), 0, 1);\n"),
        ("exc-show", "\t\tshow_kick_report(&prev, &k);\n\t}\n}\n\n/* Static frames repeat",
         "\t\tshow_kick_report(&prev, &k);\n\t\tnat047_show(&prev, &k);\n\t}\n}\n\n/* Static frames repeat"),
    ],
    "loader.c": [
        ("include", "#include \"marker.h\"\n/* Draw only on the validated framebuffer",
         "#include \"marker.h\"\n#include \"usb47.h\"\n/* Draw only on the validated framebuffer"),
        ("logchar", "static void log_char(char c)\n{\n\tuint32_t pos = loader_log.length;\n",
         "static void log_char(char c)\n{\n\tnat047_log_char(c);\n\tuint32_t pos = loader_log.length;\n"),
        ("bringup", "\tNAT022_STAGE(MK_ST_LOADER_MAIN);\n",
         "\tNAT022_STAGE(MK_ST_LOADER_MAIN);\n\tnat047_bringup((const char *)loader_log.text, loader_log.length);\n"),
    ],
}


def patch_text(name, text):
    for key, old, new in HUNKS[name]:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{name}: anchor '{key}' occurs {n} times, expected exactly once")
        text = text.replace(old, new)
    return text


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    e = Path(argv[1]) / "shim" / "e1s-xnu"
    new = {name: patch_text(name, (e / name).read_text()) for name in HUNKS}
    for name, text in new.items():
        (e / name).write_text(text)
    print("patched", ", ".join(HUNKS))


if __name__ == "__main__":
    main(sys.argv)
