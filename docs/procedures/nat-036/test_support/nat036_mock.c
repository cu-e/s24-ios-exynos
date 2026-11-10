/* Test double for the marker routines of the NAT-036 stub: records what the stub passes in, field by field (no memcpy in a
 * freestanding link). mock_log[i] is one record of 16 words per mk_ckpt3_pass / mk_ckpt3_hold call:
 *   x2 x3 sctlr ttbr1 tcr vbar esr elr far sp x0 x1 kttbr0 mask|arrivals<<32 last|nstops<<32 kind
 * kind = 1 for a pass, 2 for the hold. mock_held = 1 after mk_ckpt3_hold. */
#include "marker3.h"
volatile uint64_t mock_log[32][16];
volatile uint32_t mock_n, mock_held;
static void rec(const struct mk_ckpt3 *r, uint64_t kind)
{
	volatile uint64_t *o = mock_log[mock_n++ & 31];
	o[0] = r->x2; o[1] = r->x3; o[2] = r->sctlr; o[3] = r->ttbr1; o[4] = r->tcr; o[5] = r->vbar;
	o[6] = r->esr; o[7] = r->elr; o[8] = r->far; o[9] = r->sp; o[10] = r->x0; o[11] = r->x1; o[12] = r->kttbr0;
	o[13] = (uint64_t)r->mask | (uint64_t)r->arrivals << 32;
	o[14] = (uint64_t)r->last | (uint64_t)r->nstops << 32;
	o[15] = kind;
}
void mk_ckpt3_pass(const struct mk_ckpt3 *r) { rec(r, 1); }
__attribute__((noreturn)) void mk_ckpt3_hold(const struct mk_ckpt3 *r) { rec(r, 2); mock_held = 1; for (;;) { } }
