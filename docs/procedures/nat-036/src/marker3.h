/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-036: the report frames of the resumable-stop image (loader-diag-xnu-ckpt3). Everything NAT-022's marker.h defines
 * is unchanged; this header only adds one frame kind and the structure the new report routines take.
 *
 * Frame protocol as before: kind[31:28] idx[27:24] data16[23:8] crc8[7:0]. */
#ifndef NAT036_MARKER3_H
#define NAT036_MARKER3_H
#include "marker.h"

#define MK_CKPT3 13	/* NAT-036 only, see enum mk_ckpt3_idx */

enum mk_ckpt3_idx {
	/* The one frame every pass draws (and the first of the final report): data = (arrivals & 0xff) << 8 | (last & 0xff).
	 * arrivals counts every arrival at the stub, so the stops 1..5 are arrivals 1..5 and the first C stop is arrival 6;
	 * last is the number of the checkpoint reached (1..5 assembly, 10..44 C). Because the kernel passes the stops in
	 * program order, (arrivals, last) says exactly which of them were passed even if the camera missed a frame. */
	MK_C3_PASS = 0,
	MK_C3_LIST = 1,		/* data = number of stops in the list (the C stops after checkpoint 5) */
	MK_C3_SP_2 = 2, MK_C3_SP_1 = 3, MK_C3_SP_0 = 4,		/* the kernel's SP at the stop (loader_jump's frame), bits 47:32, 31:16, 15:0 */
	MK_C3_KTTBR0_2 = 5, MK_C3_KTTBR0_1 = 6, MK_C3_KTTBR0_0 = 7,	/* the kernel's own TTBR0 as read at the checkpoint-5 stop */
	MK_C3_X1_HI = 8, MK_C3_X1_LO = 9,	/* x1 at the stop: the length of loader_log (0 = the kernel logged nothing) */
	MK_C3_X0_2 = 10, MK_C3_X0_1 = 11, MK_C3_X0_0 = 12	/* x0 at the stop: loader_log PA, bits 47:32, 31:16, 15:0 */
};

/* What the stub read on this arrival. The system registers are read after the prologue cleared SCTLR_EL1.M/C; the arrival
 * SCTLR_EL1 is the one the prologue saved. */
struct mk_ckpt3 {
	uint64_t x2, x3;			/* the kernel's reason (2 = checkpoint, 1 = exception, 0 = done) and code */
	uint64_t sctlr, ttbr1, tcr, vbar;	/* arrival SCTLR_EL1; the others as read */
	uint64_t esr, elr, far;			/* meaningful only when x2 == 1 */
	uint64_t sp, x0, x1;			/* the kernel's SP and x0/x1 at the arrival */
	uint64_t kttbr0;			/* the kernel's TTBR0 captured at checkpoint 5 (0 = not captured) */
	uint32_t mask, arrivals, last, nstops;	/* nat031 mask (+ NAT-036 bits), arrival count, last checkpoint reached, list length */
};

/* MK_LOADER=1 and MK_XNU_CKPT=1 only (markerlib3.c). mk_ckpt3_pass draws ONE frame (MK_C3_PASS) with a full
 * redraw, a DECON0 kick and one dwell, and returns; mk_ckpt3_hold never returns and repeats the full report. */
void mk_ckpt3_pass(const struct mk_ckpt3 *r);
void mk_ckpt3_hold(const struct mk_ckpt3 *r) __attribute__((noreturn));
#endif
