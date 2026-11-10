/* SPDX-License-Identifier: GPL-2.0-only */
#include "marker.h"

#ifndef MK_HOST
#define MK_HOST 0
#endif

#if MK_HOST
extern volatile uint64_t *mk_host_fb;
extern uint64_t mk_host_cnt;
static inline uint64_t mk_cnt(void) { return mk_host_cnt; }
static inline uint64_t mk_freq(void) { return MK_FREQ_FALLBACK; }
static inline void mk_clean(uint64_t a, uint64_t n) { (void)a; (void)n; }
#define MK_FB mk_host_fb
#define MK_SKIP_WAIT 1
extern void mk_host_drawn(uint32_t frame);
#else
#define MK_FB ((volatile uint64_t *)(uintptr_t)MK_FB_BASE)
#define MK_SKIP_WAIT 0
/* CNTVCT is readable at EL1 regardless of CNTHCTL_EL2 (CNTPCT is not). */
static inline uint64_t mk_cnt(void) { uint64_t v; __asm__ volatile("mrs %0, cntvct_el0" : "=r"(v)); return v; }
static inline uint64_t mk_freq(void) { uint64_t v; __asm__ volatile("mrs %0, cntfrq_el0" : "=r"(v)); return v ? v : MK_FREQ_FALLBACK; }
static inline void mk_clean(uint64_t a, uint64_t n)
{
	uint64_t ctr;
	__asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
	uint64_t line = 4ULL << ((ctr >> 16) & 0xf);
	for (uint64_t p = a & ~(line - 1); p < a + n; p += line)
		__asm__ volatile("dc civac, %0" : : "r"(p) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
}
#endif

#ifndef MK_TRIG
#define MK_TRIG 0
#endif

/* The fault images BRK after this many full report rounds (one round is 15 frames, ~18 s, in the
 * canary-trig loop). The default keeps canary-fault byte-identical. canary-trig-fault uses 0: the
 * two recordings so far show the display ending ~60 s after the first marker, so a BRK after
 * three rounds would leave too little time to read ESR/ELR/FAR. */
#ifndef MK_FAULT_ROUND
#define MK_FAULT_ROUND 2
#endif

/* Report state of the DECON0 kick (canary-trig). Plain data, lives on the caller's stack. */
struct mk_kick {
	uint32_t gc, tc0, tc1, fc_prev, fc_now, status, n;
};

#if MK_TRIG
#if MK_HOST
extern uint32_t mk_host_rd(uint32_t off);
extern void mk_host_wr(uint32_t off, uint32_t v);
extern int mk_host_mmu_on;
static inline uint32_t mk_rd(uint32_t o) { return mk_host_rd(o); }
static inline void mk_wr(uint32_t o, uint32_t v) { mk_host_wr(o, v); }
static inline int mk_mmu_on(void) { return mk_host_mmu_on; }
#else
static inline uint32_t mk_rd(uint32_t o) { return *(volatile uint32_t *)(uintptr_t)(MK_DECON0_BASE + o); }
static inline void mk_wr(uint32_t o, uint32_t v)
{
	*(volatile uint32_t *)(uintptr_t)(MK_DECON0_BASE + o) = v;
	__asm__ volatile("dsb sy" ::: "memory");
}
static inline int mk_mmu_on(void)
{
	uint64_t el, s;
	__asm__ volatile("mrs %0, CurrentEL" : "=r"(el));
	if (el == 8) __asm__ volatile("mrs %0, sctlr_el2" : "=r"(s));
	else __asm__ volatile("mrs %0, sctlr_el1" : "=r"(s));
	return (int)(s & 1);
}
#endif

/* 1 while a kick's MMIO is in flight. If the MMIO faulted the exception handler
 * finds it still 1 and never touches the block again (no fault loop). */
volatile uint32_t mk_kick_state = 0;

/* One DECON0 command-mode frame request, the vendor driver's sequence
 * (decon-trigger-facts.md): mask, global shadow update request, unmask.
 * Odd kicks use the HW-trigger form (the DT says trig_mode 0), even kicks the
 * SW-trigger form, because the DT is not register truth. Only TRIG_CON (0x30)
 * and SHD_REG_UP_REQ (0x50) are written; nothing is written when DECON is not
 * enabled or is in video mode, when the MMU is on, or after a faulted kick. */
static void mk_kick(struct mk_kick *k)
{
	uint32_t gc, tc0, mask, val;
	k->n++;
	if (mk_mmu_on()) { k->status = MK_KS_SKIP_MMU; return; }
	if (mk_kick_state) { k->status = MK_KS_POISONED; return; }
	mk_kick_state = 1;
	gc = mk_rd(MK_DECON_GLOBAL_CON);
	tc0 = mk_rd(MK_DECON_TRIG_CON);
	k->gc = gc; k->tc0 = tc0; k->tc1 = tc0;
	k->fc_prev = k->fc_now;
	k->fc_now = mk_rd(MK_DECON_FRAME_COUNT) & 0xffff;
	if (!(gc & MK_GC_DECON_EN)) { k->status = MK_KS_SKIP_OFF; mk_kick_state = 0; return; }
	if (!(gc & MK_GC_OP_CMD)) { k->status = MK_KS_SKIP_VIDEO; mk_kick_state = 0; return; }
	if (k->n & 1) {
		mask = MK_TC_HW_TRIG_EN | MK_TC_HW_TRIG_MASK;
		mk_wr(MK_DECON_TRIG_CON, (tc0 & ~mask) | mask);	/* mask */
		mk_wr(MK_DECON_SHD_REG_UP_REQ, mk_rd(MK_DECON_SHD_REG_UP_REQ) | MK_SHD_GLOBAL);
		mk_wr(MK_DECON_TRIG_CON, (mk_rd(MK_DECON_TRIG_CON) & ~mask) | MK_TC_HW_TRIG_EN);	/* unmask */
		k->status = MK_KS_SENT_HW;
	} else {
		mask = MK_TC_HW_TRIG_EN | MK_TC_SW_TRIG_EN | MK_TC_SW_TRIG_DET_EN;
		val = MK_TC_SW_TRIG_EN | MK_TC_SW_TRIG_DET_EN;
		mk_wr(MK_DECON_TRIG_CON, tc0 & ~mask);	/* mask */
		mk_wr(MK_DECON_SHD_REG_UP_REQ, mk_rd(MK_DECON_SHD_REG_UP_REQ) | MK_SHD_GLOBAL);
		mk_wr(MK_DECON_TRIG_CON, (mk_rd(MK_DECON_TRIG_CON) & ~mask) | val);	/* unmask */
		k->status = MK_KS_SENT_SW;
	}
	k->tc1 = mk_rd(MK_DECON_TRIG_CON);
	mk_kick_state = 0;
}
#endif

static inline void mk_draw(uint32_t frame, uint32_t prev, int full)
{
	for (uint32_t b = 0; b < MK_BANDS; b++) {
		uint32_t v = mk_band_value(frame, b);
		if (!full && b >= 2 && v == mk_band_value(prev, b))
			continue;
		volatile uint64_t *p = MK_FB + (b * MK_BAND_BYTES) / 8;
		uint64_t w = v ? ~0ULL : 0ULL;
		for (uint64_t i = 0; i < MK_BAND_BYTES / 8; i++)
			p[i] = w;
		mk_clean((uint64_t)(uintptr_t)p, MK_BAND_BYTES);
	}
#if MK_HOST
	mk_host_drawn(frame);
#endif
}

static inline void mk_wait_tenths(uint32_t tenths)
{
#if !MK_SKIP_WAIT
	uint64_t f = mk_freq(), s = mk_cnt(), t = f / 10 * tenths;
	while (mk_cnt() - s < t) { }
#else
	(void)tenths;
#endif
}

static inline uint32_t entry_data(uint64_t cel, uint64_t cur, uint64_t e1)
{
	return (uint32_t)(((cel >> 2) & 3) << 14 | (cur & 1) << 13 | ((cur >> 2) & 1) << 12 |
	    ((cur >> 12) & 1) << 11 | (e1 & 1) << 10 | ((e1 >> 2) & 1) << 9 | ((e1 >> 12) & 1) << 8);
}

__attribute__((noinline)) void mk_entry_frame(uint64_t cel, uint64_t cur, uint64_t e1)
{
	mk_draw(mk_frame(MK_ENTRY, 0, entry_data(cel, cur, e1)), 0, 1);
}

__attribute__((noinline, noreturn)) void
mk_gate_halt(uint64_t stage, uint64_t cel, uint64_t cur, uint64_t e1)
{
	uint64_t id = mk_cnt();
	uint32_t f0 = mk_frame(MK_ENTRY, 0, entry_data(cel, cur, e1));
	uint32_t f1 = mk_frame(MK_STAGE, 0, (uint32_t)stage);
	uint32_t f2 = mk_frame(MK_BOOTID, 0, (uint32_t)id);
	uint32_t f3 = mk_frame(MK_BOOTID, 1, (uint32_t)(id >> 16));
	mk_draw(f0, 0, 1);
	for (;;) {
		mk_wait_tenths(MK_DWELL_TENTHS); mk_draw(f1, f0, 0);
		mk_wait_tenths(MK_DWELL_TENTHS); mk_draw(f2, f1, 0);
		mk_wait_tenths(MK_DWELL_TENTHS); mk_draw(f3, f2, 0);
		mk_wait_tenths(MK_DWELL_TENTHS); mk_draw(f0, f3, 0);
	}
}

__attribute__((noinline)) void mk_stage(uint32_t stage)
{
	mk_draw(mk_frame(MK_STAGE, 0, stage), 0, 1);
}

static void kick_after_draw(struct mk_kick *k)
{
#if MK_TRIG
	mk_kick(k);
#else
	(void)k;
#endif
}

static void show(uint32_t *prev, uint32_t f, struct mk_kick *k)
{
	mk_draw(f, *prev, 0);
	*prev = f;
	kick_after_draw(k);
	mk_wait_tenths(MK_DWELL_TENTHS);
}

/* Shows a snapshot of the kick registers (canary-trig only). */
static void show_kick_report(uint32_t *prev, struct mk_kick *k)
{
#if MK_TRIG
	struct mk_kick s = *k;
	show(prev, mk_frame(MK_REG, MK_REG_STATUS, s.status), k);
	show(prev, mk_frame(MK_REG, MK_REG_GC_HI, s.gc >> 16), k);
	show(prev, mk_frame(MK_REG, MK_REG_GC_LO, s.gc), k);
	show(prev, mk_frame(MK_REG, MK_REG_TC0_HI, s.tc0 >> 16), k);
	show(prev, mk_frame(MK_REG, MK_REG_TC0_LO, s.tc0), k);
	show(prev, mk_frame(MK_REG, MK_REG_TC1_HI, s.tc1 >> 16), k);
	show(prev, mk_frame(MK_REG, MK_REG_TC1_LO, s.tc1), k);
	show(prev, mk_frame(MK_REG, MK_REG_FC_PREV, s.fc_prev), k);
	show(prev, mk_frame(MK_REG, MK_REG_FC_NOW, s.fc_now), k);
	show(prev, mk_frame(MK_REG, MK_REG_N, s.n), k);
#else
	(void)prev; (void)k;
#endif
}

__attribute__((noinline, noreturn)) void
mk_exception_loop(uint32_t slot, uint64_t esr, uint64_t elr, uint64_t far)
{
	uint32_t prev = 0;
	struct mk_kick k = {0, 0, 0, 0, 0, 0, 0};
	mk_draw(mk_frame(MK_STAGE, 0, MK_ST_EXC), 0, 1);
	prev = mk_frame(MK_STAGE, 0, MK_ST_EXC);
	kick_after_draw(&k);
	for (;;) {
		show(&prev, mk_frame(MK_SLOT, 0, slot), &k);
		for (uint32_t i = 0; i < 4; i++) show(&prev, mk_frame(MK_ESR, i, (uint32_t)(esr >> (48 - 16 * i))), &k);
		for (uint32_t i = 0; i < 4; i++) show(&prev, mk_frame(MK_ELR, i, (uint32_t)(elr >> (48 - 16 * i))), &k);
		for (uint32_t i = 0; i < 4; i++) show(&prev, mk_frame(MK_FAR, i, (uint32_t)(far >> (48 - 16 * i))), &k);
		show_kick_report(&prev, &k);
	}
}

/* Static frames repeat; with fault set, BRK #0x1234 follows three cycles so
 * the exception path (vectors, exception stack, ESR/ELR/FAR) is exercised. */
__attribute__((noinline)) void
mk_canary_loop(uint64_t cel, uint64_t cur, uint64_t e1, uint32_t stack_ok, int fault)
{
	uint64_t id = mk_cnt();
	uint32_t prev = 0;
	struct mk_kick k = {0, 0, 0, 0, 0, 0, 0};
	mk_draw(mk_frame(MK_STAGE, 0, MK_ST_CANARY_C), 0, 1);
	prev = mk_frame(MK_STAGE, 0, MK_ST_CANARY_C);
	kick_after_draw(&k);
	for (uint32_t round = 0;; round++) {
		show(&prev, mk_frame(MK_CHECK, 0, stack_ok ? 0xA5A5 : 0), &k);
		show(&prev, mk_frame(MK_ENTRY, 0, entry_data(cel, cur, e1)), &k);
		show(&prev, mk_frame(MK_BOOTID, 0, (uint32_t)id), &k);
		show(&prev, mk_frame(MK_BOOTID, 1, (uint32_t)(id >> 16)), &k);
		show(&prev, mk_frame(MK_STAGE, 0, MK_ST_CANARY_C), &k);
		show_kick_report(&prev, &k);
		if (fault && round == MK_FAULT_ROUND) {
			show(&prev, mk_frame(MK_STAGE, 0, MK_ST_CANARY_BRK), &k);
#if !MK_HOST
			__asm__ volatile("brk #0x1234");
#endif
		}
	}
}

static inline int overlaps(uint64_t a0, uint64_t a1)
{
	return a0 < MK_FB_BASE + MK_BANDS * MK_BAND_BYTES && MK_FB_BASE < a1;
}

__attribute__((noinline)) int mk_fb_safe(uint64_t is, uint64_t ie, uint64_t dtb)
{
	if (overlaps(is, ie))
		return 0;
	if (dtb && !(dtb & 3) && !overlaps(dtb, dtb + 1)) {
		const volatile uint8_t *p = (const volatile uint8_t *)(uintptr_t)dtb;
		if (p[0] == 0xd0 && p[1] == 0x0d && p[2] == 0xfe && p[3] == 0xed) {
			uint64_t size = (uint64_t)p[4] << 24 | (uint64_t)p[5] << 16 | (uint64_t)p[6] << 8 | p[7];
			if (size > (1ULL << 26) || overlaps(dtb, dtb + size))
				return 0;
		}
	} else if (dtb && overlaps(dtb, dtb + 1)) {
		return 0;
	}
	return 1;
}
