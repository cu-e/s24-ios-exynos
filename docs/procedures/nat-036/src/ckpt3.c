/* SPDX-License-Identifier: GPL-2.0-only */
#include "ckpt3.h"

/* The checkpoint order of the payload kernel's arm_init (NAT-029), up to the last one before arm_vm_init. */
const uint8_t nat036_order[NAT036_ORDER_LEN] = {
	10, 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16,
};

/* The first 27 instructions of loader_jump (0xfffffff00744f1cc .. 0xfffffff00744f234) of the NAT-020 build-003 payload:
 * the frame, the slot[1] test, the loader_return_entered test and early return, the TCR check, the early-return epilogue
 * (index 19..21: ldp x29, x30, [sp, #0x30]; add sp, sp, #0x40; ret) and the store that sets the flag (index 25, 26). The
 * test re-derives this table from the payload bytes on every run. */
const uint32_t nat036_jump_words[NAT036_JUMP_WORDS] = {
	0xd10103ff, 0xa9037bfd, 0x9100c3fd, 0xd503201f, 0xd503201f, 0x58f6b0c8, 0xb81fc3bf, 0xb4000188, 0x90004949,
	0x3940252a, 0x3700012a, 0xd538204a, 0x9240154b, 0xd100896c, 0xb100259f, 0xcb0b03eb, 0x9acb250b, 0xfa402960,
	0x54000080, 0xa9437bfd, 0x910103ff, 0xd65f03c0, 0xf90007ea, 0xf81f03a8, 0xa90107e0, 0x52800028, 0x39002528,
};

/* _set_mmu_ttb: dsb ish; msr ttbr0_el1, x0; isb; ret. */
const uint32_t nat036_setttb_words[NAT036_SETTTB_WORDS] = { 0xd5033b9f, 0xd5182000, 0xd5033fdf, 0xd65f03c0 };

static inline uint32_t rd32(uintptr_t pa)
{
	return *(const volatile uint32_t *)pa;
}

static inline uint8_t rd8(uintptr_t pa)
{
	return *(const volatile uint8_t *)pa;
}

static inline void st64(uintptr_t pa, uint64_t v)
{
	*(volatile uint64_t *)pa = v;
}

int nat036_list_ok(const uint8_t *stops, uint32_t n)
{
	uint32_t pos = 0;

	if (!stops || n < 1 || n > NAT036_MAX_STOPS)
		return 0;
	for (uint32_t i = 0; i < n; i++) {
		while (pos < NAT036_ORDER_LEN && nat036_order[pos] != stops[i])
			pos++;
		if (pos == NAT036_ORDER_LEN)
			return 0;	/* not in the table, or out of program order (the scan only moves forward) */
		pos++;
	}
	return 1;
}

static int words_ok(uintptr_t pa, const uint32_t *w, uint32_t n)
{
	for (uint32_t i = 0; i < n; i++)
		if (rd32(pa + 4 * i) != w[i])
			return 0;
	return 1;
}

int nat036_check(uintptr_t win_base, uint64_t virt_base, uint64_t stub_pa, uint64_t stub_end_pa,
    const uint8_t *stops, uint32_t nstops, uint32_t *bad)
{
	int rc = nat031_check(win_base, virt_base, bad);

	if (rc)
		return rc;
	if (!nat036_list_ok(stops, nstops))
		return NAT036_LIST_BAD;
	if (stub_end_pa <= stub_pa || (stub_pa >> 21) != ((stub_end_pa - 1) >> 21))
		return NAT036_BLOCK_BAD;
	if (!words_ok(win_base + (uintptr_t)(NAT036_JUMP_VA - virt_base), nat036_jump_words, NAT036_JUMP_WORDS))
		return NAT036_JUMP_BAD;
	if (!words_ok(win_base + (uintptr_t)(NAT036_SETTTB_VA - virt_base), nat036_setttb_words, NAT036_SETTTB_WORDS))
		return NAT036_SETTTB_BAD;
	if (rd8(win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base)) != 0)
		return NAT036_FLAG_BAD;
	return NAT036_OK;
}

