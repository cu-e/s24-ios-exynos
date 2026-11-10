/* SPDX-License-Identifier: GPL-2.0-only */
#include "ckpt2.h"

static inline void st64(uintptr_t pa, uint64_t v)
{
	*(volatile uint64_t *)pa = v;
}

void nat034_decide(struct nat031_state *st, uint64_t x2, uint64_t x3, struct nat031_decision *d)
{
	if (x2 == 2 && x3 == 5 && st->expect == 5) {
		st->arrivals++;
		st->mask |= 1u << 5;
		st->expect = NAT034_C11;
		d->action = NAT031_RESUME;
		d->next = NAT034_C11;
		d->resume_pa = nat031_site_va(5) - NAT034_RESUME_BACK + st->pa_minus_va;
		return;
	}
	if (x2 == 2 && x3 == NAT034_C11 && st->expect == NAT034_C11) {
		st->arrivals++;
		st->mask |= NAT034_MASK_C11;
		d->action = NAT031_HOLD;
		d->next = NAT034_C11;
		d->resume_pa = 0;
		return;
	}
	nat031_decide(st, x2, x3, d);
}

void nat034_set_next(const struct nat031_state *st, uint32_t next)
{
#ifndef NAT031_HOST
	__asm__ volatile("dc civac, %0\n\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");
#endif
	st64(st->slot_pa + 16, next);
#ifndef NAT031_HOST
	__asm__ volatile("dsb sy\n\tdc civac, %0\n\tdsb sy" :: "r"(st->slot_pa + 16) : "memory");
#endif
}

#ifndef NAT031_HOST
#include "marker.h"

static struct nat031_state nat034_st;

int nat034_install(uintptr_t win_base, uint64_t virt_base, uint32_t *bad)
{
	return nat031_prepare(&nat034_st, win_base, virt_base, (uint64_t)(uintptr_t)nat034_stub, bad);
}

uint64_t nat034_ckpt_c(const struct nat031_frame *f)
{
	struct mk_ckpt r;
	struct mk_ckpt2 c;
	struct nat031_decision d;

	/* The prologue of the stub has already cleared SCTLR_EL1.M and C when they were set; the value it read before
	 * is in the x11 slot of the frame (the checkpoint macro clobbers x11 anyway, so nothing live is lost there). */
	r.sctlr = f->x[11];
	__asm__ volatile("mrs %0, ttbr1_el1" : "=r"(r.ttbr1));
	__asm__ volatile("mrs %0, tcr_el1" : "=r"(r.tcr));
	__asm__ volatile("mrs %0, vbar_el1" : "=r"(r.vbar));
	__asm__ volatile("mrs %0, ttbr0_el1" : "=r"(c.ttbr0));
	r.x2 = f->x[2];
	r.x3 = f->x[3];
	r.esr = f->x[3];	/* the early-exception report: x3 = ESR, x4 = ELR, x5 = FAR */
	r.elr = f->x[4];
	r.far = f->x[5];
	c.x0 = f->x[0];
	c.x1 = f->x[1];
	c.x5 = f->x[5];
	nat034_decide(&nat034_st, r.x2, r.x3, &d);
	r.mask = nat034_st.mask;
	r.arrivals = nat034_st.arrivals;
	if (d.action == NAT031_RESUME) {
		mk_ckpt_pass(&r);
		if (d.next == NAT034_C11)
			nat034_set_next(&nat034_st, d.next);	/* from checkpoint 5 on the kernel caches the slot line */
		else
			nat031_set_next(&nat034_st, d.next);	/* checkpoints 1..4: exactly as run 008 */
		return d.resume_pa;
	}
	if (d.next == NAT034_C11)
		mk_ckpt2_hold(&r, &c);
	mk_ckpt_hold(&r);
}
#endif
