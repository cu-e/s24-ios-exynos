/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "s5e9945.h"
#include <assert.h>
int recovery_prepare(volatile uint32_t *,const struct s5e_wdt *);
int main(void) {
    uint32_t timer[64]={0},pmu[0x10000/4]={0};
    struct s5e_wdt w={timer,pmu,25600000,0};
    uint32_t reasons[]={0x12345604,0x12345600,0x12345601,0,0xdeadbeef};
    for(unsigned i=0;i<5;i++) {
        pmu[0xbc/4]=reasons[i]; pmu[0x1244/4]=0xa0000000;
        /* No clock ticks in simulated registers: must fail closed, disarm,
           and never permit XNU handoff on write/readback alone. */
        assert(recovery_prepare(pmu,&w)==-1);
        assert(pmu[0xbc/4]==(i==0?0x12345600:reasons[i]));
        assert(!(timer[0]&0x21) && pmu[0x1244/4]==0xa0000000);
    }
    return 0;
}
