/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-036: the report routines of loader-diag-xnu-ckpt3.
 *
 * This translation unit is NAT-022's markerlib.c, unmodified, plus the two routines below. They need markerlib.c's
 * static helpers (mk_draw, show, ld_after_draw, ld_k, ld_mask), so they live in the same unit; the NAT-022 sources and
 * every earlier image stay byte-identical. The build compiles this file instead of markerlib.c. */
#include "markerlib.c"
#include "marker3.h"

#if MK_LOADER && MK_XNU_CKPT
static inline uint32_t c3_x(uint64_t v, uint32_t sh)
{
	return (uint32_t)(v >> sh) & 0xffffu;
}

static inline uint32_t c3_regs(const struct mk_ckpt3 *r)
{
	return (uint32_t)((r->x2 & 0xff) << 8 | (r->x3 & 0xff));
}

static inline uint32_t c3_pass(const struct mk_ckpt3 *r)
{
	return (r->arrivals & 0xffu) << 8 | (r->last & 0xffu);
}

/* A stop the stub resumes from: one frame, drawn in full, kicked, shown for one dwell (1.2 s plus the draw). Everything
 * else the earlier passes drew (the mask frame) is implied by (arrivals, last), so a pass costs one frame, not two. */
__attribute__((noinline)) void mk_ckpt3_pass(const struct mk_ckpt3 *r)
{
	uint32_t f = mk_frame(MK_CKPT3, MK_C3_PASS, c3_pass(r));
	ld_mask |= 1u << ld_bit(MK_ST_CKPT);
	mk_draw(f, 0, 1);		/* full redraw: whatever was on the bands before is not trusted */
	ld_after_draw();
}

/* The terminal report. The values the run is about come first (which stop, why, the kernel's SP, its own TTBR0, the log
 * length), so a run that the watchdog cuts off still shows them; the system registers follow. Reason 1 (early exception)
 * shows ESR/ELR/FAR in place of the register block, as the earlier holds do. */
__attribute__((noinline, noreturn)) void mk_ckpt3_hold(const struct mk_ckpt3 *r)
{
	uint64_t id = mk_cnt();
	uint32_t prev = mk_frame(MK_STAGE, 0, MK_ST_CKPT);
	ld_mask |= 1u << ld_bit(MK_ST_CKPT);
	mk_draw(prev, 0, 1);
	ld_after_draw();
	for (;;) {
		show(&prev, mk_frame(MK_CKPT3, MK_C3_PASS, c3_pass(r)), &ld_k);
		show(&prev, mk_frame(MK_CKPT, MK_CK_REGS, c3_regs(r)), &ld_k);
		show(&prev, mk_frame(MK_CKPT, MK_CK_MASK, r->mask), &ld_k);
		show(&prev, mk_frame(MK_CKPT3, MK_C3_LIST, r->nstops), &ld_k);
		if ((r->x2 & 0xff) == 1) {
			for (uint32_t i = 0; i < 4; i++) show(&prev, mk_frame(MK_ESR, i, (uint32_t)(r->esr >> (48 - 16 * i))), &ld_k);
			for (uint32_t i = 0; i < 4; i++) show(&prev, mk_frame(MK_ELR, i, (uint32_t)(r->elr >> (48 - 16 * i))), &ld_k);
			for (uint32_t i = 0; i < 4; i++) show(&prev, mk_frame(MK_FAR, i, (uint32_t)(r->far >> (48 - 16 * i))), &ld_k);
		} else {
			show(&prev, mk_frame(MK_CKPT3, MK_C3_SP_2, c3_x(r->sp, 32)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_SP_1, c3_x(r->sp, 16)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_SP_0, c3_x(r->sp, 0)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_KTTBR0_2, c3_x(r->kttbr0, 32)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_KTTBR0_1, c3_x(r->kttbr0, 16)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_KTTBR0_0, c3_x(r->kttbr0, 0)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_X1_HI, c3_x(r->x1, 16)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_X1_LO, c3_x(r->x1, 0)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_X0_2, c3_x(r->x0, 32)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_X0_1, c3_x(r->x0, 16)), &ld_k);
			show(&prev, mk_frame(MK_CKPT3, MK_C3_X0_0, c3_x(r->x0, 0)), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_SCTLR_LO, (uint32_t)r->sctlr), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_SCTLR_HI, (uint32_t)(r->sctlr >> 16)), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_TTBR1_2, (uint32_t)(r->ttbr1 >> 32)), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_TTBR1_1, (uint32_t)(r->ttbr1 >> 16)), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_TTBR1_0, (uint32_t)r->ttbr1), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_VBAR, (uint32_t)r->vbar), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_TCR_LO, (uint32_t)r->tcr), &ld_k);
			show(&prev, mk_frame(MK_CKPT, MK_CK_TCR_HI, (uint32_t)(r->tcr >> 16)), &ld_k);
		}
		show(&prev, mk_frame(MK_BOOTID, 0, (uint32_t)id), &ld_k);
		show(&prev, mk_frame(MK_BOOTID, 1, (uint32_t)(id >> 16)), &ld_k);
		show(&prev, mk_frame(MK_STAGE, 0, MK_ST_CKPT), &ld_k);
		show_kick_report(&prev, &ld_k);
	}
}
#endif
