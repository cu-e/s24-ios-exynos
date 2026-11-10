/* SPDX-License-Identifier: GPL-2.0-only */
#include "ckpt.h"

static const uint64_t site_va[NAT031_NSITES] = {
	0xfffffff00743e068ULL, 0xfffffff00743e0c4ULL, 0xfffffff00743e304ULL,
	0xfffffff00743e408ULL, 0xfffffff00743e470ULL,
};

uint64_t nat031_site_va(uint32_t n)
{
	return n >= 1 && n <= NAT031_NSITES ? site_va[n - 1] : 0;
}

static inline uint32_t rd32(uintptr_t pa)
{
	return *(const volatile uint32_t *)pa;
}

static inline uint64_t rd64(uintptr_t pa)
{
	return *(const volatile uint64_t *)pa;
}

/* The checkpoint macro of NAT-029, word by word. The adrp/add pair is not compared with fixed bits: it
 * is decoded and must point at the slot, so a site that loads some other address is refused too. */
static int site_ok(uintptr_t pa, uint64_t va, uint32_t n)
{
	uint32_t w[NAT031_SITE_WORDS];
	uint64_t page, imm;

	for (uint32_t i = 0; i < NAT031_SITE_WORDS; i++)
		w[i] = rd32(pa + 4 * i);
	if ((w[0] & 0x9f00001fu) != 0x90000009u)		/* adrp x9, <page> */
		return 0;
	if ((w[1] & 0xffc003ffu) != 0x91000129u)		/* add x9, x9, #imm12 (no shift) */
		return 0;
	imm = ((uint64_t)((w[0] >> 5) & 0x7ffffu) << 2) | ((w[0] >> 29) & 3u);
	if (imm & (1u << 20))
		imm |= ~0x1fffffULL;				/* sign extend the 21-bit page offset */
	page = (va & ~0xfffULL) + (imm << 12);
	if (page + ((w[1] >> 10) & 0xfffu) != NAT031_SLOT_VA)
		return 0;
	return w[2] == 0xf940092au &&				/* ldr x10, [x9, #16] */
	    w[3] == (0xf100015fu | (n << 10)) &&		/* cmp x10, #n */
	    w[4] == 0x54000161u &&				/* b.ne +44: over the stop path, to site + 60 */
	    w[5] == 0xd2800000u && w[6] == 0xd2800001u &&	/* mov x0, #0; mov x1, #0 */
	    w[7] == 0xd2800042u &&				/* mov x2, #2 */
	    w[8] == (0xd2800003u | (n << 5)) &&			/* mov x3, #n */
	    w[9] == 0xd538100bu &&				/* mrs x11, sctlr_el1 */
	    w[10] == 0x927ff96bu &&				/* and x11, x11, #~1 (clear M) */
	    w[11] == 0xd518100bu &&				/* msr sctlr_el1, x11 */
	    w[12] == 0xd5033fdfu &&				/* isb */
	    w[13] == 0xf9400529u &&				/* ldr x9, [x9, #8] */
	    w[14] == 0xd61f0120u;				/* br x9 */
}

int nat031_check(uintptr_t win_base, uint64_t virt_base, uint32_t *bad)
{
	uintptr_t slot = win_base + (uintptr_t)(NAT031_SLOT_VA - virt_base);

	*bad = 0;
	if (slot % 8 || rd64(slot) != 0x545352444c554e58ULL /* "XNULDRST" */ ||
	    rd64(slot + 8) || rd64(slot + 16) || rd64(slot + 24))
		return NAT031_SLOT_BAD;
	for (uint32_t n = 1; n <= NAT031_NSITES; n++) {
		uint64_t va = nat031_site_va(n);

		if (!site_ok(win_base + (uintptr_t)(va - virt_base), va, n)) {
			*bad = n;
			return NAT031_SITE_BAD;
		}
	}
	return NAT031_OK;
}

static inline void st64(uintptr_t pa, uint64_t v)
{
	*(volatile uint64_t *)pa = v;
}

