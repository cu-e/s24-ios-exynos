#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Mutation check for NAT-045: break one thing at a time in a scratch copy of docs/procedures/nat-045 and require test_nat045.py
to fail. Host-only; it writes under --out and under the system temp directory and nowhere else.

    capvenv/bin/python -I docs/procedures/nat-045/mutate_nat045.py --out artifacts/nat-045/mutation-001 [--jobs 8]

Four families of mutants:
  c        a line of src/ladder.c, src/ladder_usb.c or src/ladder.h (the interpreter and the L6-L8 glue)
  table    one field of one row of the generated src/ladder_regs.h (address, value, mask, delay, flag, order of two rows, rung start,
           constants). The generated table is edited directly and the tests that only say "the header equals what derive.py writes"
           (derive --check, header/json agreement) are skipped for these: what is measured is whether the anchors, the ladder's
           behaviour and the self-check notice a wrong table without the generator's help.
  derive   a line of derive.py: the generator is run (`derive.py --write`) in the scratch copy and the tests run on what it wrote.
           A mutant the generator itself rejects (its vendor cross-checks, exit status 2) is killed by the generator.
  harness  none: the baseline must pass.

A mutant is `killed` when the suite fails (a crash or a timeout of the suite counts), `INVALID` when it no longer builds (compiler
warnings are errors) or the generator crashes with anything but its own error: INVALID is not a kill and is reported. A mutant
that is not killed makes the exit status non-zero unless it is listed with a reason in EQUIVALENT (the reason is printed).

