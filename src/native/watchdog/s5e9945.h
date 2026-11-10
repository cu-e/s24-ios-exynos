/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Register facts: Samsung s3c2410_wdt.{c,h}, see NAT-007 source citations. */
#ifndef S5E9945_WATCHDOG_H
#define S5E9945_WATCHDOG_H
#include <stdint.h>
struct s5e_wdt {
    volatile uint32_t *timer;
    volatile uint32_t *pmu;
    uint32_t rate_hz; /* Caller must establish that the clock is enabled at this rate. */
    unsigned cluster; /* 0=v1, 1=v2 */
};
struct s5e_wdt_state { uint32_t control, reload, count, route; };
int s5e_wdt_query(const struct s5e_wdt *, struct s5e_wdt_state *);
int s5e_wdt_arm(const struct s5e_wdt *, uint32_t seconds);
void s5e_wdt_pet(const struct s5e_wdt *);
void s5e_wdt_disarm(const struct s5e_wdt *);
#endif
