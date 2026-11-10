/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-034: the loader side of the first run past assembly checkpoint 5 (loader-diag-xnu-ckpt2).
 *
 * Decision 0016 stopped the payload kernel at assembly checkpoint 5. This adds one step on top of ckpt.h:
 * at checkpoint 5 the stub does not hold but resumes the kernel at the start of its own MMU-enable block
 * (site 5 minus 28 bytes, NAT-032) with slot[2] = 11, and the next stop is the first C checkpoint,
 * loader_checkpoint(11) in arm_init after PE_init_platform, which is final (a hold; nothing is resumed
 * from a C checkpoint). Checkpoints 1..4 resume exactly as in ckpt.c.
 *
 * Arrival at the C stop differs from every earlier one: loader_jump branches to the stub with the MMU and the
 * caches ON (its private TTBR0 maps only the 2 MiB block that holds the stub), x0 = loader_log PA, x1 = its
 * length, x2 = 2, x3 = 11, x5 = the stub. The prologue of nat034_stub (ckpt2_stub.S) clears SCTLR_EL1.M and C
 * before any memory access and saves the arrival SCTLR_EL1 in the frame (x11 slot), so the report can tell
 * which arrival it was.
 *
 * nothing in this file changes the object code of an earlier image: ckpt.c is only guarded so that the
 * NAT-031 loader block is left out of the NAT-034 image, and the earlier images do not define NAT034_IMAGE. */
#ifndef NAT034_CKPT2_H
#define NAT034_CKPT2_H
#include "ckpt.h"

#define NAT034_C11		11u			/* the C checkpoint number the final stop is made at */
#define NAT034_RESUME_BACK	28u			/* resume at site 5 minus 28 bytes: the kernel's MMU-enable block */
#define NAT034_MASK_C11		(1u << 11)		/* mask bit: the final C stop was reached */

/* HOLD decisions carry next == NAT034_C11 when the hold is the final C stop (and 0 for every other hold). */

/* nat031_decide extended: checkpoint 5 (expected) resumes at site5 - NAT034_RESUME_BACK with slot[2] = 11; an
 * x2 = 2 / x3 = 11 arrival while the expected checkpoint is 11 holds as the final C stop; everything else is
 * decided by nat031_decide (resume 1..4, hold on the rest, with its masks). Updates st. */
void nat034_decide(struct nat031_state *st, uint64_t x2, uint64_t x3, struct nat031_decision *d);

/* Stores next into slot[2] the way that is safe once the kernel has the line in its data cache (NAT-032):
 * clean+invalidate the line, store, clean+invalidate again, each step followed by dsb sy. */
void nat034_set_next(const struct nat031_state *st, uint32_t next);

#ifndef NAT031_HOST
/* Loader build only. nat034_install = nat031_prepare with the nat034 stub and the loader's state. */
int nat034_install(uintptr_t win_base, uint64_t virt_base, uint32_t *bad);
/* Called by nat034_stub (ckpt2_stub.S) on every arrival; returns the continuation PA, or never returns. */
uint64_t nat034_ckpt_c(const struct nat031_frame *f);
void nat034_stub(void);
#endif
#endif
