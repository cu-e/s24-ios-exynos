#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Mutation check for NAT-047: break one line of the NAT-047 sources at a time in a scratch copy of the procedure trees and
require test_nat047.py to fail. Host-only; it writes under --out and under the system temp directory and nowhere else.

    TMPDIR=<big dir> capvenv/bin/python -I docs/procedures/nat-047/mutate_nat047.py --out artifacts/nat-047/mutation-001 [--jobs 4]

Run it with an interpreter that has unicorn and capstone: most mutants are visible only to the aarch64 layers. A mutant that no
longer builds (`build.py --check-only` fails) is INVALID, not killed, and counts against the run. A mutant that is not killed
and has no documented reason (the 5th field) makes the exit status non-zero; a documented one is reported as `equivalent`.
Mutants are applied to NAT-047's own files only; the pinned NAT-041/042/045 files are compiled unmodified and are covered by
their own mutation runs."""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
M = "src/markerlib47.c"
P = "patch_loader5.py"
B = "build.py"
D = "decode47.py"
PK = "package.py"

# (name, file relative to nat-047, old, new, reason it cannot be observed | None); `old` must occur exactly once in the file
MUTANTS = [
    # --- poll and engine-out-of-service
    ("poll-without-up-guard", M, "if (!n->up || n->polling)\n\t\treturn;", "if (n->polling)\n\t\treturn;", None),
    ("poll-busy-flag-never-set", M, "\tn->polling = 1;\n\tusbmon_poll(&n->m);\n\tn->polling = 0;\n", "\tusbmon_poll(&n->m);\n", None),
    ("poll-reentry-guard-dropped", M, "if (!n->up || n->polling)", "if (!n->up)",
     "usbmon_poll() never calls back into the loader, and a fault inside it takes the engine out of service (up = 0) before any later call"),
    ("poll-fault-keeps-engine-up", M, "\t\tn->up = 0;\n\t\tn->poll_faulted = 1;\n", "\t\tn->poll_faulted = 1;\n", None),
    ("poll-fault-flag-dropped", M, "\t\tn->up = 0;\n\t\tn->poll_faulted = 1;\n", "\t\tn->up = 0;\n", None),
    # --- status word
    ("status-flags-not-masked-by-up", M, "uint32_t f = n->up ? n->m.flags : 0;", "uint32_t f = n->m.flags;", None),
    ("status-connected-reads-configured", M, "((f & USBMON_F_CONNECTED) ? N47_S_CONNECTED : 0)", "((f & USBMON_F_CONFIGURED) ? N47_S_CONNECTED : 0)", None),
    ("status-nonce-dropped", M, "((f & USBMON_F_NONCE_SET) ? N47_S_NONCE : 0)", "0", None),
    ("status-faulted-dropped", M, "(n->faulted ? N47_S_FAULTED : 0)", "0", None),
    ("status-poll-faulted-dropped", M, "(n->poll_faulted ? N47_S_POLLFAULT : 0)", "0", None),
    ("status-pd-was-on-dropped", M, "((n->lad.pd_was_on == 1 || n->lad_ro.pd_was_on == 1) ? N47_S_PDWASON : 0)", "0", None),
    ("status-phase-shift", M, "((n->phase & 0xfu) << 8)", "((n->phase & 0xfu) << 4)", None),
    ("status-rung-shift", M, "((uint32_t)(n->lad.rung_done & 0xf) << 12)", "((uint32_t)(n->lad.rung_done & 0xf) << 11)", None),
    ("status-connected-bit-moved", M, "#define N47_S_CONNECTED\t0x0002u", "#define N47_S_CONNECTED\t0x0008u", None),
    ("draw-status-wrong-idx", M, "mk_draw(mk_frame(MK_USB, N47_I_STATUS, n47_status()), 0, 1);", "mk_draw(mk_frame(MK_USB, N47_I_ERR, n47_status()), 0, 1);", None),
    ("draw-before-ladder-ro-dropped", M, "\tn->phase = N47_LAD_RO;\n\tn->err_op = 0xffffu;\n\tn47_draw_status();\n", "\tn->phase = N47_LAD_RO;\n\tn->err_op = 0xffffu;\n", None),
    ("draw-before-ladder-w-dropped", M, "\tn->phase = N47_LAD_W;\n\tn47_draw_status();\n", "\tn->phase = N47_LAD_W;\n", None),
    ("draw-before-start-dropped", M, "\tn->phase = N47_START;\n\tn47_draw_status();\n", "\tn->phase = N47_START;\n", None),
    ("draw-before-connect-wait-dropped", M, "\tn->phase = N47_CONNECT;\n\tn47_draw_status();\n", "\tn->phase = N47_CONNECT;\n", None),
    ("draw-after-connect-wait-dropped", M, "\tn->phase = N47_UP;\n\tn47_draw_status();\n", "\tn->phase = N47_UP;\n",
     "the hold loop draws the same status frame within the same second; only the dwell of one frame is lost"),
    ("show-err-sign", M, "(uint32_t)(-n->err) & 0xffffu", "(uint32_t)(n->err) & 0xffffu", None),
    ("show-err-op-reads-nrec", M, "mk_frame(MK_USB, N47_I_ERROP, n->err_op)", "mk_frame(MK_USB, N47_I_ERROP, n->nrec)", None),
    ("show-nrec-reads-err-op", M, "mk_frame(MK_USB, N47_I_NREC, n->nrec)", "mk_frame(MK_USB, N47_I_NREC, n->err_op)", None),
    ("show-written-zero", M, "n->up ? (uint32_t)n->m.written : 0", "0", None),
    ("show-nrec-frame-dropped", M, "\tshow(prev, mk_frame(MK_USB, N47_I_NREC, n->nrec), k);\n", "", None),
    ("note-stop-err-dropped", M, "\tn->err = err;\n\tn->err_op", "\t(void)err;\n\tn->err_op", None),
    ("note-stop-err-op-dropped", M, "n->err_op = s ? s->err_op : 0xffffu;", "n->err_op = 0xffffu;", None),
    ("note-stop-nrec-dropped", M, "n->nrec = s ? s->nrec : 0;", "n->nrec = 0;", None),
    ("note-stop-phase-dropped", M, "\tn->phase = N47_STOP;\n", "", None),
    # --- stages
    ("stage-without-up-guard", M, "\tif (!g_nat047.up)\n\t\treturn;\n\tusbmon_stage(&g_nat047.m, stage, n47_stage_name(stage));", "\tusbmon_stage(&g_nat047.m, stage, n47_stage_name(stage));", None),
    ("stage-name-mem", M, 'case MK_ST_LOADER_MEM: return "mem";', 'case MK_ST_LOADER_MEM: return "zero";', None),
    ("stage-name-entry", M, 'case MK_ST_ENTRY: return "entry";', 'case MK_ST_ENTRY: return "start";', None),
    ("stage-name-fail", M, 'case MK_ST_LOADER_FAIL: return "fail";', 'case MK_ST_LOADER_FAIL: return "failed";', None),
    ("stage-name-reset", M, 'case MK_ST_RESET: return "reset";', 'case MK_ST_RESET: return "stage";', None),
    ("stage-name-exception", M, 'case MK_ST_EXC: return "exception";', 'case MK_ST_EXC: return "fault";', None),
    ("stage-name-default", M, 'default: return "stage";', 'default: return "unknown";', None),
    ("bringup-stage-announce-dropped", M, "\tnat047_stage(MK_ST_LOADER_MAIN);", "\t;", None),
    # --- loader log forwarding
    ("log-char-without-log-on-guard", M, "\tif (!n->log_on)\n\t\treturn;\n\tif (c == '\\n') {", "\tif (c == '\\n') {", None),
    ("log-on-never-set", M, "\tn->log_on = 1;\n\tn->phase = N47_CONNECT;\n", "\tn->phase = N47_CONNECT;\n", None),
    ("log-newline-does-not-flush", M, "\tif (c == '\\n') {\n\t\tn47_flush_line();\n\t\treturn;\n\t}", "\tif (c == '\\n') {\n\t\treturn;\n\t}", None),
    ("log-line-limit-off-by-one", M, "if (n->line_len >= NAT047_LINE_MAX)", "if (n->line_len > NAT047_LINE_MAX)", None),
    ("log-line-max-100", M, "#define NAT047_LINE_MAX\t\t200u", "#define NAT047_LINE_MAX\t\t100u", None),
    ("log-flush-empty-lines", M, "\tif (n->line_len)\n\t\tusbmon_log(", "\tusbmon_log(", None),
    ("log-flush-keeps-length", M, "\tn->line_len = 0;\n}\n\nvoid nat047_log_char", "}\n\nvoid nat047_log_char", None),
    ("log-chunk-256", M, "#define NAT047_CHUNK\t\t512u", "#define NAT047_CHUNK\t\t256u", None),
    ("log-chunk-step", M, "off += NAT047_CHUNK)", "off += NAT047_CHUNK - 1)", None),
    ("log-replay-skipped", M, "for (uint32_t off = 0; off < log_len; off += NAT047_CHUNK)", "for (uint32_t off = log_len; off < log_len; off += NAT047_CHUNK)", None),
    # --- ladder and engine start
    ("ladder-ro-may-power-on", M, "c.allow_pd_poweron = 0;", "c.allow_pd_poweron = 1;",
     "allow_pd_poweron is read only by the rung-3 power-on rows (nat-045/src/ladder.c) and the read-only ladder stops after rung 2 "
     "(stop_after = 2, guarded by ladder-ro-runs-three-rungs), so the flag is never consulted; the 0 is defence in depth"),
    ("ladder-ro-runs-three-rungs", M, "c.stop_after = 2;", "c.stop_after = 3;", None),
    ("ladder-w-may-not-power-on", M, "c.allow_pd_poweron = 1;", "c.allow_pd_poweron = 0;", None),
    ("ladder-w-stops-at-rung-4", M, "c.stop_after = LAD_LAST_RUNG;", "c.stop_after = 4;", None),
    ("ladder-ro-failure-ignored", M, "n47_note_stop(e, &n->lad_ro);\n\t\tn47_draw_status();\n\t\treturn;", "n47_note_stop(e, &n->lad_ro);\n\t\tn47_draw_status();",
     "the read-only rungs 1-2 read registers without NOTALIVE checks: the device model cannot make them fail"),
    ("ladder-w-failure-ignored", M, "n47_note_stop(e, &n->lad);\n\t\tn47_draw_status();\n\t\treturn;", "n47_note_stop(e, &n->lad);\n\t\tn47_draw_status();", None),
    ("start-failure-ignored", M, "n47_note_stop(e, 0);\n\t\tn47_draw_status();\n\t\treturn;", "n47_note_stop(e, 0);\n\t\tn47_draw_status();", None),
    ("ladder-report-order", M, "\tn47_report_ladder('R', &n->lad_ro);\n\tn47_report_ladder('W', &n->lad);\n", "\tn47_report_ladder('W', &n->lad);\n\tn47_report_ladder('R', &n->lad_ro);\n", None),
    ("boot-record-tag", M, "p = n47_s(p, NAT047_TAG);", 'p = n47_s(p, "image");', None),
    ("boot-record-deadline", M, "p = n47_d(p, NAT044_DEADLINE_S);", "p = n47_d(p, NAT044_DEADLINE_S + 1);", None),
    ("boot-record-fault-setting", M, "p = n47_d(p, NAT047_FAULT);", "p = n47_d(p, 0);", None),
    ("boot-id-head-zeroed", M, "uc.boot_id[i] = (uint8_t)(id >> (8 * i));", "uc.boot_id[i] = (uint8_t)((id >> (8 * i)) & 0);", None),
    ("boot-id-halves-swapped", M, "uc.boot_id[i] = (uint8_t)(id >> (8 * i));\n\t\tuc.boot_id[8 + i] = (uint8_t)(h >> (8 * i));",
     "uc.boot_id[i] = (uint8_t)(h >> (8 * i));\n\t\tuc.boot_id[8 + i] = (uint8_t)(id >> (8 * i));", None),
    ("boot-id-fnv-basis", M, "0xcbf29ce484222325ull", "0xcbf29ce484222326ull", None),
    ("boot-id-fnv-prime", M, "h *= 0x100000001b3ull;", "h *= 0x100000001b4ull;", None),
    ("engine-fladj-off-by-one", M, "#define NAT047_FLADJ\t\t0x20u", "#define NAT047_FLADJ\t\t0x21u", None),
    ("engine-fladj-not-passed", M, "uc.fladj = NAT047_FLADJ;", "uc.fladj = 0;", None),
    ("engine-lpm-sel-off", M, "#define NAT047_LPM_SEL\t\t1u", "#define NAT047_LPM_SEL\t\t0u",
     "the engine applies the LPM selection only together with refclk_hz, which is 0 here (README: reference clock unknown)"),
    ("engine-refclk-given", M, "uc.refclk_hz = 0;", "uc.refclk_hz = 24000000;", None),
    ("engine-dwc3-base-moved", M, "0x17900000UL", "0x17910000UL", None),
    ("engine-ring-size-halved", M, "uc.ring_size = NAT047_RING_BYTES;", "uc.ring_size = NAT047_RING_BYTES / 2;", None),
    ("engine-ring-bytes-changed", M, "#define NAT047_RING_BYTES\t32768u", "#define NAT047_RING_BYTES\t16384u", None),
    # --- bounded waits
    ("connect-wait-unbounded", M, "mk_cnt() - t0 < lim) {\n\t\t\tnat044_tick();\n\t\t\tnat047_poll();\n\t\t}\n\t}\n\tn->connect_err", "mk_cnt() - t0 < lim + (1ull << 62)) {\n\t\t\tnat044_tick();\n\t\t\tnat047_poll();\n\t\t}\n\t}\n\tn->connect_err", None),
    ("connect-wait-skipped", M, "while (!(n->m.flags & USBMON_F_CONNECTED) && mk_cnt() - t0 < lim) {", "while (!(n->m.flags & USBMON_F_CONNECTED) && mk_cnt() - t0 < lim / 1024) {", None),
    ("connect-wait-30s", M, "#define NAT047_CONNECT_S\t3u", "#define NAT047_CONNECT_S\t30u", None),
    ("connect-error-inverted", M, "n->connect_err = (n->m.flags & USBMON_F_CONNECTED) ? 0 : LAD_ERR(LAD_USB_RUNG_CONNECT, LAD_E_TIMEOUT);",
     "n->connect_err = (n->m.flags & USBMON_F_CONNECTED) ? LAD_ERR(LAD_USB_RUNG_CONNECT, LAD_E_TIMEOUT) : 0;", None),
    ("connect-loop-without-poll", M, "\t\t\tnat044_tick();\n\t\t\tnat047_poll();\n\t\t}\n\t}\n\tn->connect_err", "\t\t\tnat044_tick();\n\t\t}\n\t}\n\tn->connect_err", None),
    ("config-wait-unbounded", M, "while (!(n->m.flags & USBMON_F_CONFIGURED) && mk_cnt() - t0 < lim) {", "while (!(n->m.flags & USBMON_F_CONFIGURED) && mk_cnt() - t0 < lim + (1ull << 62)) {", None),
    ("config-wait-skipped", M, "while (!(n->m.flags & USBMON_F_CONFIGURED) && mk_cnt() - t0 < lim) {", "while (!(n->m.flags & USBMON_F_CONFIGURED) && mk_cnt() - t0 < lim / 1024) {", None),
    ("config-wait-1s", M, "#define NAT047_CONFIG_S\t\t8u", "#define NAT047_CONFIG_S\t\t1u", None),
    ("config-wait-20s", M, "#define NAT047_CONFIG_S\t\t8u", "#define NAT047_CONFIG_S\t\t20u", None),
    # --- hold and the controlled fault
    ("hold-note-dropped", M, "\tn47_text(b, p);\n#if NAT047_FAULT", "#if NAT047_FAULT", None),
    ("hold-without-up-guard", M, "\tn->holds++;\n\tif (!n->up)\n\t\treturn;\n", "\tn->holds++;\n", None),
    ("hold-count-dropped", M, "\tn->holds++;\n", "", None),
    ("hold-brk-at-wrong-stage", M, "if (stage == MK_ST_PRE_JUMP) {", "if (stage == MK_ST_LOADER_MAIN) {", None),
    ("hold-brk-note-dropped", M, '\t\tusbmon_text(&n->m, "controlled BRK #0x1234 follows");\n', "", None),
    ("hold-brk-dropped", M, '\t\t__asm__ volatile("brk #0x1234");\n', "", None),
    # --- exception record
    ("fault-count-dropped", M, "\tn->faulted++;\n", "", None),
    ("fault-reentry-guard-dropped", M, "\tif (n->in_fault)\n\t\treturn;\n", "",
     "the exception loop calls nat047_fault once; nothing re-enters it"),
    ("fault-without-up-guard", M, "\tif (!n->up)\n\t\treturn;\n\t__asm__ volatile(\"mrs %0, spsr_el1\"", "\t__asm__ volatile(\"mrs %0, spsr_el1\"", None),
    ("fault-esr-elr-swapped", M, "\tin.esr = esr;\n\tin.elr = elr;\n", "\tin.esr = elr;\n\tin.elr = esr;\n", None),
    ("fault-far-dropped", M, "\tin.far = far;\n", "\tin.far = 0;\n", None),
    ("fault-spsr-zeroed", M, "\tin.spsr = spsr;\n", "\tin.spsr = 0;\n", None),
    ("fault-sp-zeroed", M, "\tin.sp = sp;\n", "\tin.sp = 0;\n", None),
    ("fault-stage-not-announced", M, "\tusbmon_stage(&n->m, MK_ST_EXC, n47_stage_name(MK_ST_EXC));\n", "", None),
    ("fault-slot-off-by-one", M, "p = n47_d(p, (int32_t)slot);", "p = n47_d(p, (int32_t)slot + 1);", None),
    ("fault-text-elr-shows-esr", M, 'p = n47_s(p, " elr=");\n\tp = n47_x(p, elr);', 'p = n47_s(p, " elr=");\n\tp = n47_x(p, esr);', None),
    ("fault-text-far-dropped", M, 'p = n47_s(p, " far=");\n\tp = n47_x(p, far);', 'p = n47_s(p, " far=");\n\tp = n47_x(p, 0);', None),
    ("fault-record-not-written", M, "\tusbmon_fault_record(&n->m, &in);\n", "", None),
    # --- the patch
    ("patch-kind-value", P, "MK_USB = 13,", "MK_USB = 12,", None),
    ("patch-band-poll-dropped", P, r"{\n\t\tnat047_poll();\n\t\tuint32_t v", r"{\n\t\tuint32_t v", None),
    ("patch-wait-loop-poll-dropped", P, "while (mk_cnt() - s < t) { nat044_tick(); nat047_poll(); }", "while (mk_cnt() - s < t) { nat044_tick(); }", None),
    ("patch-wait-host-form-poll-dropped", P, r"nat044_tick();\n\tnat047_poll();\n#endif", r"nat044_tick();\n#endif",
     "the #else form of mk_wait_tenths is the MK_HOST build (no clock); the aarch64 loader compiles the loop form; the Patch tests count all three polls"),
    ("patch-stage-hook-dropped", P, r'{\n\tnat047_stage(stage);\n"', r'{\n"', None),
    ("patch-hold-hook-dropped", P, r"\tnat047_hold(stage, code);\n\tfor (;;)", r"\tfor (;;)", None),
    ("patch-hold-show-dropped", P, r'\t\tnat044_show(&prev, &ld_k);\n\t\tnat047_show(&prev, &ld_k);\n"', r'\t\tnat044_show(&prev, &ld_k);\n"', None),
    ("patch-exception-record-dropped", P, r"\tnat047_fault(slot, esr, elr, far);\n\tmk_draw", r"\tmk_draw", None),
    ("patch-exception-show-dropped", P, r"\t\tnat047_show(&prev, &k);\n\t}\n}\n\n/* Static", r"\t}\n}\n\n/* Static", None),
    ("patch-log-char-hook-dropped", P, r"{\n\tnat047_log_char(c);\n\tuint32_t pos", r"{\n\tuint32_t pos", None),
    ("patch-bringup-dropped", P, r'\tnat047_bringup((const char *)loader_log.text, loader_log.length);\n"', r'"', None),
    ("patch-bringup-log-length", P, "loader_log.text, loader_log.length);", "loader_log.text, 0);", None),
    # --- the build
    ("build-margin-removed", B, "MIN_MARGIN_S = 20 ", "MIN_MARGIN_S = 0 ", None),
    ("build-accepts-zero-deadline", B, "if not 0 < deadline_s <= wdt", "if not 0 <= deadline_s <= wdt", None),
    ("build-fault-flags-swapped", B, 'IMAGES = {"loader-diag-usbmon": 0, "loader-diag-usbmon-fault": 1}', 'IMAGES = {"loader-diag-usbmon": 1, "loader-diag-usbmon-fault": 0}', None),
    ("build-tag-not-the-image-name", B, "f'-DNAT047_TAG=\"{name}\"'", "'-DNAT047_TAG=\"image\"'", None),
    ("build-deadline-define-fixed", B, 'f"-DNAT044_DEADLINE_S={deadline_s}"', '"-DNAT044_DEADLINE_S=45"', None),
    ("build-ladder-without-writing-rungs", B, '(LADDER / "ladder.c", ["-DLAD_WRITING_RUNGS"], [LADDER, ENGINE], True)', '(LADDER / "ladder.c", [], [LADDER, ENGINE], True)', None),
    ("build-engine-without-werror", B, "(ENGINE / \"usbmon.c\", [], [ENGINE], True)", "(ENGINE / \"usbmon.c\", [], [ENGINE], False)", None),
    ("build-reset-module-without-werror", B, "(e / \"s5e9945_reset.c\", [], [e], True)", "(e / \"s5e9945_reset.c\", [], [e], False)", None),
    ("build-record-drops-engine-hashes", B, '"nat041_engine": {f: sha(ENGINE / f) for f in ENGINE_FILES}', '"nat041_engine": {}', None),
    # --- the packager (a call of NAT-044's, which carries its own mutants)
    ("package-does-not-run", PK, "    return m.main(argv)\n", "    return 0\n", None),
    ("package-argv-dropped", PK, "    return m.main(argv)\n", "    return m.main([])\n", None),
    # --- the decoder
    ("decoder-connected-configured-swapped", D, '0x0002: "connected", 0x0004: "configured"', '0x0002: "configured", 0x0004: "connected"', None),
    ("decoder-nrec-idx", D, "I_STATUS, I_ERR, I_ERROP, I_NREC, I_WRITTEN = 0, 1, 2, 3, 5", "I_STATUS, I_ERR, I_ERROP, I_NREC, I_WRITTEN = 0, 1, 2, 4, 5", None),
    ("decoder-phase-name", D, '4: "connect-wait"', '4: "connecting"', None),
    ("decoder-stop-code-radix", D, "return (raw // 16, LAD_ERR_NAMES.get(raw % 16,", "return (raw // 8, LAD_ERR_NAMES.get(raw % 8,", None),
    ("decoder-no-op-sentinel", D, "None if last[I_ERROP] == 0xFFFF else", "None if last[I_ERROP] == 0xFFFE else", None),
    ("decoder-first-frame-wins", D, 'last[f["idx"]] = f["data"]', 'last.setdefault(f["idx"], f["data"])', None),
]

TREES = ("nat-016", "nat-022", "nat-040", "nat-041", "nat-042", "nat-044", "nat-045", "nat-047")


def make_tree(dst, mutated=None):
    """docs/procedures/{nat-016,022,040,041,042,044,045,047} copied, artifacts linked to the real ones (read-only inputs)."""
    base = Path(dst) / "docs" / "procedures"
    base.mkdir(parents=True)
    for n in TREES:
        ign = ["__pycache__", "mutation*", "summary.json"] + (["evidence.json"] if n == "nat-047" else [])
        shutil.copytree(ROOT / "docs/procedures" / n, base / n, ignore=shutil.ignore_patterns(*ign))
    os.symlink(ROOT / "artifacts", Path(dst) / "artifacts")
    for extra in ("tools", "devices"):                       # read-only inputs of the NAT-022 packager (NAT-006 builder, pinned stock RECOVERY)
        if (ROOT / extra).exists():
            os.symlink(ROOT / extra, Path(dst) / extra)
    if mutated:
        f = base / "nat-047" / mutated[0]
        f.write_text(f.read_text().replace(mutated[1], mutated[2]))
    return Path(dst)


def builds(tree):
    r = subprocess.run([sys.executable, "-I", str(tree / "docs/procedures/nat-047/build.py"), "--check-only", "--loader-source",
                        str(ROOT / "artifacts/nat-020/build-003/source")], capture_output=True, text=True)
    return r.returncode == 0, (r.stderr or r.stdout)[-300:]


def run_tests(tree, timeout):
    try:
        r = subprocess.run([sys.executable, "-I", str(tree / "docs/procedures/nat-047/test_nat047.py")], capture_output=True, text=True,
                           timeout=timeout, cwd=tree)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    return r.returncode, r.stderr[-500:]


def one(i, mutant, tmp, timeout):
    name, rel, old, new, why = mutant
    src = (HERE / rel).read_text()
    n = src.count(old)
    if n != 1:
        return dict(name=name, status="ANCHOR", detail="anchor occurs %d times in %s" % (n, rel))
    tree = make_tree(Path(tmp) / ("m%03d" % i), (rel, old, new))
    try:
        # the mutants of the decoder and of the build script do not have to build images; every other one must
        if rel not in (D, B, PK):
            ok, why_not = builds(tree)
            if not ok:
                return dict(name=name, status="INVALID", detail=why_not)
        rc, tail = run_tests(tree, timeout)
        if rc != 0:
            return dict(name=name, status="killed", exit=rc, detail="")
        if why:
            return dict(name=name, status="equivalent", detail=why)
        return dict(name=name, status="SURVIVED", detail="tests passed")
    finally:
        shutil.rmtree(tree, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--only", help="comma-separated mutant names (a re-run of survivors)")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    todo = [m for m in MUTANTS if not a.only or m[0] in a.only.split(",")]
    with tempfile.TemporaryDirectory(prefix="nat047-mut-") as tmp:
        base = make_tree(Path(tmp) / "base")
        rc, tail = run_tests(base, a.timeout)
        if rc != 0:
            print("baseline fails; refusing to judge mutants:\n" + str(tail))
            return 2
        results = []
        with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
            futs = [ex.submit(one, i, m, tmp, a.timeout) for i, m in enumerate(todo)]
            for f in futs:
                r = f.result()
                results.append(r)
                print("%-46s %s %s" % (r["name"], r["status"], r.get("detail", "")[:100]), flush=True)
    count = lambda s: sum(1 for r in results if r["status"] == s)      # noqa: E731
    summary = dict(total=len(todo), killed=count("killed"), equivalent=count("equivalent"), survived=count("SURVIVED"), invalid=count("INVALID"),
                   anchor_errors=count("ANCHOR"), interpreter_has_unicorn_and_capstone=_has_sim(), results=results)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print("killed %d, documented equivalent %d, survived %d, invalid %d, anchor errors %d of %d" %
          (summary["killed"], summary["equivalent"], summary["survived"], summary["invalid"], summary["anchor_errors"], len(todo)))
    return 0 if summary["survived"] + summary["invalid"] + summary["anchor_errors"] == 0 else 1


def _has_sim():
    try:
        import unicorn, capstone  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.exit(main())
