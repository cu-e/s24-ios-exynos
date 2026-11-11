#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""NAT-044: the source patch behind loader-diag-reset, applied to a loader source tree that nat-022/patch_loader.py has
already patched (--trig-hold --adt-aligned) and whose shim/e1s-xnu already holds NAT-022's marker.h and markerlib.c.

  patch_loader4.py SOURCE_ROOT

Six exact-match replacements; each anchor must occur exactly once or the script fails before writing anything.
Base: the NAT-020 build-003 loader source (GPL-2.0, e1s loader) and NAT-022's marker.h / markerlib.c (GPL-2.0-only).
What the patch does, and nothing else:
  marker.h     two enumerators: MK_RST (frame kind 14), MK_ST_RESET (stage 0x41)
  markerlib.c  mk_wait_tenths polls nat044_tick() (the deadline); mk_hold's loop shows nat044_show() (the entry snapshot)
  guard.c      recovery_guard() calls nat044_snapshot() first and nat044_arm() right after the watchdog is armed
The new code is in src/markerlib4.c (compiled instead of markerlib.c) and src/reset44.h; the reset itself is the unmodified
NAT-042 module."""
import re
import sys
from pathlib import Path

WDT_RE = re.compile(r"s5e_wdt_arm\(&w,\s*(\d+)\)")

HUNKS = {
    "marker.h": [
        ("kind", "\tMK_CKPT2 = 12\t/* NAT-034 only, see enum mk_ckpt2_idx */\n",
         "\tMK_CKPT2 = 12,\t/* NAT-034 only, see enum mk_ckpt2_idx */\n"
         "\tMK_RST = 14\t/* NAT-044 only: idx 0/1 INFORM3 hi/lo at entry, 2/3 INFORM2, 4/5 reboot-cmd, 6 status, 7 status drawn at once when the attempt failed (reset44.h) */\n"),
        ("stage", "\tMK_ST_CKPT = 0x51\t/* NAT-031: only the return stub (mk_ckpt_pass / mk_ckpt_hold) may use it */\n",
         "\tMK_ST_CKPT = 0x51,\t/* NAT-031: only the return stub (mk_ckpt_pass / mk_ckpt_hold) may use it */\n"
         "\tMK_ST_RESET = 0x41\t/* NAT-044: drawn just before the reset into Download Mode is attempted */\n"),
    ],
    "markerlib.c": [
        ("wait",
         "static inline void mk_wait_tenths(uint32_t tenths)\n{\n#if !MK_SKIP_WAIT\n"
         "\tuint64_t f = mk_freq(), s = mk_cnt(), t = f / 10 * tenths;\n\twhile (mk_cnt() - s < t) { }\n#else\n"
         "\t(void)tenths;\n#endif\n}\n",
         "/* NAT-044: defined in markerlib4.c, the unit that is compiled instead of this file. */\n"
         "static void nat044_tick(void);\nstatic void nat044_show(uint32_t *prev, struct mk_kick *k);\n\n"
         "static inline void mk_wait_tenths(uint32_t tenths)\n{\n#if !MK_SKIP_WAIT\n"
         "\tuint64_t f = mk_freq(), s = mk_cnt(), t = f / 10 * tenths;\n\twhile (mk_cnt() - s < t) { nat044_tick(); }\n#else\n"
         "\t(void)tenths;\n\tnat044_tick();\n#endif\n}\n"),
        ("hold", "\t\tshow(&prev, mk_frame(MK_STAGE, 2, code), &ld_k);\n",
         "\t\tshow(&prev, mk_frame(MK_STAGE, 2, code), &ld_k);\n\t\tnat044_show(&prev, &ld_k);\n"),
    ],
    "guard.c": [
        ("externs", "extern void diagnostic_value(const char *, uint64_t);\n",
         "extern void diagnostic_value(const char *, uint64_t);\n"
         "extern void nat044_snapshot(volatile uint32_t *pmu);\nextern void nat044_arm(void);\n"),
        ("snapshot", "    diagnostic_value(\"panic_inform_before\",pmu[0xbc/4]);\n",
         "    nat044_snapshot(pmu);\n    diagnostic_value(\"panic_inform_before\",pmu[0xbc/4]);\n"),
        ("arm", "    if (s5e_wdt_arm(&w,83)) return -1;\n",
         "    if (s5e_wdt_arm(&w,83)) return -1;\n    nat044_arm();\n"),
    ],
}


def patch_text(name, text):
    for key, old, new in HUNKS[name]:
        n = text.count(old)
        if n != 1:
            raise SystemExit(f"{name}: anchor '{key}' occurs {n} times, expected exactly once")
        text = text.replace(old, new)
    return text


def wdt_seconds(guard_text):
    m = WDT_RE.search(guard_text)
    if not m:
        raise SystemExit("guard.c: no s5e_wdt_arm(&w, N) call")
    return int(m.group(1))


def main(argv):
    if len(argv) != 2:
        raise SystemExit(__doc__)
    e = Path(argv[1]) / "shim" / "e1s-xnu"
    new = {}
    for name in HUNKS:
        new[name] = patch_text(name, (e / name).read_text())
    for name, text in new.items():
        (e / name).write_text(text)
    print("patched", ", ".join(HUNKS), "WDT", wdt_seconds(new["guard.c"]), "s")


if __name__ == "__main__":
    main(sys.argv)
