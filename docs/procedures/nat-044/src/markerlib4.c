/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-044: the reset glue of loader-diag-reset. This translation unit is NAT-022's markerlib.c as patched by
 * patch_loader4.py (a deadline poll in mk_wait_tenths and a report in mk_hold's loop) plus the routines below, which need
 * markerlib.c's static helpers (mk_draw, show, ld_k) and therefore live in the same unit. The build compiles this file instead
 * of markerlib.c. */
#include "markerlib.c"
#include "reset44.h"

struct nat044 g_nat044;

/* Entry snapshot of the three words the vendor reboot path uses (NAT-042), and removal of a leftover Download request. A
 * request left by an earlier run would turn the next ordinary restart into Download Mode if this run died before its own
 * end-of-run path. Only INFORM3 is written, with a read-back, as recovery_guard() already does for the recovery reason. */
void nat044_snapshot(volatile uint32_t *pmu)
{
	struct s5e_reset_snapshot s;
	s5e_reset_snapshot(pmu, &s);
	g_nat044.pmu = pmu;
	g_nat044.inform2_0 = s.inform2;
	g_nat044.inform3_0 = s.inform3;
	g_nat044.cmd_0 = s.cmd;
	if (s.inform3 == S5E_REASON_DOWNLOAD || s.inform3 == S5E_REASON_BOOTLOADER) {
		pmu[S5E_PMU_INFORM3 / 4u] = S5E_REASON_NORMAL;
		NAT044_BARRIER();
		g_nat044.cleared = pmu[S5E_PMU_INFORM3 / 4u] == S5E_REASON_NORMAL ? 1u : 2u;
	}
}

/* Called once the loader's watchdog is armed: the deadline is measured from here, so it is always earlier than the WDT. */
void nat044_arm(void)
{
#if NAT044_DEADLINE_S > 0
	g_nat044.t0 = mk_cnt();
	g_nat044.deadline_ticks = mk_freq() * (uint64_t)NAT044_DEADLINE_S;
	g_nat044.armed = g_nat044.pmu != 0;
#endif
}

static uint32_t nat044_status(void)
{
	const struct nat044 *n = &g_nat044;
	return (n->rc & NAT044_ST_RC_MASK) | (n->fired ? NAT044_ST_FIRED : 0) | (n->armed ? NAT044_ST_ARMED : 0) |
	       (n->cleared == 1 ? NAT044_ST_CLEARED : 0) | (n->cleared == 2 ? NAT044_ST_CLEARFAIL : 0);
}

/* Polled from every wait loop of the marker library (mk_wait_tenths), so the deadline is met to within one draw. The reset is
 * attempted once. s5e_reset_to() does not return when the trigger was written; when it returns the reason was refused or a
 * register did not read back, nothing was triggered, and the watchdog stays the failsafe. */
static void nat044_tick(void)
{
	if (!g_nat044.armed)
		return;
	if (mk_cnt() - g_nat044.t0 < g_nat044.deadline_ticks)
		return;
	g_nat044.armed = 0;
	g_nat044.fired = 1;
	mk_draw(mk_frame(MK_STAGE, 0, MK_ST_RESET), 0, 1);
	g_nat044.rc = (uint32_t)(-s5e_reset_to(g_nat044.pmu, NAT044_REASON)) & NAT044_ST_RC_MASK;
	mk_draw(mk_frame(MK_RST, 7, nat044_status()), 0, 1);	/* only reached when nothing was triggered */
}

/* The entry snapshot and the state of the deadline, shown from the hold loop of mk_hold (about 9.5 s per round). */
static void nat044_show(uint32_t *prev, struct mk_kick *k)
{
	const struct nat044 *n = &g_nat044;
	show(prev, mk_frame(MK_RST, 0, n->inform3_0 >> 16), k);
	show(prev, mk_frame(MK_RST, 1, n->inform3_0 & 0xffffu), k);
	show(prev, mk_frame(MK_RST, 2, n->inform2_0 >> 16), k);
	show(prev, mk_frame(MK_RST, 3, n->inform2_0 & 0xffffu), k);
	show(prev, mk_frame(MK_RST, 4, n->cmd_0 >> 16), k);
	show(prev, mk_frame(MK_RST, 5, n->cmd_0 & 0xffffu), k);
	show(prev, mk_frame(MK_RST, 6, nat044_status()), k);
}
