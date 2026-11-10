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
    /* SEC_RESET_REASON_UNKNOWN matches normal kernel restart. Preserve other
       reasons for diagnosis. Refuse handoff if the RECOVERY marker persists. */
    if (pmu[0xbc/4]==0x12345604) {
        pmu[0xbc/4]=0x12345600;
        reason_barrier();
        if (pmu[0xbc/4]!=0x12345600) return -1;
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
