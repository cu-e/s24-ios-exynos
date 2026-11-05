/* Host-only guard-page/sanitizer fixture. Not part of a native driver. */
#define _GNU_SOURCE
#include "protocol.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

struct capture { unsigned count; int decline; struct ui_event event; };
static int emit(void *context, const struct ui_event *event)
{
    struct capture *c=context;
    if (c->decline) return 1;
    c->count++; c->event=*event; return 0;
}
int main(void)
{
    static const uint8_t raw[16]={0x40,0x12,0xab,0x3c,12,9,31,0};
    struct stm_coordinate coordinate;
    long pagesize=sysconf(_SC_PAGESIZE);
    unsigned i,code,random=24009945;
    uint8_t *region,*edge;
    struct stm_adapter state;
    struct stm_config config={4095,4095,0,0};
    struct capture capture={0};
    union { struct ui_event event; uint8_t wire[40]; } overlap;
    assert(pagesize>0);
    region=mmap(NULL,(size_t)pagesize*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(region!=MAP_FAILED);
    assert(mprotect(region+pagesize,(size_t)pagesize,PROT_NONE)==0);
    for (i=0;i<16;i++) {
        edge=region+pagesize-i;
        if (i) memcpy(edge,raw,i);
        assert(stm_decode(edge,i,4095,4095,&coordinate)==STM_LENGTH);
    }
    edge=region+pagesize-16;memcpy(edge,raw,16);
    assert(stm_decode(edge,16,4095,4095,&coordinate)==STM_OK);
    assert(coordinate.x==0x123 && coordinate.y==0xabc);
    assert(stm_decode(edge,17,4095,4095,&coordinate)==STM_LENGTH);
    for (i=0;i<100000;i++) {
        unsigned n;
        for (n=0;n<16;n++) { random=random*1664525u+1013904223u;edge[n]=(uint8_t)(random>>24); }
        code=stm_decode(edge,16,4095,4095,&coordinate);
        assert(code<=STM_CONTROLLER_LOSS);
        if (!code) assert(coordinate.slot<10 && coordinate.x<=4095 && coordinate.y<=4095);
    }
    assert(stm_adapter_init(&state,&config,1)==STM_OK);
    assert(stm_adapter_resync(&state,100,emit,&capture)==STM_OK);
    assert(stm_adapter_feed(&state,raw,16,101,emit,&capture)==STM_OK);
    capture.decline=1;
    assert(stm_adapter_stop(&state,102,emit,&capture)==STM_DELIVERY);
    assert(state.logical.active==1 && !state.logical.stopped);
    capture.decline=0;
    assert(stm_adapter_retry(&state,emit,&capture)==STM_OK);
    assert(!state.logical.active && state.logical.stopped);
    overlap.event=capture.event;
    assert(stm_event_wire(&overlap.event,overlap.wire,40)==STM_OK);
    assert(ui_event_decode(overlap.wire,40,&capture.event)==UI_OK);
    assert(capture.event.kind==UI_CANCEL_ALL);
    assert(munmap(region,(size_t)pagesize*2)==0);
    puts("{\"guard_lengths\":18,\"random_records\":100000,\"acknowledged_stop\":true,\"hardware_io\":false}");
    return 0;
}
