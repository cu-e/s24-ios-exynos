/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "s5e9945_reset.h"

#if defined(__aarch64__)
#define S5E_BARRIER() __asm__ volatile("dsb sy" ::: "memory")
#define S5E_WAIT()    do { for (;;) __asm__ volatile("wfi"); } while (0)
#else
/* host port: the model overrides both */
#ifndef S5E_BARRIER
#define S5E_BARRIER() __asm__ volatile("" ::: "memory")
#endif
#ifndef S5E_WAIT
#define S5E_WAIT()    do { } while (0)
#endif
#endif

/* Hooks for the host model (every PMU access goes through these); on the target they are plain volatile accesses. */
#ifndef S5E_MMIO_R
#define S5E_MMIO_R(a)    (*(a))
#endif
#ifndef S5E_MMIO_W
#define S5E_MMIO_W(a, v) (*(a) = (v))
#endif

static volatile uint32_t *reg(volatile uint32_t *pmu, uint32_t off) { return pmu + off / 4u; }

void s5e_reset_snapshot(volatile const uint32_t *pmu, struct s5e_reset_snapshot *out)
{
    out->inform2 = S5E_MMIO_R(pmu + S5E_PMU_INFORM2 / 4u);
    out->inform3 = S5E_MMIO_R(pmu + S5E_PMU_INFORM3 / 4u);
    out->cmd     = S5E_MMIO_R(pmu + S5E_PMU_REBOOT_CMD / 4u);
}

uint32_t s5e_reset_mode_for(uint32_t reason)
{
    return reason == S5E_REASON_BOOTLOADER ? S5E_MODE_FASTBOOT : S5E_MODE_NORMAL;
}

int s5e_reset_prepare(volatile uint32_t *pmu, uint32_t reason)
{
    if (reason != S5E_REASON_NORMAL && reason != S5E_REASON_DOWNLOAD && reason != S5E_REASON_BOOTLOADER)
        return S5E_RESET_EREASON;

    /* sec_reboot(): INFORM2 byte 2 = SEC_REBOOT_NORMAL, other bits kept (read-modify-write). */
    uint32_t w2 = (S5E_MMIO_R(reg(pmu, S5E_PMU_INFORM2)) & ~(S5E_INFORM2_BYTE_MASK << S5E_INFORM2_BYTE_SHIFT))
                | (S5E_INFORM2_NORMAL << S5E_INFORM2_BYTE_SHIFT);
    S5E_MMIO_W(reg(pmu, S5E_PMU_INFORM2), w2);
    S5E_BARRIER();
    if (S5E_MMIO_R(reg(pmu, S5E_PMU_INFORM2)) != w2) return S5E_RESET_EVERIFY2;

    /* sec_reboot(): INFORM3 = reason (plain write). */
    S5E_MMIO_W(reg(pmu, S5E_PMU_INFORM3), reason);
    S5E_BARRIER();
    if (S5E_MMIO_R(reg(pmu, S5E_PMU_INFORM3)) != reason) return S5E_RESET_EVERIFY3;

    /* exynos_reboot_parse(): regmap_update_bits(reboot-cmd-offset, 7, mode). The ACPM STOP request that precedes it in
     * exynos_restart_handler() is not replayed: the loader has no ACPM channel (see README, unknown U2). */
    uint32_t wc = (S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) & ~S5E_MODE_MASK) | s5e_reset_mode_for(reason);
    S5E_MMIO_W(reg(pmu, S5E_PMU_REBOOT_CMD), wc);
    S5E_BARRIER();
    if (((S5E_MMIO_R(reg(pmu, S5E_PMU_REBOOT_CMD)) ^ wc) & S5E_MODE_MASK) != 0) return S5E_RESET_EVERIFYC;
    return S5E_RESET_OK;
}

void s5e_reset_trigger(volatile uint32_t *pmu)
{
    S5E_MMIO_W(reg(pmu, S5E_PMU_REBOOT), S5E_PMU_REBOOT_TRIGGER); /* regmap_write(reboot-offset, reboot-trigger) */
    S5E_BARRIER();
}

int s5e_reset_to(volatile uint32_t *pmu, uint32_t reason)
{
    int r = s5e_reset_prepare(pmu, reason);
    if (r != S5E_RESET_OK) return r;
    s5e_reset_trigger(pmu);
    S5E_WAIT();
    return r;
}
