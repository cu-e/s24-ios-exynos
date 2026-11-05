#define _GNU_SOURCE
#include "observe.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
extern void oracle_tmu(void *,unsigned,unsigned,unsigned,int);
extern void oracle_tmu_read(const void *,unsigned,int *,int *);
extern void oracle_clock(void *,unsigned,uint32_t);
extern unsigned oracle_clock_read(const void *,unsigned *,int32_t *);
extern unsigned oracle_domain_count(void);
extern unsigned oracle_domain_id(unsigned);
extern void oracle_fvmap(void *,unsigned,unsigned,unsigned,unsigned);
static unsigned checks,tmu_cases,clock_cases,guard_cases,extent_cases;
#define CHECK(x) do { checks++;assert(x); } while (0)
static struct power_policy policy(uint32_t kind,uint32_t id)
{ struct power_policy p={100,POWER_SOURCE_S5E9945,kind,id,7};return p; }
static void start(struct power_observer *s,uint32_t kind,uint32_t id)
{
    struct power_policy p=policy(kind,id);
    CHECK(power_observer_init(s,&p)==0);CHECK(power_observer_begin(s,100)==0);
}
int main(void)
{
    struct power_observer state,before;
    struct power_policy p;
    struct power_ticket ticket,stale;
    struct power_value out;
    struct power_extent extent;
    uint8_t raw[16],copy[POWER_FVMAP_COPY_BYTES],*region,*edge;
    union { uint8_t raw[sizeof(struct power_value)];struct power_value value; } overlap;
    unsigned i,j,unit,ret,random=24009945,domain;
    const uint32_t freqs[]={0,1,999,1000,INT32_MAX,UINT32_C(0x80000000),UINT32_MAX};
    uint32_t id;
    int32_t rate;
    int temp,status;
    long pagesize=sysconf(_SC_PAGESIZE);
    CHECK(oracle_domain_count()==POWER_DVFS_DOMAINS);
    for(i=0;i<33;i++) { CHECK(power_source_domain_id(i,&id)==0);CHECK(id==oracle_domain_id(i)); }
    CHECK(power_source_domain_id(33,&id)==POWER_UNSUPPORTED);CHECK(id==0);
    /* Actual TMU declaration/read helper and actual Linux conversion line. */
    for(i=0;i<8;i++) for(j=0;j<256;j++) {
        oracle_tmu(raw,i,j,j^0xa5,0);oracle_tmu_read(raw,i,&temp,&status);
        CHECK(power_decode_tmu(raw,16,i,POWER_CELSIUS_U8,&out)==0);
        CHECK(out.value==(uint64_t)temp && out.status==(unsigned)status);
        CHECK(out.kind==POWER_TMU && out.unit==POWER_MILLI_CELSIUS);tmu_cases++;
    }
    /* Genuine callback capture is a QoS request, not measured frequency. */
    for(i=0;i<2;i++) for(j=0;j<sizeof(freqs)/sizeof(freqs[0]);j++) {
        oracle_clock(raw,i,freqs[j]);CHECK(oracle_clock_read(raw,&domain,&rate)==1);
        ret=power_decode_clock_request(raw,16,i,POWER_KHZ_U32,&out);
        if(rate<0) { CHECK(ret==(freqs[j]==UINT32_MAX?POWER_UNAVAILABLE:POWER_UNSUPPORTED));CHECK(out.value==0); }
        else { CHECK(ret==0);CHECK(out.value==(uint64_t)rate*1000 && out.source_id==domain);CHECK(out.kind==POWER_CLOCK_REQUEST); }
        clock_cases++;
    }
    for(i=0;i<33;i++) {
        oracle_fvmap(copy,i,i^17,255,7000);
        CHECK(power_fvmap_extent(copy,sizeof(copy),i,POWER_SOURCE_S5E9945,&extent)==0);
        CHECK(extent.selected_index==i && extent.reported_domain==(i^17) && extent.levels==255 && extent.offset==7000 && extent.bytes==1020);extent_cases++;
        oracle_fvmap(copy,i,i,255,8000);CHECK(power_fvmap_extent(copy,sizeof(copy),i,1,&extent)==POWER_LENGTH);
        oracle_fvmap(copy,i,i,1,1715);CHECK(power_fvmap_extent(copy,sizeof(copy),i,1,&extent)==POWER_LENGTH);
        oracle_fvmap(copy,i,i,1,8188);CHECK(power_fvmap_extent(copy,sizeof(copy),i,1,&extent)==0);
        oracle_fvmap(copy,i,i,1,8189);CHECK(power_fvmap_extent(copy,sizeof(copy),i,1,&extent)==POWER_LENGTH);
        oracle_fvmap(copy,i,i,0,7000);CHECK(power_fvmap_extent(copy,sizeof(copy),i,1,&extent)==POWER_UNAVAILABLE);
    }
    oracle_fvmap(copy,0,0,1,7000);CHECK(power_fvmap_extent(copy,sizeof(copy),0,0,&extent)==POWER_UNAVAILABLE);
    CHECK(power_fvmap_extent(copy,sizeof(copy),33,1,&extent)==POWER_ARGUMENT);
    CHECK(power_fvmap_extent(copy,sizeof(copy)-1,0,1,&extent)==POWER_LENGTH);
    oracle_tmu(raw,0,0,0,0);
    for(i=0;i<256;i++) if(i!=2) { raw[4]=(uint8_t)i;CHECK(power_decode_tmu(raw,16,0,1,&out)==POWER_UNSUPPORTED);CHECK(out.value==0); }
    oracle_tmu(raw,0,99,0,-3);oracle_tmu_read(raw,0,&temp,&status);
    CHECK(temp==99000);CHECK(power_decode_tmu(raw,16,0,1,&out)==POWER_FIRMWARE_ERROR);CHECK(out.value==0);
    for(i=1;i<256;i++) {raw[5]=(uint8_t)i;CHECK(power_decode_tmu(raw,16,0,1,&out)==POWER_FIRMWARE_ERROR);}
    oracle_tmu(raw,1,50,0,0);CHECK(power_decode_tmu(raw,16,0,1,&out)==POWER_STALE);
    CHECK(power_decode_tmu(raw,16,8,1,&out)==POWER_ARGUMENT);
    for(unit=0;unit<6;unit++) if(unit!=1) CHECK(power_decode_tmu(raw,16,1,unit,&out)==POWER_UNIT);
    oracle_clock(raw,2,1000);CHECK(power_decode_clock_request(raw,16,0,2,&out)==POWER_UNSUPPORTED);
    oracle_clock(raw,1,1000);CHECK(power_decode_clock_request(raw,16,0,2,&out)==POWER_STALE);
    CHECK(power_decode_clock_request(raw,16,1,4,&out)==POWER_UNIT);
    for(i=0;i<4;i++) {p=policy(i,0);ret=power_observer_init(&state,&p);CHECK(ret==(i==1 || i==2 ? POWER_OK:POWER_UNAVAILABLE));}
    p=policy(POWER_VOLTAGE,0);CHECK(power_observer_init(&state,&p)==POWER_UNAVAILABLE);
    p=policy(POWER_TMU,0);p.profile=0;CHECK(power_observer_init(&state,&p)==POWER_UNAVAILABLE);
    p=policy(POWER_TMU,0);p.max_age_ns=0;CHECK(power_observer_init(&state,&p)==POWER_ARGUMENT);
    /* Missing/error transport cannot become a valid zero degree sample. */
    start(&state,POWER_TMU,0);ticket=state.ticket;
    CHECK(power_observer_accept(&state,&ticket,NULL,0,1,POWER_TRANSPORT_MISSING,0,101)==POWER_UNAVAILABLE);
    CHECK(power_observer_read(&state,101,&out)==POWER_UNAVAILABLE && out.value==0 && !state.valid);
    start(&state,POWER_TMU,0);ticket=state.ticket;
    CHECK(power_observer_accept(&state,&ticket,NULL,0,1,POWER_TRANSPORT_FAILED,0,101)==POWER_TRANSPORT_ERROR);
    start(&state,POWER_TMU,0);oracle_tmu(raw,0,0,0,0);ticket=state.ticket;stale=ticket;stale.generation++;
    before=state;CHECK(power_observer_accept(&state,&stale,raw,16,1,0,101,101)==POWER_STALE);CHECK(!memcmp(&state,&before,sizeof(state)));
    stale=ticket;stale.epoch++;CHECK(power_observer_accept(&state,&stale,raw,16,1,0,101,101)==POWER_STALE);CHECK(!memcmp(&state,&before,sizeof(state)));
    CHECK(power_observer_begin(&state,101)==POWER_BUSY);
    CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,101,102)==0);
    CHECK(power_observer_read(&state,102,&out)==0 && out.value==0 && state.valid);
    CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,101,103)==POWER_STALE);
    CHECK(power_observer_read(&state,200,&out)==0);CHECK(power_observer_read(&state,201,&out)==POWER_STALE && !state.valid);
    start(&state,1,0);ticket=state.ticket;CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,101,200)==POWER_STALE);
    CHECK(power_observer_begin(&state,201)==0);CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,202,202)==POWER_STALE);
    ticket=state.ticket;CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,203,202)==POWER_CLOCK);
    start(&state,1,0);ticket=state.ticket;CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,99,101)==POWER_CLOCK);
    start(&state,1,0);ticket=state.ticket;CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,100,99)==POWER_CLOCK);
    start(&state,1,0);ticket=state.ticket;CHECK(power_observer_accept(&state,&ticket,raw,15,1,0,101,101)==POWER_LENGTH);CHECK(!state.valid && !state.waiting);
    p=policy(1,0);CHECK(power_observer_init(&state,&p)==0);CHECK(power_observer_begin(&state,UINT64_MAX-99)==POWER_OVERFLOW);
    CHECK(power_observer_begin(&state,1)==0);CHECK(power_observer_stop(&state)==0);CHECK(power_observer_stop(&state)==0);
    CHECK(power_observer_begin(&state,2)==POWER_STOPPED);ticket=state.ticket;
    CHECK(power_observer_accept(&state,&ticket,raw,16,1,0,2,2)==POWER_STOPPED);
    CHECK(power_observer_read(&state,2,&out)==POWER_STOPPED && out.value==0);
    CHECK(power_observer_init(&state,&p)==0);state.ticket.generation=UINT32_MAX;CHECK(power_observer_begin(&state,1)==POWER_EXHAUSTED);
    start(&state,2,1);oracle_clock(raw,1,INT32_MAX);ticket=state.ticket;
    CHECK(power_observer_accept(&state,&ticket,raw,16,2,0,101,101)==0);
    CHECK(power_observer_read(&state,102,&state.sample)==0 && state.sample.value==UINT64_C(2147483647000));
    CHECK(power_observer_stop(&state)==0 && !state.valid);CHECK(power_observer_read(&state,103,&out)==POWER_STOPPED && !out.value);
    oracle_tmu(overlap.raw,0,73,0,0);CHECK(power_decode_tmu(overlap.raw,16,0,1,&overlap.value)==0 && overlap.value.value==73000);
    CHECK(pagesize>0);region=mmap(NULL,(size_t)pagesize*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    CHECK(region!=MAP_FAILED);CHECK(mprotect(region+pagesize,(size_t)pagesize,PROT_NONE)==0);
    oracle_tmu(raw,0,10,0,0);
    for(i=0;i<16;i++) {edge=region+pagesize-i;if(i)memcpy(edge,raw,i);CHECK(power_decode_tmu(edge,i,0,1,&out)==POWER_LENGTH);CHECK(power_decode_clock_request(edge,i,0,2,&out)==POWER_LENGTH);guard_cases+=2;}
    CHECK(power_decode_tmu(raw,17,0,1,&out)==POWER_LENGTH);CHECK(power_decode_clock_request(raw,17,0,2,&out)==POWER_LENGTH);
    CHECK(power_decode_tmu(NULL,16,0,1,&out)==POWER_ARGUMENT);CHECK(power_decode_clock_request(NULL,16,0,2,&out)==POWER_ARGUMENT);
    edge=region+pagesize-16;
    for(i=0;i<100000;i++) {
        for(j=0;j<16;j++) { random=random*1664525u+1013904223u;edge[j]=(uint8_t)(random>>24); }
        ret=power_decode_tmu(edge,16,0,1,&out);CHECK(ret<=POWER_STALE);if(!ret)CHECK(out.value<=255000);
        ret=power_decode_clock_request(edge,16,0,2,&out);CHECK(ret<=POWER_STALE);if(!ret)CHECK(out.value<=UINT64_C(2147483647000));
    }
    CHECK(munmap(region,(size_t)pagesize*2)==0);
    printf("{\"checks\":%u,\"tmu_cases\":%u,\"clock_cases\":%u,\"extent_cases\":%u,\"guard_lengths\":%u,\"random_records\":100000,\"hardware_io\":false}\n",checks,tmu_cases,clock_cases,extent_cases,guard_cases);
    return 0;
}