int nat031_prepare(struct nat031_state *st, uintptr_t win_base, uint64_t virt_base, uint64_t stub_pa, uint32_t *bad)
{
	int rc = nat031_check(win_base, virt_base, bad);
	uintptr_t slot = win_base + (uintptr_t)(NAT031_SLOT_VA - virt_base);

	if (rc)
		return rc;
	st->slot_pa = slot;
	st->pa_minus_va = (uint64_t)win_base - virt_base;
	st->expect = 1;
	st->mask = 0;
	st->arrivals = 0;
	st->pad = 0;
	st64(slot + 24, st->pa_minus_va);
	st64(slot + 8, stub_pa);
	st64(slot + 16, 1);		/* last: until this word is nonzero no checkpoint stops */
#ifndef NAT031_HOST
	__asm__ volatile("dsb sy" ::: "memory");
#endif
	return NAT031_OK;
}

void nat031_decide(struct nat031_state *st, uint64_t x2, uint64_t x3, struct nat031_decision *d)
{
	st->arrivals++;
	d->action = NAT031_HOLD;
	d->next = 0;
	d->resume_pa = 0;
	if (x2 == 2 && x3 == st->expect && x3 >= 1 && x3 <= NAT031_NSITES) {
		st->mask |= 1u << x3;
		if (x3 < NAT031_NSITES) {
			st->expect = (uint32_t)x3 + 1;
			d->action = NAT031_RESUME;
			d->next = st->expect;
			d->resume_pa = nat031_site_va((uint32_t)x3) + NAT031_SITE_WORDS * 4 + st->pa_minus_va;
		}
		return;
	}
	st->mask |= x2 == 1 ? NAT031_MASK_EXC : x2 == 0 ? NAT031_MASK_ORDERLY : NAT031_MASK_OTHER;
}

void nat031_set_next(const struct nat031_state *st, uint32_t next)
{
	st64(st->slot_pa + 16, next);
#ifndef NAT031_HOST
	__asm__ volatile("dsb sy\n\tdc civac, %0\n\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");
#endif
}

/* NAT034_IMAGE (loader-diag-xnu-ckpt2): that image has its own stub and C entry (ckpt2.c, ckpt2_stub.S), so the
 * loader block below is left out of it. No earlier image defines the macro: their object code is unchanged. */
#if !defined(NAT031_HOST) && !defined(NAT034_IMAGE)
#include "marker.h"

static struct nat031_state nat031_st;

extern void nat031_stub(void);

int nat031_install(uintptr_t win_base, uint64_t virt_base, uint32_t *bad)
{
	return nat031_prepare(&nat031_st, win_base, virt_base, (uint64_t)(uintptr_t)nat031_stub, bad);
}

uint64_t nat031_ckpt_c(const struct nat031_frame *f)
{
	struct mk_ckpt r;
	struct nat031_decision d;

	/* Read before anything else here can change them; the kernel's stop path has already cleared SCTLR_EL1.M. */
	__asm__ volatile("mrs %0, sctlr_el1" : "=r"(r.sctlr));
	__asm__ volatile("mrs %0, ttbr1_el1" : "=r"(r.ttbr1));
	__asm__ volatile("mrs %0, tcr_el1" : "=r"(r.tcr));
	__asm__ volatile("mrs %0, vbar_el1" : "=r"(r.vbar));
	r.x2 = f->x[2];
	r.x3 = f->x[3];
	r.esr = f->x[3];	/* the early-exception report: x3 = ESR, x4 = ELR, x5 = FAR */
	r.elr = f->x[4];
	r.far = f->x[5];
	nat031_decide(&nat031_st, r.x2, r.x3, &d);
	r.mask = nat031_st.mask;
	r.arrivals = nat031_st.arrivals;
	if (d.action == NAT031_RESUME) {
		mk_ckpt_pass(&r);
		nat031_set_next(&nat031_st, d.next);
		return d.resume_pa;
	}
	mk_ckpt_hold(&r);
}
#endif
