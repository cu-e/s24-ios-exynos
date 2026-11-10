/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <string.h>
#include "s5e9945.h"
int main(void) {
    uint32_t timer[64]={0}, pmu[0x10000/4]={0};
    struct s5e_wdt w={timer,pmu,25600000,0};
    struct s5e_wdt_state s;
    for (unsigned c=0;c<2;c++) {
        w.cluster=c; unsigned r=(c?0x1844:0x1244)/4;
        pmu[r]=0xa5000000;
        assert(s5e_wdt_arm(&w,30)==0);
        /* 25.6MHz /128 = 200000Hz; 6000000/92 rounded up =65218.
           Effective timeout = 65218*92/200000 =30.00028s. */
        assert(timer[0]==0x105b39 && timer[1]==65218 && timer[2]==65218);
        assert(timer[4]==130436 && timer[3]==0);
        assert(pmu[r]==(0xa5000000u | (c?8:4)));
        timer[2]=10; assert(s5e_wdt_query(&w,&s)==0 && s.count==10);
        s5e_wdt_pet(&w); assert(timer[2]==65218);
        s5e_wdt_disarm(&w); assert(!(timer[0]&0x21) && pmu[r]==0xa5000000u);
    }
    uint32_t saved[64]; memcpy(saved,timer,sizeof timer);
    assert(s5e_wdt_arm(&w,0)==-1);
    assert(s5e_wdt_arm(&w,0xffffffffu)==-1);
    w.rate_hz=0; assert(s5e_wdt_arm(&w,1)==-1);
    w.cluster=2; assert(s5e_wdt_arm(&w,1)==-1);
    assert(!memcmp(saved,timer,sizeof timer));
    assert(s5e_wdt_query(0,&s)==-1);
    return 0;
}
