/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-036: the loader side of resumable C-checkpoint stops (loader-diag-xnu-ckpt3).
 *
 * Run 009 (decision 0017) stopped the payload kernel at the first C checkpoint (11) and held there. This module lets
 * the return stub give the kernel back from a C stop, so that it can be stopped at a list of C checkpoints in turn
 * (checkpoint program order 10, 11, 30..35, 12, 40..44, 13..16) and held at the last one. The resume sequence is the
 * one NAT-035 specified and checked in the instruction-level model (README section 2); ckpt3_stub.S is its assembly.
 *
 * Arrivals at the stub:
 *   * assembly checkpoint 1..4 (x2 = 2, x3 = n, MMU off): resume at the site's continuation with slot[2] = n + 1, exactly as
 *     NAT-031. The only change to the report is one frame per pass instead of two.
 *   * assembly checkpoint 5: capture the kernel's TTBR0 (MMU off, the value the kernel set), resume at the start of the
 *     kernel's MMU-enable block (site 5 minus 28 bytes) with slot[2] = the first C stop, exactly as NAT-034.
 *   * C checkpoint n in the list (x2 = 2, x3 = n, MMU ON with loader_jump's private TTBR0): clear loader_return_entered by
 *     physical address, store the next stop into slot[2], and return into the kernel's own loader_jump epilogue through its
 *     _set_mmu_ttb. The last stop in the list holds.
 *   * anything else holds and reports what it was given (the old report plus the kernel's SP, x0, x1).
 * C resume is only ever done for an arrival with SCTLR_EL1.M set (a C arrival) and a captured kernel TTBR0; every other
 * case holds. Stops after the kernel's arm_vm_init (checkpoint 17 on) are refused in the list: the kernel's TTBR0 changes
 * there and the stub only has the value from checkpoint 5.
 *
 * The decision code builds on the host (NAT031_HOST) and is run there. The aarch64 code is run in the NAT-030/033/035
 * instruction-level model against the real payload bytes (test_nat036.py); nothing here has run on the phone. */
#ifndef NAT036_CKPT3_H
#define NAT036_CKPT3_H
#include "ckpt2.h"
#include "marker3.h"

/* The payload's own addresses (artifacts/nat-020/build-003/payload.bin; NAT-029, NAT-035). */
#define NAT036_JUMP_VA		0xfffffff00744f1ccULL	/* loader_jump */
#define NAT036_JUMP_WORDS	27u			/* its first 27 instructions: entry .. the store that sets loader_return_entered */
#define NAT036_JUMP_EPILOGUE	0x4cu			/* loader_jump + 0x4c: ldp x29, x30, [sp, #0x30]; add sp, sp, #0x40; ret */
#define NAT036_SETTTB_VA	0xfffffff0074428bcULL	/* _set_mmu_ttb: dsb ish; msr ttbr0_el1, x0; isb; ret */
#define NAT036_SETTTB_WORDS	4u
#define NAT036_FLAG_VA		0xfffffff007d77009ULL	/* loader_return_entered (a byte; loader_jump sets it, tests it, returns early) */

#define NAT036_MAX_STOPS	24u
#define NAT036_ORDER_LEN	18u
#define NAT036_LAST_STOP	16u	/* the last checkpoint in program order before arm_vm_init */

/* Extra bits of struct nat031_state.mask / MK_CK_MASK. */
#define NAT036_MASK_BAD_TTBR0	(1u << 12)	/* the TTBR0 read at checkpoint 5 is not a plausible table base: hold, nothing resumed */
#define NAT036_MASK_FINAL	(1u << 13)	/* the last stop of the list was reached (the intended hold) */
#define NAT036_MASK_BAD_STATE	(1u << 14)	/* a C stop arrived in a state the resume does not support: hold */

enum nat036_rc {
	NAT036_OK = 0,
	/* NAT031_SLOT_BAD = 1, NAT031_SITE_BAD = 2 (with *bad = the failing site) */
	NAT036_LIST_BAD = 3,	/* the stop list is empty, too long, not in program order, or has a checkpoint after 16 */
	NAT036_BLOCK_BAD = 4,	/* the stub's code is not inside one 2 MiB block (loader_jump maps one block around the stub) */
	NAT036_JUMP_BAD = 5,	/* the kernel's loader_jump is not the function NAT-035 analysed */
	NAT036_SETTTB_BAD = 6,	/* the kernel's _set_mmu_ttb is not the four instructions NAT-035 relies on */
	NAT036_FLAG_BAD = 7	/* loader_return_entered is not zero in the kernel copy */
};

enum nat036_action { NAT036_RESUME_ASM = 1, NAT036_RESUME_C = 2, NAT036_HOLD = 3 };

struct nat036_decision {
	uint32_t action;
	uint32_t next;		/* RESUME_*: the checkpoint number to store in slot[2] */
	uint32_t final;		/* HOLD: 1 when this is the last stop of the list (the intended hold) */
	uint64_t resume_pa;	/* RESUME_ASM: where the kernel continues */
};

struct nat036_state {
	struct nat031_state s;	/* slot_pa, pa_minus_va, expect (the checkpoint stopped at next), mask, arrivals */
	const uint8_t *stops;	/* the C stops after checkpoint 5, in program order */
	uint32_t nstops;
	uint32_t idx;		/* index in stops of the stop expected next (valid once checkpoint 5 is past) */
	uint32_t last;		/* number of the last checkpoint reached (0 = none) */
	uint32_t pad;
	uint64_t kernel_ttbr0;	/* TTBR0_EL1 read at the checkpoint-5 stop; 0 = not captured */
	uint64_t flag_pa;	/* PA of loader_return_entered */
};

/* What a C resume hands to the assembly tail: the kernel's TTBR0 and the two kernel addresses it branches through. */
struct nat036_cres {
	uint64_t ttbr0;		/* x0 for _set_mmu_ttb */
	uint64_t ret;		/* x30: loader_jump + NAT036_JUMP_EPILOGUE */
	uint64_t gadget;	/* the branch target: _set_mmu_ttb */
};

/* The register pair nat036_ckpt_c returns to the stub: mode 0 = branch to v (assembly resume, registers restored from the
 * frame); mode 1 = v is a struct nat036_cres, the C resume of ckpt3_stub.S. */
struct nat036_ret {
	uint64_t v;
	uint64_t mode;
};

extern const uint8_t nat036_order[NAT036_ORDER_LEN];	/* 10, 11, 30..35, 12, 40..44, 13, 14, 15, 16 */
extern const uint32_t nat036_jump_words[NAT036_JUMP_WORDS];
extern const uint32_t nat036_setttb_words[NAT036_SETTTB_WORDS];

/* 1 when stops[0..n) is a non-empty list of at most NAT036_MAX_STOPS checkpoints of nat036_order in strictly increasing
 * program order. */
int nat036_list_ok(const uint8_t *stops, uint32_t n);

/* nat031_check (slot and the five sites), then the checks the C resume adds: the list, the stub block, loader_jump,
 * _set_mmu_ttb and the flag byte, all read from the copied kernel image (win_base = the PA of virt_base). Reads only;
 * NAT036_OK or an enum nat036_rc (nat031's codes keep their meaning, *bad as there). */
int nat036_check(uintptr_t win_base, uint64_t virt_base, uint64_t stub_pa, uint64_t stub_end_pa,
    const uint8_t *stops, uint32_t nstops, uint32_t *bad);

/* nat036_check, then fills the slot like nat031_prepare (slot[3], slot[1] = stub_pa, last slot[2] = 1). Nothing is written
 * when a check fails. Initialises *st. */
int nat036_prepare(struct nat036_state *st, uintptr_t win_base, uint64_t virt_base, uint64_t stub_pa, uint64_t stub_end_pa,
    const uint8_t *stops, uint32_t nstops, uint32_t *bad);

/* What the stub does for an arrival with (x2, x3), the arrival SCTLR_EL1 and the TTBR0_EL1 read on arrival. Updates st. */
void nat036_decide(struct nat036_state *st, uint64_t x2, uint64_t x3, uint64_t sctlr, uint64_t ttbr0, struct nat036_decision *d);

/* Stores next into slot[2] with the cache maintenance NAT-032 requires (the kernel may hold the line): clean+invalidate,
 * store, clean+invalidate, each followed by dsb sy. */
void nat036_set_next(const struct nat031_state *st, uint32_t next);

/* Clears loader_return_entered by physical address with the same cache maintenance (MMU off). */
void nat036_clear_flag(uint64_t flag_pa);

/* Fills what the report shows from the arrival frame (x2/x3 = the kernel's reason and code, x0, x1, x4, x5, the arrival
 * SCTLR_EL1 in the x11 slot, SP), the three system registers the stub reads (TTBR1_EL1, TCR_EL1, VBAR_EL1) and the state
 * after nat036_decide. Pure: the host tests call it on crafted frames. */
void nat036_report(struct mk_ckpt3 *r, const struct nat036_state *st, const struct nat031_frame *f, uint64_t ttbr1, uint64_t tcr,
    uint64_t vbar);

#ifndef NAT031_HOST
/* Loader build only. */
int nat036_install(uintptr_t win_base, uint64_t virt_base, uint32_t *bad);
const char *nat036_msg(int rc, uint32_t bad);
struct nat036_ret nat036_ckpt_c(const struct nat031_frame *f);
void nat036_stub(void);
#endif
#endif
