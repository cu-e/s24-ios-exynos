/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Diagnostic derivative of NAT-009's published guard, not a return guarantee. */
#include "s5e9945.h"
extern void diagnostic_value(const char *, uint64_t);
int recovery_guard(void)
{
    volatile uint32_t *pmu=(volatile uint32_t *)(uintptr_t)0x12860000;
    struct s5e_wdt w={(volatile uint32_t *)(uintptr_t)0x10040000,pmu,25600000,0};
    diagnostic_value("panic_inform_before",pmu[0xbc/4]);
    if (pmu[0xbc/4]==0x12345604) {
        pmu[0xbc/4]=0x12345600;
        __asm__ volatile("dsb sy" ::: "memory");
        if (pmu[0xbc/4]!=0x12345600) return -1;
    }
    diagnostic_value("panic_inform_after",pmu[0xbc/4]);
    if (s5e_wdt_arm(&w,83)) return -1;
    uint32_t initial=w.timer[2];
    diagnostic_value("WTCON",w.timer[0]);
    diagnostic_value("WTDAT",w.timer[1]);
    diagnostic_value("WTCNT_initial",initial);
    for (unsigned i=0;i<1000000;i++) {
        uint32_t current=w.timer[2];
        if (current<initial) {
            diagnostic_value("WTCNT_decremented",current);
            return 0;
        }
    }
    diagnostic_value("watchdog_not_decrementing",w.timer[2]);
    /* Stop before XNU. Do not disable a possibly working reset timer on failure. */
    return -1;
}
