/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-079: the part of nat079.h that does not depend on the build parameters (generated nat079.h = a parameter block + this file). */
#ifndef NAT079_FIXED_H
#define NAT079_FIXED_H
#include <stdint.h>

#define NAT079_HOLD_BYTES	512u		/* placeholder destination of the engine until the layout is known: one USB packet */
#define NAT079_PAGE		16384ull	/* the kernel's page size once memSize > 1 GiB; the reserve is a whole number of pages */
#define NAT079_PROBES		8u		/* pages the self-test touches */
#define NAT079_WORDS		16u		/* 64-bit words written per probed page */
#define NAT079_LINE_MAX		112u		/* progress line buffer: the longest line (four 20-digit numbers) is 109 bytes */

/* nat079_receive_root() results (also struct nat079_result.status) */
#define NAT079_RUNNING		(-1)		/* internal: keep looping */
#define NAT079_DONE		0		/* every byte committed: rx_bytes == rx_committed == bytes */
#define NAT079_NO_ENGINE	1		/* the USB engine never came up (ladder stop, no cable irrelevant): nothing was attempted */
#define NAT079_NOT_PRESENT	2		/* the engine has no bulk-OUT endpoint (built without rx_dest) */
#define NAT079_BAD_ARGS		3		/* alignment, size or range refused (including the engine's own memory inside the range) */
#define NAT079_PREMATURE	4		/* the host sent before the destination was real */
#define NAT079_SELFTEST		5		/* the CPU could not write/read back the reserve: RX_BEGIN stays refused */
#define NAT079_TIMEOUT		6		/* the cap passed before every byte was committed */
#define NAT079_ENGINE_DOWN	7		/* nat047_fault() took the engine out of service */
#define NAT079_INCONSISTENT	8		/* all bytes committed but the engine's own counters disagree (a defect) */

struct nat079_result {
	uint64_t pa, bytes;			/* the range the phase was given */
	uint64_t committed, rx_bytes;		/* engine: bytes committed in order / bytes counted */
	uint64_t trbs, errors, resets, dups, gaps, rejects, aborts;
	uint64_t last_sum;			/* engine checksum of the last committed chunk */
	uint64_t elapsed_ticks, freq;		/* receive loop time in counter ticks and the counter frequency */
	uint64_t selftest_bad_pa;		/* address that read back wrong, 0 when the self-test passed or did not run */
	int32_t status;				/* NAT079_* */
	int32_t pad;
};

int nat079_receive_root(uint64_t win_base, uint64_t mem_end, uint64_t pa, uint64_t bytes, struct nat079_result *r);
#endif
