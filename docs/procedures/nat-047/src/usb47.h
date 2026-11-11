/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-047: the hooks the loader and the marker library call to move text and exceptions over USB (the NAT-041 usbmon engine,
 * brought up by the NAT-045 ladder). Declarations only; the code is markerlib47.c. Every hook is a no-op until the engine is
 * up, so a stop inside the ladder leaves the loader exactly as the NAT-044 image behaves. */
#ifndef NAT047_USB47_H
#define NAT047_USB47_H
#include <stdint.h>

struct mk_kick;

/* One engine poll when the engine is up. Called from every band of mk_draw and from every wait loop (mk_wait_tenths). */
void nat047_poll(void);
/* mk_stage(): the stage number becomes a STAGE record. */
void nat047_stage(uint32_t stage);
/* log_char(): characters of the loader's RAM log become TEXT records, one per line. */
void nat047_log_char(char c);
/* mk_hold() before its report loop: a HOLD note; the fault image executes its controlled BRK here. */
void nat047_hold(uint32_t stage, uint32_t code);
/* mk_exception_loop(): the exception becomes a FAULT record (once). */
void nat047_fault(uint32_t slot, uint64_t esr, uint64_t elr, uint64_t far);
/* The report frames of the hold and exception loops (kind MK_USB). */
void nat047_show(uint32_t *prev, struct mk_kick *k);
/* loader_main(), right after the LOADER_MAIN stage: the ladder, the engine, the boot record, the replay of the RAM log so far. */
void nat047_bringup(const char *log, uint32_t log_len);
#endif
