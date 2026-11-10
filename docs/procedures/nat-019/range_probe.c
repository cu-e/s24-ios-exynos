/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Actual owned watchdog API, host arrays only; no device MMIO. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "s5e9945.h"
int main(void) {
    const unsigned requests[]={30,83,84,120};
    puts("[");
    for(unsigned i=0;i<sizeof(requests)/sizeof(requests[0]);i++) {
        uint32_t timer[5]={0}, pmu[0x2000/4]={0};
        uint32_t old_timer[5],old_pmu[0x2000/4];
        memcpy(old_timer,timer,sizeof(timer));memcpy(old_pmu,pmu,sizeof(pmu));
        struct s5e_wdt w={timer,pmu,25600000,0};
        int rc=s5e_wdt_arm(&w,requests[i]);
        int unchanged=!memcmp(timer,old_timer,sizeof(timer))&&!memcmp(pmu,old_pmu,sizeof(pmu));
        unsigned divisor=((timer[0]>>8)&255)+1;
        if(requests[i]>=84){assert(rc==-1);assert(unchanged);}
        else {assert(rc==0);assert(timer[1]<=65535);assert(!unchanged);}
        printf("{\"requested_seconds\":%u,\"return_code\":%d,\"registers_unchanged\":%s,\"count\":%u,\"divisor\":%u,\"nominal_seconds\":%.9f}%s\n",
          requests[i],rc,unchanged?"true":"false",timer[1],divisor,
          timer[1]*(double)divisor*128/25600000,i==3?"":",");
    }
    puts("]");return 0;
}
