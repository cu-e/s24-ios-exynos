/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-052: the code behind glue52.h. Included by markerlib52.c after marker3.h, inside its translation unit, so it can use
 * markerlib47.c's n47_* formatters and g_nat047 and markerlib.c's mk_wait_tenths / mk_kick / ld_k. Only for MK_LOADER builds
 * with MK_XNU_CKPT; the loader is linked at 0 and holds no pointer in initialised static data (nothing here does). */
#if MK_LOADER && MK_XNU_CKPT

#ifndef NAT052_SERVICE_TENTHS
#define NAT052_SERVICE_TENTHS	3u	/* 0.3 s per pass (the video-only image dwelt 1.2 s so a camera could read the frame) */
#endif
#define NAT052_NOTE_MAX		352u

/* Longest line nat052_note_stop can build, so the buffer size is a checked fact: the labels and the widest value of each
 * field ("0x" + 16 hex digits = 18; a 32-bit counter prints at most 10 digits and a sign = 11). */
#define N52_LABELS	(5 + 5 + 6 + 4 + 4 + 6 + 7 + 4 + 8 + 6 + 8 + 5 + 5 + 5)	/* CK n=, arr, last, x2, x3, mask, sctlr, sp, kttbr0, vbar, setups, esr, elr, far */
#define N52_VALUES	(11 * 4 + 18 * 8 + 10 + 18 * 3)
_Static_assert(N52_LABELS + N52_VALUES < NAT052_NOTE_MAX, "NAT-052: the stop note can overflow its buffer");

static uint64_t g_nat052_loader_vbar;
static uint32_t g_nat052_notes, g_nat052_last_setups;

void nat052_capture_vbar(void)
{
	uint64_t v;

	__asm__ volatile("mrs %0, vbar_el1" : "=r"(v));
	g_nat052_loader_vbar = v;
}

uint64_t nat052_vbar_enter(void)
{
	uint64_t cur;

	__asm__ volatile("mrs %0, vbar_el1" : "=r"(cur));
	if (g_nat052_loader_vbar && cur != g_nat052_loader_vbar)
		__asm__ volatile("msr vbar_el1, %0\n\tisb" :: "r"(g_nat052_loader_vbar) : "memory");
	return cur;
}

void nat052_vbar_leave(uint64_t saved)
{
	uint64_t cur;

	__asm__ volatile("mrs %0, vbar_el1" : "=r"(cur));
	if (cur != saved)
		__asm__ volatile("msr vbar_el1, %0\n\tisb" :: "r"(saved) : "memory");
}

/* Field order is the contract with decode52.py. esr/elr/far follow only for an early exception (x2 == 1). */
void nat052_note_stop(const struct mk_ckpt3 *r)
{
	struct nat047 *n = &g_nat047;
	char b[NAT052_NOTE_MAX];
	char *p = b;
	uint32_t setups;

	g_nat052_notes++;
	if (!n->up)
		return;
	setups = n->m.setups;
	p = n47_s(p, "CK n=");
	p = n47_d(p, (int32_t)g_nat052_notes);
	p = n47_s(p, " arr=");
	p = n47_d(p, (int32_t)r->arrivals);
	p = n47_s(p, " last=");
	p = n47_d(p, (int32_t)r->last);
	p = n47_s(p, " x2=");
	p = n47_x(p, r->x2);
	p = n47_s(p, " x3=");
	p = n47_x(p, r->x3);
	p = n47_s(p, " mask=");
	p = n47_x(p, r->mask);
	p = n47_s(p, " sctlr=");
	p = n47_x(p, r->sctlr);
	p = n47_s(p, " sp=");
	p = n47_x(p, r->sp);
	p = n47_s(p, " kttbr0=");
	p = n47_x(p, r->kttbr0);
	p = n47_s(p, " vbar=");
	p = n47_x(p, r->vbar);
	p = n47_s(p, " setups=");
	p = n47_d(p, (int32_t)(setups - g_nat052_last_setups));
	g_nat052_last_setups = setups;
	if ((r->x2 & 0xff) == 1) {
		p = n47_s(p, " esr=");
		p = n47_x(p, r->esr);
		p = n47_s(p, " elr=");
		p = n47_x(p, r->elr);
		p = n47_s(p, " far=");
		p = n47_x(p, r->far);
	}
	n47_text(b, p);
}

void nat052_service(void)
{
#if MK_TRIG
	mk_kick(&ld_k);
#endif
	mk_wait_tenths(NAT052_SERVICE_TENTHS);
}
#endif
