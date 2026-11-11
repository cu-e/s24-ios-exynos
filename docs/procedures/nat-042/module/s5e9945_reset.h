/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * NAT-042: end-of-run reset of the S5E9945 into a chosen boot target, as a replay of the register writes the vendor
 * Android kernel makes for `reboot <cmd>`. Every value below is cited in ../plan.json (pin 417484173abc2c4f...):
 *   sec_reboot.c      INFORM2[23:16] = 0x4E, INFORM3 = reason, cache flush          (priority 130, first)
 *   exynos-reboot.c   ACPM STOP request (NOT replayed here), reboot-cmd-offset[2:0] = mode, reboot-offset = trigger
 * The code is host-built against a PMU model; it has not run on the phone. Constants are copied from the vendor
 * sources/DT (GPL-2.0); the loader this is meant for is GPL-2.0-or-later.
 */
#ifndef S5E9945_RESET_H
#define S5E9945_RESET_H
#include <stdint.h>

#define S5E_PMU_BASE            0x12860000u
#define S5E_PMU_INFORM2         0x00b8u   /* sec-reboot magic-inform  */
#define S5E_PMU_INFORM3         0x00bcu   /* sec-reboot panic-inform  */
#define S5E_PMU_REBOOT_CMD      0x0190u   /* exynos-reboot reboot-cmd-offset */
#define S5E_PMU_REBOOT          0x3c00u   /* exynos-reboot reboot-offset     */
#define S5E_PMU_REBOOT_TRIGGER  0x2u      /* exynos-reboot reboot-trigger    */

#define S5E_REASON_NORMAL       0x12345600u  /* SEC_RESET_REASON_UNKNOWN: plain restart       */
#define S5E_REASON_DOWNLOAD     0x12345601u  /* SEC_RESET_REASON_DOWNLOAD: `reboot download`  */
#define S5E_REASON_BOOTLOADER   0x1234560du  /* SEC_RESET_REASON_BOOTLOADER: `reboot bootloader` */

#define S5E_INFORM2_BYTE_SHIFT  16u
#define S5E_INFORM2_BYTE_MASK   0xffu
#define S5E_INFORM2_NORMAL      0x4eu     /* SEC_REBOOT_NORMAL */

#define S5E_MODE_MASK           0x7u      /* REBOOT_MODE_MASK */
#define S5E_MODE_NORMAL         0x0u      /* REBOOT_MODE_NORMAL */
#define S5E_MODE_FASTBOOT       0x3u      /* REBOOT_MODE_FASTBOOT (cmd "bootloader") */

#define S5E_RESET_OK            0
#define S5E_RESET_EREASON      (-1)   /* reason is not one of the three above; nothing written */
#define S5E_RESET_EVERIFY2     (-2)   /* INFORM2 did not read back; nothing after it written */
#define S5E_RESET_EVERIFY3     (-3)   /* INFORM3 did not read back */
#define S5E_RESET_EVERIFYC     (-4)   /* reboot-cmd word did not read back */

struct s5e_reset_snapshot { uint32_t inform2, inform3, cmd; };

/* Read-only: what S-Boot left in the three words. Never writes. */
void s5e_reset_snapshot(volatile const uint32_t *pmu, struct s5e_reset_snapshot *out);

/* Mode (reboot-cmd bits 2:0) the vendor handler stores for a reason: "bootloader" -> 3, "download"/unknown -> 0. */
uint32_t s5e_reset_mode_for(uint32_t reason);

/* Writes INFORM2, INFORM3 and the reboot-cmd word in the vendor order, with a dsb and a read-back check after each.
 * Does not trigger. On error the registers written so far stay written and the trigger must not follow. */
int s5e_reset_prepare(volatile uint32_t *pmu, uint32_t reason);

/* The software-reset store (reboot-offset = reboot-trigger) and a dsb; the caller then waits for the reset. */
void s5e_reset_trigger(volatile uint32_t *pmu);

/* prepare, then trigger only if prepare returned S5E_RESET_OK. Returns the prepare status (on the target it returns only
 * on failure, or never; the host port returns after the trigger store so a test can look at the register file). */
int s5e_reset_to(volatile uint32_t *pmu, uint32_t reason);

#endif