Run it with an interpreter that has unicorn and capstone, and zig on PATH: several mutants (the delay, the counter, the bare-metal
build of the default image) are visible only to the aarch64 layer; a baseline that skipped it is refused.
"""
import argparse
import concurrent.futures
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

SKIP_FOR_TABLE = ("test_derive_check_passes_against_the_vendor_sources_and_the_plan",
                  "test_the_header_the_json_and_the_compiler_agree_on_the_table")

# --------------------------------------------------------------------------------------------------------------------------
# c mutants: (name, file relative to nat-045, old, new). `old` must occur exactly once. EQUIVALENT names the ones that cannot be
# told apart from the original by any behaviour of the program, with the reason.
C = [
    # ---- default stop / default configuration
    ("default-stop-writing-build-lowered", "src/ladder.c", "#define LAD_DEFAULT_STOP\tLAD_LAST_RUNG", "#define LAD_DEFAULT_STOP\t4"),
    ("default-stop-default-build-raised", "src/ladder.c", "#define LAD_DEFAULT_STOP\t2\n", "#define LAD_DEFAULT_STOP\t3\n"),
    ("default-poweron-off", "src/ladder.c", "c->allow_pd_poweron = 1;", "c->allow_pd_poweron = 0;"),
    ("default-pd-wait-nonzero", "src/ladder.c", "c->pd_wait_us = 0;", "c->pd_wait_us = 1;"),
    # ---- L0 self-check
    ("selfcheck-rung1-start-unchecked", "src/ladder.c", "lad_rung_start[1] != 0 || lad_rung_start[6] != LAD_NOPS", "lad_rung_start[6] != LAD_NOPS"),
    ("selfcheck-table-end-unchecked", "src/ladder.c", "lad_rung_start[1] != 0 || lad_rung_start[6] != LAD_NOPS", "lad_rung_start[1] != 0"),
    ("selfcheck-monotonic-unchecked", "src/ladder.c", "\t\tif (lad_rung_start[r] > lad_rung_start[r + 1])\n\t\t\treturn LAD_ERR(0, LAD_E_CFG);\n", ""),
    ("selfcheck-membership-unchecked", "src/ladder.c", "\t\t\tif (lad_ops[i].rung != r)\n\t\t\t\treturn LAD_ERR(0, LAD_E_CFG);\n", ""),
    ("selfcheck-l4-may-write", "src/ladder.c", "(r == 1 || r == 2 || r == 4)", "(r == 1 || r == 2)"),
    ("selfcheck-l1-may-write", "src/ladder.c", "(r == 1 || r == 2 || r == 4)", "(r == 2 || r == 4)"),
    ("selfcheck-l2-may-write", "src/ladder.c", "(r == 1 || r == 2 || r == 4)", "(r == 1 || r == 4)"),
    ("selfcheck-last-rung-unchecked", "src/ladder.c", "for (r = 1; r <= 5; r++) {", "for (r = 1; r <= 4; r++) {"),
    ("selfcheck-read-only-test-inverted", "src/ladder.c", "lad_ops[i].kind != LK_RD", "lad_ops[i].kind == LK_RD"),
    # ---- reads
    ("read-record-dropped", "src/ladder.c", "\tlad_rec_add(st, i, v, 0);\n\tif ((op->flags & LAD_F_NOTALIVE)", "\t(void)lad_rec_add;\n\tif ((op->flags & LAD_F_NOTALIVE)"),
    ("notalive-needs-both-words", "src/ladder.c", "(v == op->val || v == op->val2)", "(v == op->val && v == op->val2)"),
    ("notalive-second-word-ignored", "src/ladder.c", "(v == op->val || v == op->val2)", "(v == op->val)"),
    ("notalive-first-word-ignored", "src/ladder.c", "(v == op->val || v == op->val2)", "(v == op->val2)"),
    ("notalive-flag-ignored", "src/ladder.c", "if ((op->flags & LAD_F_NOTALIVE) && ", "if ("),
    ("notalive-wrong-code", "src/ladder.c", "return lad_fail(st, op->rung, LAD_E_NOTALIVE, i);\n\tif (op->flags & LAD_F_DWC3ID)", "return lad_fail(st, op->rung, LAD_E_STATE, i);\n\tif (op->flags & LAD_F_DWC3ID)"),
    ("dwc3-id-accepts-anything-else", "src/ladder.c", "id != LAD_DWC3_ID_0 && id != LAD_DWC3_ID_1", "id != LAD_DWC3_ID_0 || id != LAD_DWC3_ID_1"),
    ("dwc3-id-second-ignored", "src/ladder.c", "id != LAD_DWC3_ID_0 && id != LAD_DWC3_ID_1", "id != LAD_DWC3_ID_0"),
    ("dwc3-id-first-ignored", "src/ladder.c", "id != LAD_DWC3_ID_0 && id != LAD_DWC3_ID_1", "id != LAD_DWC3_ID_1"),
    ("dwc3-id-from-the-whole-word", "src/ladder.c", "uint32_t id = v & LAD_DWC3_ID_MASK;", "uint32_t id = v;"),
    ("dwc3-id-narrow-mask", "src/ladder.c", "uint32_t id = v & LAD_DWC3_ID_MASK;", "uint32_t id = v & (LAD_DWC3_ID_MASK << 1);"),
    ("dwc3-id-wrong-code", "src/ladder.c", "return lad_fail(st, op->rung, LAD_E_NOTALIVE, i);\n\t\tst->gsnpsid = v;", "return lad_fail(st, op->rung, LAD_E_CFG, i);\n\t\tst->gsnpsid = v;"),
    ("gsnpsid-not-stored", "src/ladder.c", "\t\tst->gsnpsid = v;\n", ""),
    ("gsnpsid-id-half-stored", "src/ladder.c", "st->gsnpsid = v;", "st->gsnpsid = id;"),
    # ---- the L1 result
    ("pd-wait-op-first-power-on-op", "src/ladder.c", "lad_ops[i].kind == LK_WAIT && (lad_ops[i].flags & LAD_F_POWERON)", "lad_ops[i].kind == LK_WAIT || (lad_ops[i].flags & LAD_F_POWERON)"),
    ("l1-result-from-any-l1-read", "src/ladder.c", "if (w < LAD_NOPS && op->addr == lad_ops[w].addr)", "if (w < LAD_NOPS)"),
    ("l1-result-inverted", "src/ladder.c", "(st->rec[st->nrec - 1].v0 & lad_ops[w].mask) == lad_ops[w].val", "(st->rec[st->nrec - 1].v0 & lad_ops[w].mask) != lad_ops[w].val"),
    ("l1-result-unmasked", "src/ladder.c", "(st->rec[st->nrec - 1].v0 & lad_ops[w].mask) == lad_ops[w].val", "st->rec[st->nrec - 1].v0 == lad_ops[w].val"),
    ("l1-result-taken-in-l2", "src/ladder.c", "\t\t\tif (r == 1) {", "\t\t\tif (r == 2) {"),
    # ---- writes: plain
    ("wrp-readback-unchecked", "src/ladder.c", "\t\tif (rb != op->val)\n\t\t\treturn lad_fail(st, op->rung, LAD_E_READBACK, i);\n\t\treturn LAD_OK;\n\tcase LK_WRM:", "\t\treturn LAD_OK;\n\tcase LK_WRM:"),
    ("wrp-readback-inverted", "src/ladder.c", "if (rb != op->val)", "if (rb == op->val)"),
    ("wrp-record-dropped", "src/ladder.c", "lad_rec_add(st, i, op->val, rb);", "(void)rb;"),
    ("wrp-writes-zero", "src/ladder.c", "usbmon_wr32(op->addr, op->val);\n\t\trb = usbmon_rd32(op->addr);\n\t\tlad_rec_add(st, i, op->val, rb);", "usbmon_wr32(op->addr, 0);\n\t\trb = usbmon_rd32(op->addr);\n\t\tlad_rec_add(st, i, op->val, rb);"),
    ("wrp-readback-wrong-code", "src/ladder.c", "if (rb != op->val)\n\t\t\treturn lad_fail(st, op->rung, LAD_E_READBACK, i);", "if (rb != op->val)\n\t\t\treturn lad_fail(st, op->rung, LAD_E_TIMEOUT, i);"),
    # ---- writes: read-modify-write
    ("wrm-keeps-the-bits-of-the-mask", "src/ladder.c", "want = (v & ~op->mask) | (op->val & op->mask);", "want = (v & op->mask) | (op->val & op->mask);"),
    ("wrm-value-unmasked", "src/ladder.c", "want = (v & ~op->mask) | (op->val & op->mask);", "want = (v & ~op->mask) | op->val;"),
    ("wrm-readback-whole-word", "src/ladder.c", "if ((rb ^ want) & op->mask)", "if (rb ^ want)"),
    ("wrm-readback-outside-the-mask", "src/ladder.c", "if ((rb ^ want) & op->mask)", "if ((rb ^ want) & ~op->mask)"),
    ("wrm-readback-unchecked", "src/ladder.c", "\t\tif ((rb ^ want) & op->mask)\n\t\t\treturn lad_fail(st, op->rung, LAD_E_READBACK, i);\n", ""),
    ("wrm-record-dropped", "src/ladder.c", "\t\tlad_rec_add(st, i, v, rb);\n", ""),
    ("wrm-record-wants", "src/ladder.c", "lad_rec_add(st, i, v, rb);", "lad_rec_add(st, i, want, rb);"),
    # ---- the bounded wait
    ("wait-bound-ignores-cfg", "src/ladder.c", "uint32_t limit = cfg->pd_wait_us ? cfg->pd_wait_us : LAD_WAIT_TIMEOUT_US;", "uint32_t limit = LAD_WAIT_TIMEOUT_US;\n\t\t(void)cfg;"),
    ("wait-bound-only-cfg", "src/ladder.c", "uint32_t limit = cfg->pd_wait_us ? cfg->pd_wait_us : LAD_WAIT_TIMEOUT_US;", "uint32_t limit = cfg->pd_wait_us;"),
    ("wait-bound-one-short", "src/ladder.c", "if (t > limit) {", "if (t >= limit) {"),
    ("wait-bound-one-long", "src/ladder.c", "if (t > limit) {", "if (t > limit + 1) {"),
    ("wait-poll-pause-doubled", "src/ladder.c", "t++;\n\t\t\tusbmon_delay_us(1);", "t++;\n\t\t\tusbmon_delay_us(2);"),
    ("wait-condition-inverted", "src/ladder.c", "if ((v & op->mask) == op->val)\n\t\t\t\tbreak;", "if ((v & op->mask) != op->val)\n\t\t\t\tbreak;"),
    ("wait-mask-ignored", "src/ladder.c", "if ((v & op->mask) == op->val)\n\t\t\t\tbreak;", "if (v == op->val)\n\t\t\t\tbreak;"),
    ("wait-timeout-record-dropped", "src/ladder.c", "\t\t\t\tlad_rec_add(st, i, v, t);\n\t\t\t\treturn lad_fail(st, op->rung, LAD_E_TIMEOUT, i);", "\t\t\t\treturn lad_fail(st, op->rung, LAD_E_TIMEOUT, i);"),
    ("wait-timeout-wrong-code", "src/ladder.c", "return lad_fail(st, op->rung, LAD_E_TIMEOUT, i);", "return lad_fail(st, op->rung, LAD_E_STATE, i);"),
    ("wait-success-record-without-time", "src/ladder.c", "\t\tlad_rec_add(st, i, v, t);\n\t\treturn LAD_OK;", "\t\tlad_rec_add(st, i, v, 0);\n\t\treturn LAD_OK;"),
    # ---- load / set / const / store
    ("load-chk-not-reset", "src/ladder.c", "\t\t*chk = 0;\n\t\tlad_rec_add(st, i, *reg, 0);", "\t\tlad_rec_add(st, i, *reg, 0);"),
    ("load-record-without-value", "src/ladder.c", "lad_rec_add(st, i, *reg, 0);", "lad_rec_add(st, i, 0, 0);"),
    ("set-keeps-the-old-field-bits", "src/ladder.c", "*reg = (*reg & ~op->mask) | op->val;", "*reg = *reg | op->val;"),
    ("set-clears-by-value", "src/ladder.c", "*reg = (*reg & ~op->mask) | op->val;", "*reg = (*reg & ~op->val) | op->val;"),
    ("set-chk-replaced", "src/ladder.c", "*chk |= op->mask;", "*chk = op->mask;"),
    ("set-chk-not-accumulated", "src/ladder.c", "\t\t*chk |= op->mask;\n", ""),
    ("const-chk-empty", "src/ladder.c", "*chk = 0xffffffffu;", "*chk = 0;"),
    ("store-readback-whole-word", "src/ladder.c", "if ((rb ^ *reg) & *chk) {", "if (rb ^ *reg) {"),
    ("store-readback-unchecked", "src/ladder.c", "if ((rb ^ *reg) & *chk) {", "if (0) {"),
    ("store-readback-outside-chk", "src/ladder.c", "if ((rb ^ *reg) & *chk) {", "if ((rb ^ *reg) & ~*chk) {"),
    ("store-soft-never", "src/ladder.c", "if (op->flags & LAD_F_SOFT) {", "if (0) {"),
    ("store-soft-always", "src/ladder.c", "if (op->flags & LAD_F_SOFT) {", "if (1) {"),
    ("store-soft-counted-twice", "src/ladder.c", "st->soft_mismatch++;", "st->soft_mismatch += 2;"),
    ("store-soft-not-counted", "src/ladder.c", "\t\t\t\tst->soft_mismatch++;\n", ""),
    ("store-record-dropped", "src/ladder.c", "\t\tlad_rec_add(st, i, *reg, rb);\n", ""),
    ("store-writes-the-chk", "src/ladder.c", "usbmon_wr32(op->addr, *reg);\n\t\trb = usbmon_rd32(op->addr);\n\t\tlad_rec_add(st, i, *reg, rb);", "usbmon_wr32(op->addr, *reg & *chk);\n\t\trb = usbmon_rd32(op->addr);\n\t\tlad_rec_add(st, i, *reg, rb);"),
    ("rdlog-record-dropped", "src/ladder.c", "lad_rec_add(st, i, usbmon_rd32(op->addr), 0);", "(void)usbmon_rd32(op->addr);"),
    ("rdlog-does-not-read", "src/ladder.c", "lad_rec_add(st, i, usbmon_rd32(op->addr), 0);", "lad_rec_add(st, i, 0, 0);"),
    ("delay-one-long", "src/ladder.c", "usbmon_delay_us(op->val);", "usbmon_delay_us(op->val + 1);"),
    ("delay-dropped", "src/ladder.c", "\t\tusbmon_delay_us(op->val);\n", ""),
    ("unknown-op-kind-passes", "src/ladder.c", "default:\n\t\treturn lad_fail(st, op->rung, LAD_E_CFG, i);\n\t}", "default:\n\t\treturn LAD_OK;\n\t}"),
    # ---- the rung loop
    ("default-build-gate-one-rung-late", "src/ladder.c", "\tif (r >= 3)\n\t\treturn lad_fail(st, r, LAD_E_DISABLED, LAD_NOPS);", "\tif (r >= 4)\n\t\treturn lad_fail(st, r, LAD_E_DISABLED, LAD_NOPS);"),
    ("default-build-disabled-op-index", "src/ladder.c", "LAD_E_DISABLED, LAD_NOPS", "LAD_E_DISABLED, 0"),
    ("default-build-disabled-code", "src/ladder.c", "LAD_E_DISABLED", "LAD_E_CFG"),
    ("default-build-write-op-in-a-read-rung-passes", "src/ladder.c", "return lad_fail(st, r, LAD_E_CFG, i);\t/* a write op in a rung that is not supposed to write */", "continue;"),
    ("l3-policy-on-the-wrong-rung", "src/ladder.c", "\t\tif (r == 3) {", "\t\tif (r == 4) {"),
    ("l3-unknown-domain-state-allowed", "src/ladder.c", "\t\t\tif (st->pd_was_on > 1)\n\t\t\t\treturn lad_fail(st, r, LAD_E_STATE, i);\n", ""),
    ("l3-power-on-ops-not-recognised", "src/ladder.c", "if (op->flags & (LAD_F_POWERON | LAD_F_CMUINIT)) {", "if (op->flags & LAD_F_CMUINIT) {"),
    ("l3-cmu-init-ops-not-recognised", "src/ladder.c", "if (op->flags & (LAD_F_POWERON | LAD_F_CMUINIT)) {", "if (op->flags & LAD_F_POWERON) {"),
    ("l3-skip-when-the-domain-is-off", "src/ladder.c", "if (st->pd_was_on)\n\t\t\t\t\tcontinue;", "if (!st->pd_was_on)\n\t\t\t\t\tcontinue;"),
    ("l3-power-on-permission-ignored", "src/ladder.c", "\t\t\t\tif (!cfg->allow_pd_poweron)\n\t\t\t\t\treturn lad_fail(st, r, LAD_E_STATE, i);\n", ""),
    ("l3-power-on-permission-inverted", "src/ladder.c", "if (!cfg->allow_pd_poweron)", "if (cfg->allow_pd_poweron)"),
    ("l3-power-on-refusal-wrong-code", "src/ladder.c", "if (!cfg->allow_pd_poweron)\n\t\t\t\t\treturn lad_fail(st, r, LAD_E_STATE, i);", "if (!cfg->allow_pd_poweron)\n\t\t\t\t\treturn lad_fail(st, r, LAD_E_CFG, i);"),
    ("write-failure-ignored", "src/ladder.c", "rc = lad_exec_write(st, cfg, i, &reg, &chk);\n\t\tif (rc)\n\t\t\treturn rc;", "rc = lad_exec_write(st, cfg, i, &reg, &chk);\n\t\t(void)rc;"),
    ("read-failure-ignored", "src/ladder.c", "rc = lad_exec_read(st, i);\n\t\t\tif (rc)\n\t\t\t\treturn rc;", "rc = lad_exec_read(st, i);\n\t\t\t(void)rc;"),
    ("rung-ends-one-op-early", "src/ladder.c", "end = lad_rung_start[r + 1];", "end = lad_rung_start[r + 1] - 1;"),
    # ---- lad_run
    ("run-state-last-byte-not-cleared", "src/ladder.c", "for (n = 0; n < sizeof(*st); n++)", "for (n = 0; n < sizeof(*st) - 1; n++)"),
    ("run-state-not-cleared", "src/ladder.c", "for (n = 0; n < sizeof(*st); n++)", "for (n = 0; n < 1; n++)"),
    ("run-l1-result-initially-off", "src/ladder.c", "st->pd_was_on = 0xff;", "st->pd_was_on = 0;"),
    ("run-failed-op-initially-zero", "src/ladder.c", "st->err_op = LAD_NOPS;", "st->err_op = 0;"),
    ("run-null-cfg-accepted", "src/ladder.c", "if (!cfg || cfg->stop_after > LAD_LAST_RUNG)", "if (cfg->stop_after > LAD_LAST_RUNG)"),
    ("run-last-rung-refused", "src/ladder.c", "cfg->stop_after > LAD_LAST_RUNG", "cfg->stop_after >= LAD_LAST_RUNG"),
    ("run-rung-past-the-last-accepted", "src/ladder.c", "cfg->stop_after > LAD_LAST_RUNG", "cfg->stop_after > LAD_LAST_RUNG + 1"),
    ("run-selfcheck-skipped", "src/ladder.c", "rc = lad_selfcheck();\n\tif (rc)\n\t\treturn lad_fail(st, 0, LAD_E_CFG, LAD_NOPS);", "rc = 0;"),
    ("run-selfcheck-failure-has-an-op", "src/ladder.c", "\tif (rc)\n\t\treturn lad_fail(st, 0, LAD_E_CFG, LAD_NOPS);\n\tfor (r", "\tif (rc)\n\t\treturn lad_fail(st, 0, LAD_E_CFG, 0);\n\tfor (r"),
    ("run-starts-at-rung-2", "src/ladder.c", "for (r = 1; r <= cfg->stop_after; r++) {", "for (r = 2; r <= cfg->stop_after; r++) {"),
    ("run-stops-one-rung-early", "src/ladder.c", "for (r = 1; r <= cfg->stop_after; r++) {", "for (r = 1; r < cfg->stop_after; r++) {"),
    ("run-rung-done-before-the-rung", "src/ladder.c", "\t\trc = lad_rung(st, cfg, r);\n\t\tif (rc)\n\t\t\treturn rc;\n\t\tst->rung_done = (uint8_t)r;", "\t\tst->rung_done = (uint8_t)r;\n\t\trc = lad_rung(st, cfg, r);\n\t\tif (rc)\n\t\t\treturn rc;"),
    ("run-rung-done-off-by-one", "src/ladder.c", "st->rung_done = (uint8_t)r;", "st->rung_done = (uint8_t)(r - 1);"),
    ("run-rung-failure-ignored", "src/ladder.c", "\t\trc = lad_rung(st, cfg, r);\n\t\tif (rc)\n\t\t\treturn rc;", "\t\trc = lad_rung(st, cfg, r);\n\t\t(void)rc;"),
    # ---- failure and record bookkeeping
    ("fail-code-composed-backwards", "src/ladder.c", "st->err = (int16_t)LAD_ERR(rung, code);", "st->err = (int16_t)LAD_ERR(code, rung);"),
    ("fail-op-not-recorded", "src/ladder.c", "\tst->err_op = (uint16_t)op;\n", "\t(void)op;\n"),
    ("rec-op-shifted", "src/ladder.c", "r->op = (uint16_t)op;", "r->op = (uint16_t)(op + 1);"),
    ("rec-values-swapped", "src/ladder.c", "r->v0 = v0;\n\tr->v1 = v1;", "r->v0 = v1;\n\tr->v1 = v0;"),
    ("rec-count-not-advanced", "src/ladder.c", "&st->rec[st->nrec++]", "&st->rec[st->nrec]"),
    # ---- the header
    ("hdr-error-codes-composed-with-15", "src/ladder.h", "(-((int)(rung) * 16 + (int)(code)))", "(-((int)(rung) * 15 + (int)(code)))"),
    ("hdr-last-rung", "src/ladder.h", "#define LAD_LAST_RUNG\t\t5", "#define LAD_LAST_RUNG\t\t4"),
    ("hdr-code-readback", "src/ladder.h", "#define LAD_E_READBACK\t1", "#define LAD_E_READBACK\t7"),
    ("hdr-code-notalive", "src/ladder.h", "#define LAD_E_NOTALIVE\t4", "#define LAD_E_NOTALIVE\t8"),
    ("hdr-usb-rung-connect", "src/ladder.h", "#define LAD_USB_RUNG_CONNECT\t7", "#define LAD_USB_RUNG_CONNECT\t6"),
    ("hdr-state-field-order", "src/ladder.h", "\tuint8_t rung_done;\t\t/* highest rung that completed */\n\tuint8_t pd_was_on;", "\tuint8_t pd_was_on;\t\t/* highest rung that completed */\n\tuint8_t rung_done;"),
    # ---- ladder_usb.c
    ("usb-id-code", "src/ladder_usb.c", "e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_NOTALIVE);", "e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_TIMEOUT);"),
    ("usb-reset-and-halt-code", "src/ladder_usb.c", "case USBMON_E_HALT:\n\t\te = LAD_ERR(LAD_USB_RUNG_START, LAD_E_TIMEOUT);", "case USBMON_E_HALT:\n\t\te = LAD_ERR(LAD_USB_RUNG_START, LAD_E_READBACK);"),
    ("usb-halt-is-a-cfg-error", "src/ladder_usb.c", "case USBMON_E_RESET:\n\tcase USBMON_E_HALT:", "case USBMON_E_RESET:"),
    ("usb-reset-is-a-cfg-error", "src/ladder_usb.c", "case USBMON_E_RESET:\n\tcase USBMON_E_HALT:", "case USBMON_E_HALT:"),
    ("usb-cmd-code", "src/ladder_usb.c", "e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_READBACK);", "e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_TIMEOUT);"),
    ("usb-other-failure-code", "src/ladder_usb.c", "e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_CFG);", "e = LAD_ERR(LAD_USB_RUNG_START, LAD_E_STATE);"),
    ("usb-error-not-stored", "src/ladder_usb.c", "\tif (err)\n\t\t*err = e;\n", "\t(void)err;\n"),
    ("usb-start-returns-ok", "src/ladder_usb.c", "\treturn e;\n}\n\nint lad_usb_wait", "\treturn 0;\n}\n\nint lad_usb_wait"),
    ("usb-wait-rung-check-or", "src/ladder_usb.c", "rung != LAD_USB_RUNG_CONNECT && rung != LAD_USB_RUNG_HOST", "rung != LAD_USB_RUNG_CONNECT || rung != LAD_USB_RUNG_HOST"),
    ("usb-wait-connect-only", "src/ladder_usb.c", "rung != LAD_USB_RUNG_CONNECT && rung != LAD_USB_RUNG_HOST", "rung != LAD_USB_RUNG_CONNECT"),
    ("usb-wait-host-only", "src/ladder_usb.c", "rung != LAD_USB_RUNG_CONNECT && rung != LAD_USB_RUNG_HOST", "rung != LAD_USB_RUNG_HOST"),
    ("usb-wait-rung-unchecked", "src/ladder_usb.c", "\tif (rung != LAD_USB_RUNG_CONNECT && rung != LAD_USB_RUNG_HOST)\n\t\treturn LAD_ERR(rung, LAD_E_CFG);\n", ""),
    ("usb-wait-one-poll-too-many", "src/ladder_usb.c", "n < max_polls", "n <= max_polls"),
    ("usb-wait-one-poll-too-few", "src/ladder_usb.c", "n < max_polls", "n + 1 < max_polls"),
    ("usb-wait-engine-not-polled", "src/ladder_usb.c", "\t\tusbmon_poll(m);\n", ""),
    ("usb-wait-flags-equal", "src/ladder_usb.c", "if (m->flags & flag)", "if (m->flags == flag)"),
    ("usb-wait-any-flag", "src/ladder_usb.c", "if (m->flags & flag)", "if (m->flags && flag)"),
    ("usb-wait-pause-dropped", "src/ladder_usb.c", "usbmon_delay_us(poll_delay_us);", "(void)poll_delay_us;"),
    ("usb-wait-pause-forced", "src/ladder_usb.c", "if (poll_delay_us)\n\t\t\tusbmon_delay_us(poll_delay_us);", "usbmon_delay_us(poll_delay_us ? poll_delay_us : 1);"),
    ("usb-wait-timeout-code", "src/ladder_usb.c", "return LAD_ERR(rung, LAD_E_TIMEOUT);", "return LAD_ERR(rung, LAD_E_STATE);"),
    ("usb-wait-cfg-code", "src/ladder_usb.c", "return LAD_ERR(rung, LAD_E_CFG);", "return LAD_ERR(rung, LAD_E_STATE);"),
]

# Mutants that no behaviour of the program can tell from the original, with the reason. A listed mutant that survives is reported as
# `equivalent`; one that is killed anyway is reported as `killed` (the reason was too cautious).
EQUIVALENT = {
    "selfcheck-monotonic-unchecked": "every op index is covered by at least one rung range (rung 1 starts at 0, the last ends at the table end); a descent between two starts "
                                      "makes some op covered by two ranges of different rungs, and the membership check refuses that op; the monotonic check only reports "
                                      "the same stop earlier",
    "l1-result-from-any-l1-read": "L1 reads the config word first and the status word last, and the status read overwrites the result; the guard on the address only matters if "
                                   "the op order were reversed, which the L1 address anchor forbids",
    "wrm-value-unmasked": "every WRM row of the table has val inside mask (derive.py computes val = value & mask), so `val & mask` == `val`",
    "derive-poweron-value-unmasked": "every PMUCAL row the ladder uses has its value inside its mask on the pinned sources (checked by "
                                     "Table.test_every_masked_op_has_its_value_inside_its_mask), so `value & mask` == `value`",
    "derive-cmuinit-value-unmasked": "same as derive-poweron-value-unmasked for the hsi0_cmu_init rows",
    "default-build-write-op-in-a-read-rung-passes": "in the default build only rungs 1 and 2 run; lad_selfcheck() has already refused a table with a write op in them, so this "
                                                    "second line of defence is never reached",
}

# --------------------------------------------------------------------------------------------------------------------------
# derive mutants: (name, old, new) on derive.py; the generator is run on the mutated copy and the tests run on what it wrote.
DERIVE = [
    ("poweron-write-kind-inverted", 'add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],\n                val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=["0.20"]',
     'add(3, "WRP" if row["mask"] != 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],\n                val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=["0.20"]'),
    ("cmuinit-write-kind-inverted", 'add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],\n            val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=[], cmu_init=True)',
     'add(3, "WRP" if row["mask"] != 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],\n            val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=[], cmu_init=True)'),
    ("poweron-value-unmasked", 'val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=["0.20"]', 'val=row["value"], label=row["name"], source=row["text"], plan=["0.20"]'),
    ("cmuinit-value-unmasked", 'val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=[], cmu_init=True)', 'val=row["value"], label=row["name"], source=row["text"], plan=[], cmu_init=True)'),
    ("poweron-address-shifted", 'add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],\n                val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=["0.20"]',
     'add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"] + 4, mask=row["mask"],\n                val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=["0.20"]'),
    ("cmuinit-address-shifted", 'add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"], mask=row["mask"],\n            val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=[], cmu_init=True)',
     'add(3, "WRP" if row["mask"] == 0xFFFFFFFF else "WRM", addr=row["base"] + row["offset"] + 4, mask=row["mask"],\n            val=row["value"] & row["mask"], label=row["name"], source=row["text"], plan=[], cmu_init=True)'),
    ("wait-value-masked", 'add(3, "WAIT", addr=row["base"] + row["offset"], mask=row["mask"], val=row["value"],', 'add(3, "WAIT", addr=row["base"] + row["offset"], mask=row["mask"] | 0x2, val=row["value"],'),
    ("header-wait-timeout-constant", "L.append(f\"#define LAD_WAIT_TIMEOUT_US\\t{spec['pmucal_semantics']['wait_timeout_us']}u\")",
     "L.append(f\"#define LAD_WAIT_TIMEOUT_US\\t{int(spec['pmucal_semantics']['wait_timeout_us']) + 1}u\")"),
    ("isolation-value-inverted", 'val = 0 if iso["on_arg"] else bit', 'val = bit if iso["on_arg"] else 0'),
    ("isolation-bit-shifted", 'bit = 1 << iso["bit"]', 'bit = 1 << (iso["bit"] + 1)'),
    ("set-mask-one-bit-too-wide", "mask = ((1 << w) - 1) << lsb", "mask = (1 << w) << lsb"),
    ("set-mask-one-bit-too-narrow", "mask = ((1 << w) - 1) << lsb", "mask = ((1 << (w - 1)) - 1) << lsb"),
    ("set-value-not-shifted", '"val": v << lsb', '"val": v'),
    ("set-field-lsb-and-width-swapped", "lsb, w = lay[m.group(2)]", "w, lsb = lay[m.group(2)]"),
    ("merged-sets-or-their-values", 'p["val"] = (p["val"] & ~o["mask"]) | o["val"]', 'p["val"] = p["val"] | o["val"]'),
    ("merged-sets-take-the-last-mask", 'p["mask"] |= o["mask"]', 'p["mask"] = o["mask"]'),
    ("delay-variable-off-by-one", "us = vars_[a] if a in vars_ else cint(a)", "us = vars_[a] + 1 if a in vars_ else cint(a)"),
    ("delay-literal-off-by-one", "us = vars_[a] if a in vars_ else cint(a)", "us = vars_[a] if a in vars_ else cint(a) + 1"),
    ("delay-variable-assignment-off-by-one", 'vars_["value"] = int(m.group(1))', 'vars_["value"] = int(m.group(1)) + 1'),
    ("const-store-value-off-by-one", 'emit({"k": "CONST", "val": cint(m.group(1)), "text": s})', 'emit({"k": "CONST", "val": cint(m.group(1)) ^ 1, "text": s})'),
    ("dwc3-id-0-shift", 'consts["DWC3_ID_0"] = idh[idspec["accept"][0]] << 16', 'consts["DWC3_ID_0"] = idh[idspec["accept"][0]] << 15'),
    ("dwc3-id-1-shift", 'consts["DWC3_ID_1"] = idh[idspec["accept"][1]] << 16', 'consts["DWC3_ID_1"] = idh[idspec["accept"][1]] << 15'),
    ("dwc3-id-flag-not-set", '    ops[-1]["dwc3_id"] = True\n', "    pass\n"),
    ("sfr-address-shifted", 'addr, src = bases[b] + off, f"SFR({r[\'sfr\']}, 0x{off:x}, {b})"', 'addr, src = bases[b] + off + 4, f"SFR({r[\'sfr\']}, 0x{off:x}, {b})"'),
    ("define-address-shifted", 'addr, src = bases[r["base"]] + d, f"#define {r[\'define\'][1]} 0x{d:x}"', 'addr, src = bases[r["base"]] + d + 4, f"#define {r[\'define\'][1]} 0x{d:x}"'),
    ("header-address-shifted", 'addr, src = bases[r["base"]] + hdr[r["name"]], f"#define {r[\'name\']} 0x{hdr[r[\'name\']]:x}"', 'addr, src = bases[r["base"]] + hdr[r["name"]] + 4, f"#define {r[\'name\']} 0x{hdr[r[\'name\']]:x}"'),
    ("pre-read-address-shifted", 'a = bases[pr["base"]] + hdr[pr["name"]]', 'a = bases[pr["base"]] + hdr[pr["name"]] + 4'),
    ("not-alive-word-changed", "not_alive=[cint(x) for x in pr[\"not_alive\"]])", "not_alive=[cint(x) ^ 1 for x in pr[\"not_alive\"]])"),
    ("isolation-address-shifted", 'add(5, "WRM", addr=bases[iso["base"]] + consts[iso["offset_const"]], mask=bit', 'add(5, "WRM", addr=bases[iso["base"]] + consts[iso["offset_const"]] + 4, mask=bit'),
    ("flag-power-on-dropped", '        if o.get("poweron"):\n            fl.append("LAD_F_POWERON")', '        if False:\n            fl.append("LAD_F_POWERON")'),
    ("flag-not-alive-dropped", '        if o.get("not_alive"):\n            fl.append("LAD_F_NOTALIVE")', '        if False:\n            fl.append("LAD_F_NOTALIVE")'),
    ("flag-cmu-init-dropped", '        if o.get("cmu_init"):\n            fl.append("LAD_F_CMUINIT")', '        if False:\n            fl.append("LAD_F_CMUINIT")'),
    ("flag-dwc3-id-dropped", '        if o.get("dwc3_id"):\n            fl.append("LAD_F_DWC3ID")', '        if False:\n            fl.append("LAD_F_DWC3ID")'),
    ("flag-soft-on-every-store", 'if o.get("via") and o["k"] == "STORE":', 'if o["k"] == "STORE":'),
    ("flag-soft-dropped", 'if o.get("via") and o["k"] == "STORE":', "if False:"),
    ("l1-reads-reversed", 'for r in R["L1"]["reads"]:', 'for r in reversed(R["L1"]["reads"]):'),
    ("l2-reads-reversed", 'for r in R["L2"]["reads"]:', 'for r in reversed(R["L2"]["reads"]):'),
    ("l3-reads-reversed", 'for r in l3["reads"]:', 'for r in reversed(l3["reads"]):'),
    ("l5-parts-reversed", 'for part in l5["parts"]:', 'for part in reversed(l5["parts"]):'),
    ("l5-final-reads-reversed", 'for r in l5["final_reads"]:', 'for r in reversed(l5["final_reads"]):'),
    ("cmu-init-rows-reversed", 'for row in map(used, arrays[l3["cmu_init"]["pmucal_seq"]]):', 'for row in reversed(list(map(used, arrays[l3["cmu_init"]["pmucal_seq"]]))):'),
    ("cmu-init-omission-ignored", 'if row["name"] in omit:', "if False:"),
    ("cmu-init-omission-check-dropped", 'if seen_omit != set(omit):', "if False:"),
    ("plan-statement-check-dropped", "if txt not in fn_stmts[fn]:", "if False:"),
    ("plan-row-check-dropped", "if not hit:", "if False:"),
    ("plan-step-existence-check-dropped", "if sid not in steps:", "if False:"),
    ("conditional-row-check-dropped", 'if row["cond_base"] or row["cond_offset"]:', "if False:"),
    ("field-overflow-check-dropped", "if v >> w:", "if False:"),
    ("base-text-check-dropped", 'if b["text"] not in vendor(pin, files[b["file"]]):', "if False:"),
    ("isolation-verify-dropped", '    for v in iso["verify"]:\n        if v["text"] not in vendor(pin, files[v["file"]]):', '    for v in iso["verify"]:\n        if False:'),
    ("part-verify-dropped", '        for v in part.get("verify", []):\n            if v["text"] not in vendor(pin, files[v["file"]]):', '        for v in part.get("verify", []):\n            if False:'),
    ("inline-call-verify-dropped", '            for v in ic.get("verify", []):\n                if v["text"] not in vendor(pin, files[v["file"]]):', '            for v in ic.get("verify", []):\n                if False:'),
    ("constant-text-check-dropped", 'if c["text"] not in vendor(pin, files[c["file"]]):', "if False:"),
    ("base-value-check-dropped", 'if f"0x{bases[name]:08x}".lower() not in b["text"].lower().replace("0x0 0x", "0x"):', "if False:"),
    ("plan-read-row-satisfied-by-a-wait", '"PMUCAL_READ": ("RD",)', '"PMUCAL_READ": ("RD", "WAIT")'),
    ("plan-write-row-satisfied-by-a-read", '"PMUCAL_WRITE": ("WRP", "WRM")', '"PMUCAL_WRITE": ("WRP", "WRM", "RD")'),
    ("plan-wait-row-satisfied-by-a-read", '"PMUCAL_WAIT": ("WAIT",)', '"PMUCAL_WAIT": ("WAIT", "RD")'),
    ("plan-row-mask-not-compared", 'and o.get("mask", row["mask"]) == row["mask"]\n', "\n"),
    ("plan-row-value-not-compared", 'and (o["k"] == "RD" or o.get("val", row["value"]) == row["value"] & row["mask"])]', "]"),
    ("plan-row-unknown-type-accepted", 'if kinds is None:', "if False and kinds is None:"),
    ("id-mask-check-dropped", 'if consts["DWC3_ID_MASK"] != 0xFFFF0000:', "if False:"),
]


# --------------------------------------------------------------------------------------------------------------------------
# table mutants, generated from the header
ROW = re.compile(r"^(\t/\*\s*(\d+) L(\d) .*?\*/ )\{ LK_(\w+), (\d+), ([^,]+), (0x[0-9a-f]+)u, (0x[0-9a-f]+)u, (0x[0-9a-f]+)u, (0x[0-9a-f]+)u \},$")
ADDR_KINDS = {"RD", "WRP", "WRM", "WAIT", "LOAD", "STORE", "RDLOG"}


def parse_rows(text):
    rows = []
    for line in text.splitlines():
        m = ROW.match(line)
        if m:
            pre, i, lab, kind, rung, flags, addr, mask, val, val2 = m.groups()
            rows.append(dict(line=line, pre=pre, i=int(i), kind=kind, rung=int(rung), flags=flags.strip(), addr=int(addr, 16), mask=int(mask, 16),
                             val=int(val, 16), val2=int(val2, 16)))
    return rows


def fmt_row(r, **kw):
    d = dict(r, **kw)
    return "%s{ LK_%s, %d, %s, 0x%08xu, 0x%08xu, 0x%08xu, 0x%08xu }," % (d["pre"], d["kind"], d["rung"], d["flags"] or "0", d["addr"] & 0xFFFFFFFF,
                                                                         d["mask"] & 0xFFFFFFFF, d["val"] & 0xFFFFFFFF, d["val2"] & 0xFFFFFFFF)


def table_mutants(header_text):
    rows = parse_rows(header_text)
    out = []

    def add(name, old, new):
        out.append((name, "src/ladder_regs.h", old, new))
    for r in rows:
        n, k = r["i"], r["kind"]
        tag = "row%03d-%s" % (n, k.lower())
        if k in ADDR_KINDS:
            add(tag + "-address", r["line"], fmt_row(r, addr=r["addr"] ^ 0x4))
        if k in ("WRP", "CONST"):
            add(tag + "-value", r["line"], fmt_row(r, val=r["val"] ^ 1))
        if k in ("WRM", "WAIT", "SET"):
            low = r["mask"] & -r["mask"]
            add(tag + "-value", r["line"], fmt_row(r, val=r["val"] ^ low))
            b = next(b for b in range(32) if not (r["val"] >> b) & 1)
            add(tag + "-mask", r["line"], fmt_row(r, mask=r["mask"] ^ (1 << b)))
        if k == "DELAY":
            add(tag + "-delay", r["line"], fmt_row(r, val=r["val"] + 1))
        if k == "RD" and r["flags"] == "LAD_F_NOTALIVE":
            add(tag + "-notalive-word", r["line"], fmt_row(r, val=1))
            add(tag + "-notalive-word2", r["line"], fmt_row(r, val2=0xFFFFFFFE))
        for f in [x for x in r["flags"].split("|") if x != "0"]:
            rest = "|".join(x for x in r["flags"].split("|") if x != f) or "0"
            add(tag + "-no-" + f.lower(), r["line"], fmt_row(r, flags=rest))
        if k == "STORE" and r["flags"] == "0":
            add(tag + "-made-soft", r["line"], fmt_row(r, flags="LAD_F_SOFT"))
    for a, b in zip(rows, rows[1:]):
        if a["rung"] == b["rung"] and (a["kind"], a["addr"], a["mask"], a["val"], a["flags"]) != (b["kind"], b["addr"], b["mask"], b["val"], b["flags"]):
            add("swap-rows-%03d-%03d" % (a["i"], b["i"]), a["line"] + "\n" + b["line"],
                fmt_row(a, kind=b["kind"], flags=b["flags"], addr=b["addr"], mask=b["mask"], val=b["val"], val2=b["val2"]) + "\n" +
                fmt_row(b, kind=a["kind"], flags=a["flags"], addr=a["addr"], mask=a["mask"], val=a["val"], val2=a["val2"]))
    m = re.search(r"static const uint16_t lad_rung_start\[7\] = \{ ([0-9, ]+) \};", header_text)
    starts = [int(x) for x in m.group(1).split(",")]
    for idx in (2, 3, 4, 5):
        s = list(starts)
        s[idx] += 1
        add("rung-start-%d-plus-one" % idx, m.group(0), m.group(0).replace(m.group(1), ", ".join(map(str, s))))
    for name, old, new in (("dwc3-id-0", "#define LAD_DWC3_ID_0\t0x55330000u", "#define LAD_DWC3_ID_0\t0x55340000u"),
                           ("dwc3-id-1", "#define LAD_DWC3_ID_1\t0x33310000u", "#define LAD_DWC3_ID_1\t0x33320000u"),
                           ("dwc3-id-mask", "#define LAD_DWC3_ID_MASK\t0xffff0000u", "#define LAD_DWC3_ID_MASK\t0xff000000u"),
                           ("wait-timeout", "#define LAD_WAIT_TIMEOUT_US\t200000u", "#define LAD_WAIT_TIMEOUT_US\t199999u")):
        add("const-" + name, old, new)
    return out


# --------------------------------------------------------------------------------------------------------------------------
def make_tree(dst):
    base = Path(dst) / "docs" / "procedures"
    base.mkdir(parents=True)
    shutil.copytree(HERE, base / "nat-045", ignore=shutil.ignore_patterns("__pycache__", "evidence*.json", "mutation*", "README.md"))
    for n in ("nat-040", "nat-041"):
        os.symlink(ROOT / "docs" / "procedures" / n, base / n)
    os.symlink(ROOT / "references", Path(dst) / "references")
    return Path(dst)


def apply(tree, rel, old, new):
    f = tree / "docs" / "procedures" / "nat-045" / rel
    text = f.read_text()
    if text.count(old) != 1:
        return False
    f.write_text(text.replace(old, new))
    return True


def suite(tree, skip, timeout):
    """Run the scratch copy's test suite in a child process. -> (verdict, detail) verdict in ok / failed / invalid / crash / timeout"""
    cmd = [sys.executable, "-I", str(HERE / "mutate_nat045.py"), "--suite", str(tree / "docs/procedures/nat-045"), "--skip", ",".join(skip)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "timeout", ""
    try:
        res = json.loads(r.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return "crash", ("rc=%d %s" % (r.returncode, (r.stderr or r.stdout)[-200:])).strip()
    if "invalid" in res:
        return "invalid", res["invalid"]
    if res["failed"]:
        return "failed", res["failed"][0]
    return ("ok" if res["skipped"] == 0 else "ok-with-skips"), json.dumps(res)


def generate(tree):
    r = subprocess.run([sys.executable, "-I", str(tree / "docs/procedures/nat-045/derive.py"), "--write"], capture_output=True, text=True, cwd=tree)
    return r.returncode, (r.stderr or r.stdout)[-300:]


def one(i, mutant, family, tmp, timeout):
    name, rel, old, new = mutant
    tree = make_tree(Path(tmp) / ("m%03d" % i))
    t0 = time.time()
    try:
        if not apply(tree, rel, old, new):
            return dict(name=name, family=family, status="ANCHOR", detail="anchor is not unique in " + rel)
        skip = ()
        if family == "table":
            skip = SKIP_FOR_TABLE
        if family == "derive":
            rc, tail = generate(tree)
            if rc == 2:
                return dict(name=name, family=family, status="killed", by="derive.py (its own vendor/plan cross-check)", detail=tail.strip()[:160], secs=round(time.time() - t0, 1))
            if rc != 0:
                return dict(name=name, family=family, status="INVALID", detail="derive.py crashed: " + tail.strip()[-200:])
        verdict, detail = suite(tree, skip, timeout)
        if verdict == "invalid":
            return dict(name=name, family=family, status="INVALID", detail=detail)
        if verdict in ("failed", "crash", "timeout"):
            return dict(name=name, family=family, status="killed", by=verdict + (": " + detail if detail else ""), secs=round(time.time() - t0, 1))
        if verdict == "ok-with-skips":
            return dict(name=name, family=family, status="SURVIVED", detail="the suite skipped tests: " + detail[:120])
        return dict(name=name, family=family, status="SURVIVED", detail="the suite passed", secs=round(time.time() - t0, 1))
    finally:
        shutil.rmtree(tree, ignore_errors=True)


# --------------------------------------------------------------------------------------------------------------------------
def suite_main(d, skip):
    """Child mode: import the scratch copy's test module, build both libraries (a build failure is `invalid`), run the suite."""
    import importlib.util
    d = Path(d)
    spec = importlib.util.spec_from_file_location("t45", d / "test_nat045.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["t45"] = mod
    try:
        spec.loader.exec_module(mod)
        for w in (False, True):
            mod.lib(w)
    except Exception as e:                      # noqa: BLE001 - any failure to build or parse is an invalid mutant
        print(json.dumps({"invalid": ("%s: %s" % (type(e).__name__, e))[-300:]}))
        return 0
    cases = []

    def flat(s):
        for t in s:
            if isinstance(t, unittest.TestSuite):
                flat(t)
            else:
                cases.append(t)
    flat(unittest.TestLoader().loadTestsFromModule(mod))
    skipset = {x for x in skip.split(",") if x}
    todo = unittest.TestSuite(c for c in cases if c._testMethodName not in skipset)
    res = unittest.TextTestRunner(stream=io.StringIO(), failfast=True).run(todo)
    failed = [c.id().replace("t45.", "") for c, _ in res.failures + res.errors]
    print(json.dumps({"ran": res.testsRun, "failed": failed, "skipped": len(res.skipped)}))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=240, help="seconds per mutant")
    ap.add_argument("--only", help="run only the mutants whose name contains this text")
    ap.add_argument("--suite", help="(internal) run the suite of this scratch copy")
    ap.add_argument("--skip", default="", help="(internal) test names to skip")
    a = ap.parse_args()
    if a.suite:
        return suite_main(a.suite, a.skip)
    if not a.out:
        ap.error("--out is required")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=False)
    header = (HERE / "src" / "ladder_regs.h").read_text()
    mutants = [(m, "c") for m in C] + [(("derive-" + n, "derive.py", o, w), "derive") for n, o, w in DERIVE] + [(m, "table") for m in table_mutants(header)]
    if a.only:
        mutants = [(m, f) for m, f in mutants if a.only in m[0]]
    with tempfile.TemporaryDirectory(prefix="nat045-mut-") as tmp:
        base = make_tree(Path(tmp) / "base")
        verdict, detail = suite(base, (), a.timeout * 2)
        if verdict != "ok":
            print("baseline is not clean (%s: %s); refusing to judge mutants" % (verdict, detail))
            return 2
        results = []
        t0 = time.time()
        with concurrent.futures.ThreadPoolExecutor(a.jobs) as ex:
            futs = [ex.submit(one, i, m, f, tmp, a.timeout) for i, (m, f) in enumerate(mutants)]
            for fut in futs:
                r = fut.result()
                if r["status"] == "SURVIVED" and r["name"] in EQUIVALENT:
                    r["status"] = "equivalent"
                    r["detail"] = EQUIVALENT[r["name"]]
                results.append(r)
                print("%-58s %-10s %s" % (r["name"], r["status"], (r.get("by") or r.get("detail", ""))[:110]), flush=True)
    by = lambda s: sum(1 for r in results if r["status"] == s)  # noqa: E731
    fam = {f: dict(total=sum(1 for r in results if r["family"] == f), killed=sum(1 for r in results if r["family"] == f and r["status"] == "killed"))
           for f in ("c", "derive", "table")}
    summary = dict(total=len(results), killed=by("killed"), equivalent=by("equivalent"), survived=by("SURVIVED"), invalid=by("INVALID"), anchor_errors=by("ANCHOR"),
                   families=fam, seconds=round(time.time() - t0), interpreter_has_unicorn_and_capstone=_has_sim(), results=results)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print("killed %d, equivalent %d, survived %d, invalid %d, anchor errors %d, of %d (%s)" % (summary["killed"], summary["equivalent"], summary["survived"],
          summary["invalid"], summary["anchor_errors"], summary["total"], ", ".join("%s %d/%d" % (f, v["killed"], v["total"]) for f, v in fam.items())))
    bad = summary["survived"] + summary["invalid"] + summary["anchor_errors"]
    return 0 if not bad else 1


def _has_sim():
    try:
        import unicorn, capstone  # noqa: F401
        return True
    except ImportError:
        return False


if __name__ == "__main__":
    sys.exit(main())
