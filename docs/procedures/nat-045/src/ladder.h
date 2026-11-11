/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * NAT-045: the USB bring-up ladder of the loader (freestanding C, no libc, no allocation).
 *
 * The register sequences (addresses, masks, values, delays, order) are NOT written in ladder.c. They are the generated
 * table ladder_regs.h (derive.py, from the vendor sources pinned in ladder_spec.json); ladder.c only interprets it:
 *
 *   rung  what                                                                                      writes
 *   L0    table self-check, hardware untouched                                                      no
 *   L1    pd_hsi0 power state: PMU HSI0_CONFIGURATION / HSI0_STATUS (always-on PMU)                  no
 *   L2    CMU_TOP mux / gate / divider that feed HSI0 (always on)                                    no
 *   L3    domain off: vendor power-on + bounded wait + hsi0_cmu_init rows; then CMU_HSI0 / QCH reads   yes
 *   L4    DWC3 liveness: GSNPSID upper half is 0x5533 or 0x3331                                      no
 *   L5    PHY isolation release, USBCON init_link, pipe3 detach, eUSB2 PHY initiate, read-backs       yes
 *   L6-8  NAT-041 usbmon engine: core init + RUN_STOP, bus reset / CONNECTDONE, host nonce            yes  (ladder_usb.c)
 *
 * L0-L2 are read-only. Rungs that write (L3 and above) exist only in an image built with -DLAD_WRITING_RUNGS; without it
 * lad_run() refuses them (LAD_E_DISABLED) and no store to the platform is compiled into ladder.c at all. The default
 * stop rung is 2 in that build.
 *
 * A write rung stops at the first failure and says where: lad_state.err = -(rung * 16 + code), err_op = index into the
 * table (ladder_ops.json names it). Nothing is retried. A read-back mismatch, a wait that times out, a block that does not
 * answer are all stops, never silent: "a stuck bit points to a gated clock or an unpowered rail".
 *
 * Nothing here has run on the phone.
 */
#ifndef LADDER_H
#define LADDER_H

#include <stddef.h>
#include <stdint.h>

#define LAD_OK		0
#define LAD_E_READBACK	1	/* a write was read back and the bits written differ */
#define LAD_E_TIMEOUT	2	/* a bounded wait ended without the awaited value */
#define LAD_E_STATE	3	/* precondition does not hold (domain off and power-on not allowed, or L1 did not run) */
#define LAD_E_NOTALIVE	4	/* the block answered with a word that means it is not there (all-zero/all-ones/foreign id) */
#define LAD_E_CFG	5	/* bad configuration or an inconsistent op table */
#define LAD_E_DISABLED	6	/* the rung writes and the image was built without LAD_WRITING_RUNGS */

#define LAD_ERR(rung, code)	(-((int)(rung) * 16 + (int)(code)))
#define LAD_ERR_RUNG(e)		((-(e)) / 16)
#define LAD_ERR_CODE(e)		((-(e)) % 16)

#define LAD_LAST_RUNG		5	/* ladder.c: L0..L5; ladder_usb.c: L6..L8 */

struct lad_cfg {
	uint32_t stop_after;		/* highest rung to run (0..LAD_LAST_RUNG) */
	uint32_t allow_pd_poweron;	/* L3: run the vendor hsi0_on rows when HSI0_STATUS reads off; 0 = stop with LAD_E_STATE */
	uint32_t pd_wait_us;		/* L3: bound of the HSI0_STATUS wait; 0 = the vendor's 200000 */
};

/* One record per hardware access, in the order they happened (an op that does not touch hardware leaves none). */
struct lad_rec {
	uint16_t op;			/* index into the op table */
	uint16_t pad;
	uint32_t v0;			/* RD LOAD RDLOG: value read; WRM: value read before; WRP STORE: value written; WAIT: last value */
	uint32_t v1;			/* WRM WRP STORE: value read back; WAIT: microseconds waited */
};

/* The op table size is generated; the record array is sized to it so it cannot overflow (every op runs at most once). */
#include "ladder_regs.h"

struct lad_state {
	struct lad_rec rec[LAD_NOPS];
	uint16_t nrec;
	int16_t err;			/* 0, or LAD_ERR(rung, code) */
	uint16_t err_op;		/* op index of the failure, LAD_NOPS when none / not an op */
	uint8_t rung_done;		/* highest rung that completed */
	uint8_t pd_was_on;		/* L1: HSI0_STATUS said on at entry; 0xff = not read */
	uint16_t soft_mismatch;		/* read-back mismatches of vendor writes the NAT-040 plan does not list (not fatal) */
	uint32_t gsnpsid;		/* L4 */
};

void lad_default_cfg(struct lad_cfg *c);
int lad_selfcheck(void);		/* L0: 0 or LAD_ERR(0, LAD_E_CFG); touches no hardware */
int lad_run(struct lad_state *st, const struct lad_cfg *cfg);	/* 0 or the stop code (also in st->err) */

/* ---- L6-L8 (ladder_usb.c): the NAT-041 engine behind the ladder ---- */
struct usbmon;
struct usbmon_cfg;
int lad_usb_start(struct usbmon *m, const struct usbmon_cfg *cfg, int *err);	/* L6: usbmon_init */
/* L7/L8: poll the engine until `flag` is set in m->flags or max_polls polls passed; 0 or the stop code. */
int lad_usb_wait(struct usbmon *m, unsigned rung, uint32_t flag, uint32_t max_polls, uint32_t poll_delay_us);
#define LAD_USB_RUNG_START	6
#define LAD_USB_RUNG_CONNECT	7
#define LAD_USB_RUNG_HOST	8

#endif
