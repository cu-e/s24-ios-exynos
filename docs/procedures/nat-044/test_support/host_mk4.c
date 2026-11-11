/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-only harness for the NAT-044 reset glue. It is NAT-022's host_mk.c (the fake DECON0 and the draw hook, included with its
 * main renamed) plus a PMU register model and one scenario that runs the real mk_hold (markerlib.c as patched by
 * patch_loader4.py) with the real nat044_snapshot / nat044_arm / nat044_tick / nat044_show (markerlib4.c) and the unmodified
 * NAT-042 module (reset_host.c). Time: the host build skips waits, so every completed draw advances the counter by one dwell
 * (1.2 s), which is what a draw followed by its wait costs on the phone.
 *
 *   host_mk4 reset44 MAXDRAWS OUTFILE INFORM3 INFORM2 CMD [noarm] [nosnap] [fail2|fail3|failc]
 * stdout is the event log, in order: "DRAW %08x" (a completed draw), "PMUR %x %08x", "PMUW %x %08x", "BARRIER", "WAIT" (the
 * reset: the process ends), and once "SNAPSHOT %08x" = INFORM3 after nat044_snapshot (its clearing store is not a module access).
 * fail2/fail3/failc make the first read of INFORM2 / INFORM3 / reboot-cmd after the loader stored to it differ from the stored value. */
#define main host_mk_main
#define mk_host_drawn host_mk_drawn_orig
#include "host_mk.c"
#undef main
#undef mk_host_drawn

#include "reset44.h"

extern void nat044_snapshot(volatile uint32_t *pmu);
extern void nat044_arm(void);

static uint32_t pmu_mem[0x4000 / 4];
static int fail_off = -1, fail_active;
static uint8_t written[0x4000 / 4];

void mk_host_drawn(uint32_t frame)
{
	mk_host_cnt += MK_FREQ_FALLBACK / 10 * MK_DWELL_TENTHS;
	host_mk_drawn_orig(frame);
}

uint32_t host_pmu_r(volatile const uint32_t *a)
{
	uint32_t off = (uint32_t)((const uint32_t *)a - pmu_mem) * 4u, v = pmu_mem[off / 4];
	if (fail_active && (int)off == fail_off && written[off / 4])
		v ^= 1u;	/* a read after a store of this register that does not match what was stored */
	printf("PMUR %x %08x\n", off, v);
	return v;
}

void host_pmu_w(volatile uint32_t *a, uint32_t v)
{
	uint32_t off = (uint32_t)((uint32_t *)a - pmu_mem) * 4u;
	printf("PMUW %x %08x\n", off, v);
	pmu_mem[off / 4] = v;
	written[off / 4] = 1;
}

void host_pmu_barrier(void)
{
	printf("BARRIER\n");
}

void host_pmu_wait(void)
{
	printf("WAIT\n");
	fflush(stdout);
	exit(0);
}

int main(int argc, char **argv)
{
	if (argc >= 7 && !strcmp(argv[1], "reset44")) {
		int arm = 1, nosnap = 0;

		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = 0x113; fake_tc = 0x3063;
		pmu_mem[S5E_PMU_INFORM3 / 4] = (uint32_t)strtoul(argv[4], 0, 0);
		pmu_mem[S5E_PMU_INFORM2 / 4] = (uint32_t)strtoul(argv[5], 0, 0);
		pmu_mem[S5E_PMU_REBOOT_CMD / 4] = (uint32_t)strtoul(argv[6], 0, 0);
		for (int i = 7; i < argc; i++) {
			if (!strcmp(argv[i], "noarm")) arm = 0;
			if (!strcmp(argv[i], "nosnap")) nosnap = 1;
			if (!strcmp(argv[i], "fail2")) fail_off = S5E_PMU_INFORM2;
			if (!strcmp(argv[i], "fail3")) fail_off = S5E_PMU_INFORM3;
			if (!strcmp(argv[i], "failc")) fail_off = S5E_PMU_REBOOT_CMD;
		}
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		if (!nosnap)
			nat044_snapshot(pmu_mem);
		printf("SNAPSHOT %08x\n", pmu_mem[S5E_PMU_INFORM3 / 4]);	/* INFORM3 after the entry snapshot (it may have cleared a request) */
		fail_active = 1;	/* the entry snapshot is read before any fault is injected */
		if (arm)
			nat044_arm();
		mk_hold(MK_ST_PRE_JUMP, 0);
	}
	return host_mk_main(argc, argv);
}
