/* Test double for the marker routines: records what the stub passes in, field by field (no memcpy in a
 * freestanding link). mock_log[i] = x2 x3 sctlr ttbr1 tcr vbar esr elr far mask|arrivals<<32, 10 words each. */
#include "marker.h"
volatile uint64_t mock_log[8][10];
volatile uint32_t mock_n, mock_held;
static void rec(const struct mk_ckpt *r)
{
	volatile uint64_t *o = mock_log[mock_n++ & 7];
	o[0] = r->x2; o[1] = r->x3; o[2] = r->sctlr; o[3] = r->ttbr1; o[4] = r->tcr; o[5] = r->vbar;
	o[6] = r->esr; o[7] = r->elr; o[8] = r->far; o[9] = (uint64_t)r->mask | (uint64_t)r->arrivals << 32;
}
void mk_ckpt_pass(const struct mk_ckpt *r) { rec(r); }
__attribute__((noreturn)) void mk_ckpt_hold(const struct mk_ckpt *r) { rec(r); mock_held = 1; for (;;) { } }
