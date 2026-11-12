// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-079 host fixture: the NAT-076 host model (simulated DWC3 controller, non-coherent cache, USB host) in one translation unit with the
 * exact text of the loader's receive phase (src/nat079_impl.h). The loader's own collaborators are replaced by the smallest stand-ins:
 *
 *   nat047_poll()   one engine poll; the first call of a run also runs the registered host callback (the real tools/ios/root_send.py sender,
 *                   which drives the model's own USB host side and polls the engine through it)
 *   nat044_tick()   counts the rounds (the NAT-044 pet / deadline behaviour is tested on the compiled loader in test_nat079.py)
 *   mk_cnt()/mk_freq()   a fake counter: 1000 Hz, advancing by `step` ticks per read, so a cap of C seconds is C*1000/step rounds
 *   N79_BARRIER()   a full barrier, plus an optional stuck-at fault: one 64-bit word is OR-ed with a mask after every barrier, which makes
 *                   the CPU self-test read back a wrong value (what a dead reserve would do)
 *
 * Nothing here is the S24: the model is a reading of the DWC3 documentation and the CPU stores are plain stores of the host.
 * Build: tests build this with -I engine -I model -I src -I <generated nat079.h dir> (see test_e2e79.py).
 */
#include "model.c"
#include "nat079.h"

static int fx_up_flag = 1;
static uint64_t fx_now, fx_step = 1, fx_tick_calls, fx_poll_calls;
static void (*fx_cb)(void);
static volatile uint64_t *fx_stuck_addr;
static uint64_t fx_stuck_mask;

static void fx_barrier(void)
{
	__sync_synchronize();
	if (fx_stuck_addr)
		*fx_stuck_addr |= fx_stuck_mask;
}

static uint64_t mk_cnt(void)
{
	uint64_t v = fx_now;

	fx_now += fx_step;
	return v;
}

static uint64_t mk_freq(void) { return 1000; }
static void nat044_tick(void) { fx_tick_calls++; }

static void nat047_poll(void)
{
	void (*cb)(void) = fx_cb;

	fx_poll_calls++;
	if (cb) {
		fx_cb = 0;
		cb();
	}
	usbmon_poll(g_m);
}

#define N79_ENGINE()	(g_m)
#define N79_UP()	(fx_up_flag)
#define N79_BARRIER()	fx_barrier()
#include "nat079_impl.h"

void fx_reset(uint64_t step)
{
	fx_up_flag = 1;
	fx_now = 1000000;
	fx_step = step;
	fx_tick_calls = fx_poll_calls = 0;
	fx_cb = 0;
	fx_stuck_addr = 0;
	fx_stuck_mask = 0;
}

void fx_set_cb(void (*cb)(void)) { fx_cb = cb; }
void fx_set_up(int up) { fx_up_flag = up; }
void fx_set_stuck(uint64_t addr, uint64_t mask)
{
	fx_stuck_addr = (volatile uint64_t *)(uintptr_t)addr;
	fx_stuck_mask = mask;
}

uint64_t fx_window_base(void) { return (uint64_t)(uintptr_t)win; }
uint64_t fx_window_size(void) { return win_size; }
uint64_t fx_ticks(void) { return fx_tick_calls; }
uint64_t fx_polls(void) { return fx_poll_calls; }
uint32_t fx_result_size(void) { return sizeof(struct nat079_result); }
uint64_t fx_rx_dest(void) { return (uint64_t)(uintptr_t)g_m->rx_dest; }
uint64_t fx_rx_size(void) { return g_m->rx_size; }

int fx_receive(uint64_t pa, uint64_t bytes, struct nat079_result *r)
{
	return nat079_receive_root((uint64_t)(uintptr_t)win, (uint64_t)(uintptr_t)win + win_size, pa, bytes, r);
}

/* The argument rules with every argument free: the aarch64 loader build specialises nat079_check_args() to its one call site (the engine's
 * own address range), so the boundaries of that comparison are exercised here, through a volatile pointer that defeats the specialisation. */
int fx_check_args(uint64_t win_base, uint64_t mem_end, uint64_t pa, uint64_t bytes, uint64_t self_lo, uint64_t self_hi)
{
	int (*volatile f)(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t) = nat079_check_args;

	return f(win_base, mem_end, pa, bytes, self_lo, self_hi);
}
