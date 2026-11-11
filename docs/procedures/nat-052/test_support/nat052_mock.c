/* Test double for the NAT-052 hooks and the marker routines of the NAT-036 stub, for the model run of the patched ckpt3.c.
 * m52_ev[i] = {kind, arg}: kind 1 = nat052_vbar_enter (arg = the token it returned), 2 = nat052_vbar_leave (arg = what it was given),
 * 3 = nat052_note_stop (arg = last | arrivals << 32), 4 = mk_ckpt3_pass (arg = last), 5 = mk_ckpt3_hold (arg = last).
 * The token is unique per enter, so a leave that is given anything but the token of its own arrival is visible. */
#include "marker3.h"
volatile uint64_t m52_ev[256][2];
volatile uint32_t m52_n, m52_enters, mock_held;
static void ev(uint64_t kind, uint64_t arg)
{
	volatile uint64_t *o = m52_ev[m52_n++ & 255];
	o[0] = kind;
	o[1] = arg;
}
uint64_t nat052_vbar_enter(void)
{
	uint64_t tok = 0xA0000u + ++m52_enters;
	ev(1, tok);
	return tok;
}
void nat052_vbar_leave(uint64_t saved) { ev(2, saved); }
void nat052_note_stop(const struct mk_ckpt3 *r) { ev(3, (uint64_t)r->last | (uint64_t)r->arrivals << 32); }
void mk_ckpt3_pass(const struct mk_ckpt3 *r) { ev(4, r->last); }
__attribute__((noreturn)) void mk_ckpt3_hold(const struct mk_ckpt3 *r) { ev(5, r->last); mock_held = 1; for (;;) { } }
