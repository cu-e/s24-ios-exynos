/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "s5e9945.h"
/* Called once before loader_main; never pet in exception/halt paths. */
static void reason_barrier(void) {
#if defined(__aarch64__)
    __asm__ volatile("dsb sy" ::: "memory");
#else
    __asm__ volatile("" ::: "memory");
#endif
}
int recovery_prepare(volatile uint32_t *pmu, const struct s5e_wdt *w) {
    /* S921BXXS9BYH3 S-Boot sbl_check_reboot_mode (0x29d994..0x29dde8) copies
       PMU_PANIC_INFORM (0x128600bc == 0x12345604) into persistent param(0)
       REBOOT_MODE=4 and then zeroes 0x128600bc (str wzr, [x21] at 0x29dde8).
       On the next boot after watchdog reset, S-Boot skips param(0) update if
       0x128600bc is 0 (0x29dec4), which would leave param(0)=4 sticky, whereas
       0x12345600 (SEC_RESET_REASON_UNKNOWN) causes sbl_check_reboot_mode
       (0x29d9d8..0x29da64) to call set_param(0, 0, 0, 1) and boot normal Android.
       Write 0x12345600 when 0x128600bc is 0x12345604 or 0; preserve other
       non-zero diagnostic reasons. */
    uint32_t cur=pmu[0xbc/4];
    if (cur==0x12345604u || cur==0u) {
        pmu[0xbc/4]=0x12345600u;
        reason_barrier();
        if (pmu[0xbc/4]!=0x12345600u) return -1;
    }
    if (s5e_wdt_arm(w,30)) return -1;
    /* Gate/clock assumptions are not established by register write readback.
       Require an observed decrement within a bounded CPU loop. This cannot
       prove future clock survival or S-Boot's choice after reset. */
    uint32_t initial=w->timer[2];
    for (unsigned i=0;i<1000000;i++)
        if (w->timer[2]<initial) return 0;
    s5e_wdt_disarm(w);
    return -1;
}

int recovery_guard(void) {
    volatile uint32_t *pmu=(volatile uint32_t *)(uintptr_t)0x12860000;
    struct s5e_wdt w={(volatile uint32_t *)(uintptr_t)0x10040000,pmu,25600000,0};
    return recovery_prepare(pmu,&w);
}
