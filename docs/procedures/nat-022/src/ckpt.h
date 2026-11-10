/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-031: the loader side of the payload kernel's XNULDRST hook (NAT-029): fill the slot, check the five
 * assembly checkpoint sites, and decide what the return stub does when the kernel stops at one.
 *
 * Everything here that does not touch a system register builds on the host (NAT031_HOST) and is run
 * there on the real payload bytes. The payload is identified by its SHA-256 in the task evidence; the
 * addresses below are those of artifacts/nat-020/build-003/payload.bin and the loader refuses (nothing
 * written, no jump) when the words at those addresses are not the ones NAT-029 read. */
#ifndef NAT031_CKPT_H
#define NAT031_CKPT_H
#include <stdint.h>

#define NAT031_NSITES		5u
#define NAT031_SITE_WORDS	15u	/* the checkpoint macro is 15 instructions; the continuation is the 16th */
#define NAT031_SLOT_VA		0xfffffff00743c7f0ULL

/* Mask bits of struct mk_ckpt.mask / MK_CK_MASK (bit N, 1..5: arrival at assembly checkpoint N, in order). */
#define NAT031_MASK_EXC		(1u << 8)	/* the kernel's early-exception report (x2 = 1) */
#define NAT031_MASK_ORDERLY	(1u << 9)	/* x2 = 0: the kernel says it is done */
#define NAT031_MASK_OTHER	(1u << 10)	/* any other x2, or a checkpoint that is not the expected one */

enum nat031_rc {
	NAT031_OK = 0,
	NAT031_SLOT_BAD = 1,	/* magic missing, slot not three zero words, or not 8-byte aligned */
	NAT031_SITE_BAD = 2	/* a site's instruction words are not the NAT-029 macro (bad = site number) */
};

/* Loader-owned state. Lives in the loader image (outside the kernel window). */
struct nat031_state {
	uint64_t slot_pa;	/* PA of _loader_stub_slot */
	uint64_t pa_minus_va;	/* slot[3]; physical = va + pa_minus_va */
	uint32_t expect;	/* the checkpoint number the kernel should stop at next (1..5) */
	uint32_t mask;		/* arrival mask, see above */
	uint32_t arrivals;	/* number of arrivals at the stub, whatever their reason */
	uint32_t pad;
};

enum nat031_action { NAT031_RESUME = 1, NAT031_HOLD = 2 };

struct nat031_decision {
	uint32_t action;
	uint32_t next;		/* RESUME: checkpoint number to write into slot[2] */
	uint64_t resume_pa;	/* RESUME: where the kernel continues (site + 15 instructions) */
};

/* VA of assembly checkpoint n (1..NAT031_NSITES); 0 for anything else. */
uint64_t nat031_site_va(uint32_t n);

/* Checks the slot and the five sites in the copied kernel image. win_base is the PA the loader copied the
 * image to (physical = win_base + (va - virt_base)). Reads only; *bad = the failing site (0 = the slot). */
int nat031_check(uintptr_t win_base, uint64_t virt_base, uint32_t *bad);

/* nat031_check, then fills the slot: [3] pa_minus_va, [1] stub_pa, last [2] = 1 (the first checkpoint).
 * Nothing is written when the check fails. Initialises *st. All stores are aligned 64-bit stores. */
int nat031_prepare(struct nat031_state *st, uintptr_t win_base, uint64_t virt_base, uint64_t stub_pa, uint32_t *bad);

/* What the return stub does for an arrival with (x2, x3). Updates st (arrivals, mask, expect). */
void nat031_decide(struct nat031_state *st, uint64_t x2, uint64_t x3, struct nat031_decision *d);

/* Stores next into slot[2] and, outside the host build, cleans and invalidates that line (the kernel may
 * hold it in its data cache after the MMU is on). */
void nat031_set_next(const struct nat031_state *st, uint32_t next);

/* Register frame the stub saves on the loader's stack: x0..x30, then the kernel's SP. */
struct nat031_frame {
	uint64_t x[31];
	uint64_t sp;
};

#ifndef NAT031_HOST
/* Loader build only. nat031_install = nat031_prepare with the real stub address and the loader's state. */
int nat031_install(uintptr_t win_base, uint64_t virt_base, uint32_t *bad);
/* Called by nat031_stub (ckpt_stub.S) on every arrival; returns the continuation PA, or never returns. */
uint64_t nat031_ckpt_c(const struct nat031_frame *f);
void nat031_stub(void);
#endif
#endif
