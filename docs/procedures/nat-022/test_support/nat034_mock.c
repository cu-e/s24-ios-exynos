/* Test double for the marker routines of the NAT-034 stub: records what the stub passes in, field by field (no memcpy in
 * a freestanding link). mock_log[i] = x2 x3 sctlr ttbr1 tcr vbar esr elr far mask|arrivals<<32, 10 words each;
 * mock_c2 = x0 x1 x5 ttbr0 of the last C-stop report; mock_held = 1 after mk_ckpt_hold, 2 after mk_ckpt2_hold. */
#include "marker.h"
volatile uint64_t mock_log[8][10];
volatile uint64_t mock_c2[4];
volatile uint32_t mock_n, mock_held;
static void rec(const struct mk_ckpt *r)
{
	volatile uint64_t *o = mock_log[mock_n++ & 7];
	o[0] = r->x2; o[1] = r->x3; o[2] = r->sctlr; o[3] = r->ttbr1; o[4] = r->tcr; o[5] = r->vbar;
	o[6] = r->esr; o[7] = r->elr; o[8] = r->far; o[9] = (uint64_t)r->mask | (uint64_t)r->arrivals << 32;
}
void mk_ckpt_pass(const struct mk_ckpt *r) { rec(r); }
__attribute__((noreturn)) void mk_ckpt_hold(const struct mk_ckpt *r) { rec(r); mock_held = 1; for (;;) { } }
__attribute__((noreturn)) void mk_ckpt2_hold(const struct mk_ckpt *r, const struct mk_ckpt2 *c)
{
	rec(r);
	mock_c2[0] = c->x0; mock_c2[1] = c->x1; mock_c2[2] = c->x5; mock_c2[3] = c->ttbr0;
	mock_held = 2;
	for (;;) { }
}
