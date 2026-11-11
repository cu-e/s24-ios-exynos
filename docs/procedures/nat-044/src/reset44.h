/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-044: the loader-diag-reset glue. The loader (NAT-022 loader-diag-trig-hold-adt8-aln) is otherwise unchanged; this adds
 * an entry snapshot of the PMU reboot words, a deadline, and a reset into Download Mode through the NAT-042 module. */
#ifndef NAT044_RESET44_H
#define NAT044_RESET44_H
#include <stdint.h>
#include "s5e9945_reset.h"

/* Seconds from the moment the loader's hardware watchdog was armed (guard.c, 83 s) to the reset call. The builder passes it
 * and checks it against the WDT value read out of guard.c; 0 builds an image that never arms the reset (control). There is no
 * default on purpose: a value the build did not state would be a value nobody checked. */
#ifndef NAT044_DEADLINE_S
#error "NAT044_DEADLINE_S must be given by the build"
#endif

/* The reason word written before the trigger: S5E_REASON_DOWNLOAD (0x12345601, primary) or S5E_REASON_BOOTLOADER
 * (0x1234560d, unknown U4). No other value is accepted by the module. Also given by the build. */
#ifndef NAT044_REASON
#error "NAT044_REASON must be given by the build"
#endif

/* The only barrier markerlib4.c needs (after the clearing store of the entry snapshot). */
#if defined(__aarch64__)
#define NAT044_BARRIER() __asm__ volatile("dsb sy" ::: "memory")
#else
#define NAT044_BARRIER() __asm__ volatile("" ::: "memory")	/* host model: the PMU is plain memory */
#endif

/* STATUS frame (kind MK_RST, idx 6) data bits */
#define NAT044_ST_RC_MASK    0x00ffu   /* s5e_reset_to() return code after a refused/failed attempt, 0 otherwise */
#define NAT044_ST_FIRED      0x1000u   /* the deadline passed and the reset call was made */
#define NAT044_ST_ARMED      0x2000u   /* the deadline is armed (WDT armed, PMU window known) */
#define NAT044_ST_CLEARED    0x4000u   /* a leftover Download request in INFORM3 was cleared at entry */
#define NAT044_ST_CLEARFAIL  0x8000u   /* ... and the clear did not read back */

struct nat044 {
	volatile uint32_t *pmu;
	uint64_t t0, deadline_ticks;
	uint32_t armed, fired, rc, cleared;	/* cleared: 0 none, 1 cleared, 2 clear failed */
	uint32_t inform2_0, inform3_0, cmd_0;	/* entry snapshot, taken before anything else touched the PMU */
};
extern struct nat044 g_nat044;

void nat044_snapshot(volatile uint32_t *pmu);	/* guard.c: first thing in recovery_guard() */
void nat044_arm(void);				/* guard.c: right after the watchdog is armed */
#endif
