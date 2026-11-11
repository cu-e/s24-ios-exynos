/* SPDX-License-Identifier: GPL-2.0-only */
/* Host build of the unmodified NAT-042 reset module against the NAT-044 harness' PMU model: every register access goes through
 * host_pmu_r / host_pmu_w (host_mk4.c), a barrier is only recorded, and the wait after the trigger ends the process (a reset). */
#include <stdint.h>
extern uint32_t host_pmu_r(volatile const uint32_t *a);
extern void host_pmu_w(volatile uint32_t *a, uint32_t v);
extern void host_pmu_barrier(void);
extern void host_pmu_wait(void);
#define S5E_MMIO_R(a)    host_pmu_r((volatile const uint32_t *)(a))
#define S5E_MMIO_W(a, v) host_pmu_w((volatile uint32_t *)(a), (v))
#define S5E_BARRIER()    host_pmu_barrier()
#define S5E_WAIT()       host_pmu_wait()
#include "s5e9945_reset.c"