int nat036_prepare(struct nat036_state *st, uintptr_t win_base, uint64_t virt_base, uint64_t stub_pa, uint64_t stub_end_pa,
    const uint8_t *stops, uint32_t nstops, uint32_t *bad)
{
	int rc = nat036_check(win_base, virt_base, stub_pa, stub_end_pa, stops, nstops, bad);

	if (rc)
		return rc;
	st->stops = stops;
	st->nstops = nstops;
	st->idx = 0;
	st->last = 0;
	st->pad = 0;
	st->kernel_ttbr0 = 0;
	st->flag_pa = win_base + (uintptr_t)(NAT036_FLAG_VA - virt_base);
	return nat031_prepare(&st->s, win_base, virt_base, stub_pa, bad);
}

/* A table base the C resume may write back: not zero, no stray bits in 11:1 (bit 0 is CnP, the ASID in 63:48 is the kernel's). */
static int ttbr0_ok(uint64_t t)
{
	return (t & 0x0000fffffffff000ULL) != 0 && (t & 0xffeULL) == 0;
}

void nat036_decide(struct nat036_state *st, uint64_t x2, uint64_t x3, uint64_t sctlr, uint64_t ttbr0, struct nat036_decision *d)
{
	struct nat031_decision d31;

	d->action = NAT036_HOLD;
	d->next = 0;
	d->final = 0;
	d->resume_pa = 0;
	if (x2 == 2 && x3 == 5 && st->s.expect == 5 && !(sctlr & 1)) {
		/* checkpoint 5, an assembly stop: the MMU is off and TTBR0 is the kernel's own. */
		st->s.arrivals++;
		st->s.mask |= 1u << 5;
		st->last = 5;
		if (!ttbr0_ok(ttbr0)) {
			st->s.mask |= NAT036_MASK_BAD_TTBR0;
			return;
		}
		st->kernel_ttbr0 = ttbr0;
		st->idx = 0;
		st->s.expect = st->stops[0];
		d->action = NAT036_RESUME_ASM;
		d->next = st->stops[0];
		d->resume_pa = nat031_site_va(5) - NAT034_RESUME_BACK + st->s.pa_minus_va;
		return;
	}
	if (x2 == 2 && st->kernel_ttbr0 && st->idx < st->nstops && x3 == st->stops[st->idx] && x3 == st->s.expect) {
		/* the C stop the kernel was set up to reach */
		st->s.arrivals++;
		st->last = (uint32_t)x3;
		if (!(sctlr & 1)) {			/* a C stop always arrives with the MMU on; anything else is not understood */
			st->s.mask |= NAT036_MASK_BAD_STATE;
			return;
		}
		if (st->idx + 1 < st->nstops) {
			st->idx++;
			st->s.expect = st->stops[st->idx];
			d->action = NAT036_RESUME_C;
			d->next = st->stops[st->idx];
			return;
		}
		st->s.mask |= NAT036_MASK_FINAL;
		d->final = 1;
		return;
	}
	nat031_decide(&st->s, x2, x3, &d31);
	if (d31.action == NAT031_RESUME) {
		st->last = (uint32_t)x3;
		d->action = NAT036_RESUME_ASM;
		d->next = d31.next;
		d->resume_pa = d31.resume_pa;
	}
}

void nat036_set_next(const struct nat031_state *st, uint32_t next)
{
#ifndef NAT031_HOST
	__asm__ volatile("dc civac, %0\n\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");
#endif
	st64(st->slot_pa + 16, next);
#ifndef NAT031_HOST
	__asm__ volatile("dsb sy\n\tdc civac, %0\n\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");
#endif
}

void nat036_clear_flag(uint64_t flag_pa)
{
#ifndef NAT031_HOST
	__asm__ volatile("dc civac, %0\n\tdsb sy" :: "r"(flag_pa) : "memory");
#endif
	*(volatile uint8_t *)(uintptr_t)flag_pa = 0;
#ifndef NAT031_HOST
	__asm__ volatile("dsb sy\n\tdc civac, %0\n\tdsb sy" :: "r"(flag_pa) : "memory");
#endif
}

