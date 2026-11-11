/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-052: what the resumable-checkpoint stub (NAT-036) calls so that every stop reaches the host over the NAT-047 USB log
 * engine. Declarations only; the code is glue52_impl.h, which markerlib52.c includes (it needs the static helpers of
 * markerlib47.c / markerlib.c, so it must live in that translation unit).
 *
 * Everything here runs where nat036_ckpt_c runs: SCTLR_EL1.M and C are clear (the stub's prologue cleared them), so every
 * access is by physical address and the engine's registers and DMA block need no mapping. */
#ifndef NAT052_GLUE52_H
#define NAT052_GLUE52_H
#include <stdint.h>

struct mk_ckpt3;

/* loader_main(), right after nat047_bringup(): remember the loader's own VBAR_EL1 (the loader's vectors). */
void nat052_capture_vbar(void);
/* Install the loader's vectors for the time the stub services the engine; returns the VBAR_EL1 found, to give back to
 * nat052_vbar_leave(). With the kernel's vectors (a virtual address) an engine fault would fetch from a bad physical address. */
uint64_t nat052_vbar_enter(void);
void nat052_vbar_leave(uint64_t saved);
/* One TEXT record for this stop ("CK n=... arr=... last=..."); no-op while the engine is not up. */
void nat052_note_stop(const struct mk_ckpt3 *r);
/* The service window of a pass: the DECON0 kick, then NAT052_SERVICE_TENTHS tenths of a second in which the engine and the
 * deadline are polled (mk_wait_tenths). Replaces ld_after_draw() in mk_ckpt3_pass; the final hold keeps its own loop. */
void nat052_service(void);
#endif