void nat036_report(struct mk_ckpt3 *r, const struct nat036_state *st, const struct nat031_frame *f, uint64_t ttbr1, uint64_t tcr,
    uint64_t vbar)
{
	r->x2 = f->x[2];
	r->x3 = f->x[3];
	r->sctlr = f->x[11];	/* the stub's prologue keeps the arrival value in the x11 slot */
	r->ttbr1 = ttbr1;
	r->tcr = tcr;
	r->vbar = vbar;
	r->esr = f->x[3];	/* the early-exception report: x3 = ESR, x4 = ELR, x5 = FAR */
	r->elr = f->x[4];
	r->far = f->x[5];
	r->sp = f->sp;
	r->x0 = f->x[0];
	r->x1 = f->x[1];
	r->kttbr0 = st->kernel_ttbr0;
	r->mask = st->s.mask;
	r->arrivals = st->s.arrivals;
	r->last = st->last;
	r->nstops = st->nstops;
}

#ifndef NAT031_HOST

#ifndef NAT036_STOP_LIST
#define NAT036_STOP_LIST 11, 30, 31, 32, 33, 34, 35, 12, 40, 41, 42, 43, 44, 13, 14, 15, 16
#endif

static const uint8_t nat036_list[] = { NAT036_STOP_LIST };
static struct nat036_state nat036_st;
static struct nat036_cres nat036_cres = { 0, NAT036_JUMP_VA + NAT036_JUMP_EPILOGUE, NAT036_SETTTB_VA };
extern char nat036_stub_end[];

int nat036_install(uintptr_t win_base, uint64_t virt_base, uint32_t *bad)
{
	return nat036_prepare(&nat036_st, win_base, virt_base, (uint64_t)(uintptr_t)nat036_stub,
	    (uint64_t)(uintptr_t)nat036_stub_end, nat036_list, (uint32_t)sizeof nat036_list, bad);
}

const char *nat036_msg(int rc, uint32_t bad)
{
	static const char *const site[] = {
		"XNU checkpoint slot check failed", "XNU checkpoint site 1 check failed", "XNU checkpoint site 2 check failed",
		"XNU checkpoint site 3 check failed", "XNU checkpoint site 4 check failed", "XNU checkpoint site 5 check failed",
	};

	switch (rc) {
	case NAT031_SLOT_BAD: return site[0];
	case NAT031_SITE_BAD: return site[bad >= 1 && bad <= 5 ? bad : 0];
	case NAT036_LIST_BAD: return "XNU stop list invalid";
	case NAT036_BLOCK_BAD: return "XNU stub not in one 2 MiB block";
	case NAT036_JUMP_BAD: return "XNU loader_jump check failed";
	case NAT036_SETTTB_BAD: return "XNU set_mmu_ttb check failed";
	case NAT036_FLAG_BAD: return "XNU return flag check failed";
	default: return "XNU checkpoint install failed";
	}
}

struct nat036_ret nat036_ckpt_c(const struct nat031_frame *f)
{
	struct mk_ckpt3 r;
	struct nat036_decision d;
	struct nat036_ret ret;
	uint64_t ttbr0, ttbr1, tcr, vbar;

	/* The prologue of the stub has already cleared SCTLR_EL1.M and C; the value it read before is in the x11 slot. */
	__asm__ volatile("mrs %0, ttbr1_el1" : "=r"(ttbr1));
	__asm__ volatile("mrs %0, tcr_el1" : "=r"(tcr));
	__asm__ volatile("mrs %0, vbar_el1" : "=r"(vbar));
	__asm__ volatile("mrs %0, ttbr0_el1" : "=r"(ttbr0));
	nat036_decide(&nat036_st, f->x[2], f->x[3], f->x[11], ttbr0, &d);
	nat036_report(&r, &nat036_st, f, ttbr1, tcr, vbar);
	if (d.action == NAT036_HOLD)
		mk_ckpt3_hold(&r);
	mk_ckpt3_pass(&r);
	if (d.action == NAT036_RESUME_C)
		nat036_clear_flag(nat036_st.flag_pa);
	if (d.action == NAT036_RESUME_ASM && d.next <= 5)
		nat031_set_next(&nat036_st.s, d.next);		/* checkpoints 1..4: exactly as runs 008 and 009 */
	else
		nat036_set_next(&nat036_st.s, d.next);		/* from checkpoint 5 on the kernel caches the slot line */
	if (d.action == NAT036_RESUME_C) {
		nat036_cres.ttbr0 = nat036_st.kernel_ttbr0;
		ret.v = (uint64_t)(uintptr_t)&nat036_cres;
		ret.mode = 1;
	} else {
		ret.v = d.resume_pa;
		ret.mode = 0;
	}
	return ret;
}
#endif
