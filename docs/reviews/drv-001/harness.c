/* Independent review fixture; project-authored, host only. */
#include "protocol.h"
#include "samsung-layout.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

struct sink { struct stm_adapter *adapter; struct ui_input_state consumer; unsigned declined, calls, reenter; };
static int accept(void *context, const struct ui_event *e)
{
    struct sink *s=context;
    if (s->reenter) {
        const uint8_t raw[16]={0x40};
        assert(stm_adapter_feed(s->adapter,raw,16,e->time_ns,accept,s)==STM_BUSY);
        assert(stm_adapter_retry(s->adapter,accept,s)==STM_BUSY);
        assert(stm_adapter_stop(s->adapter,e->time_ns,accept,s)==STM_BUSY);
        assert(stm_adapter_resync(s->adapter,e->time_ns,accept,s)==STM_BUSY);
    }
    if (s->declined) return -9;
    assert(ui_input_apply(&s->consumer,e)==UI_OK);
    s->calls++;
    return 0;
}
static void equal(const struct stm_adapter *a, const struct sink *s)
{
    assert(a->logical.epoch==s->consumer.epoch);
    assert(a->logical.sequence==s->consumer.sequence);
    assert(a->logical.time_ns==s->consumer.time_ns);
    assert(a->logical.active==s->consumer.active);
}
int main(void)
{
    unsigned action,slot,type,i,checked=0;
    struct stm_coordinate c;
    uint8_t raw[16]={0};
    _Static_assert(sizeof(struct stm_ts_event_coordinate)==16,"Samsung record size");
    for(action=1;action<=3;action++) for(slot=0;slot<16;slot++) for(type=0;type<16;type++) for(i=0;i<16;i++) {
        struct stm_ts_event_coordinate oracle;
        raw[0]=(uint8_t)((action<<6)|(slot<<2));
        raw[1]=(uint8_t)(i*17);raw[2]=(uint8_t)(255-i*17);raw[3]=(uint8_t)(i*17);
        raw[4]=12;raw[5]=7;raw[6]=(uint8_t)(((type>>2)<<6)|63);raw[7]=(uint8_t)(((type&3)<<6)|32|i);
        raw[10]=0xff;raw[15]=0xff;
        memcpy(&oracle,raw,16);
        unsigned r=stm_decode(raw,16,4095,4095,&c);
        if(slot>=10) assert(r==STM_RANGE);
        else if(type!=0 && type!=3 && type!=5 && type!=6) assert(r==STM_UNSUPPORTED);
        else {
            assert(r==STM_OK);
            assert(c.slot==oracle.tid && c.action==oracle.tchsta);
            assert(c.x==((unsigned)oracle.x_11_4<<4|oracle.x_3_0));
            assert(c.y==((unsigned)oracle.y_11_4<<4|oracle.y_3_0));
            assert(c.touch_type==((unsigned)oracle.ttype_3_2<<2|oracle.ttype_1_0));
            assert(c.remaining==oracle.left_event && c.pressure==oracle.z);
        }
        checked++;
    }
    for(i=0;i<4;i++) {
        memset(raw,0,sizeof(raw));raw[0]=(uint8_t)(9|(i<<6));raw[2]=0x10;
        assert(stm_decode(raw,16,4095,4095,&c)==STM_CONTROLLER_LOSS);
        raw[2]=0x11;assert(stm_decode(raw,16,4095,4095,&c)==STM_NOT_COORDINATE);
    }
    struct stm_adapter a;
    struct stm_config cfg={4095,4095,0,0};
    struct sink s={.adapter=&a,.declined=1,.reenter=1};
    assert(stm_adapter_init(&a,&cfg,3)==STM_OK);
    assert(ui_input_init(&s.consumer,3)==UI_OK);
    assert(stm_adapter_resync(&a,100,accept,&s)==STM_DELIVERY);
    assert(a.logical.needs_resync && !a.logical.sequence);
    assert(stm_adapter_stop(&a,99,accept,&s)==STM_DELIVERY); /* Replaces unpublished initial cancel. */
    struct ui_event pending=a.pending;
    assert(stm_adapter_resync(&a,101,accept,&s)==STM_BUSY);
    assert(stm_adapter_stop(&a,0,accept,&s)==STM_CLOCK);
    assert(memcmp(&pending,&a.pending,sizeof(pending))==0 && a.stop_after);
    s.declined=0;assert(stm_adapter_retry(&a,accept,&s)==STM_OK);
    equal(&a,&s);assert(a.logical.stopped && s.calls==1 && s.consumer.time_ns==99);
    /* A fresh epoch with an acknowledged contact and a declined MOVE. */
    assert(stm_adapter_init(&a,&cfg,4)==STM_OK);assert(ui_input_init(&s.consumer,4)==UI_OK);
    assert(stm_adapter_resync(&a,200,accept,&s)==STM_OK);
    memset(raw,0,sizeof(raw));raw[0]=0x64; /* DOWN slot 9, origin. */
    assert(stm_adapter_feed(&a,raw,16,201,accept,&s)==STM_OK);equal(&a,&s);
    raw[0]=0xa4;s.declined=1;
    assert(stm_adapter_feed(&a,raw,16,500,accept,&s)==STM_DELIVERY);
    assert(stm_adapter_stop(&a,202,accept,&s)==STM_DELIVERY); /* Time relative to last accepted event. */
    assert(a.logical.active==(1u<<9) && !a.logical.stopped && a.pending.time_ns==202);
    s.declined=0;assert(stm_adapter_retry(&a,accept,&s)==STM_OK);equal(&a,&s);
    assert(!a.logical.active && a.logical.stopped);
    /* Exhaustion keeps the final cancellation available and never wraps. */
    assert(stm_adapter_init(&a,&cfg,5)==STM_OK);assert(ui_input_init(&s.consumer,5)==UI_OK);
    assert(stm_adapter_resync(&a,600,accept,&s)==STM_OK);
    a.logical.sequence=UINT32_MAX-1;s.consumer.sequence=UINT32_MAX-1;
    raw[0]=0x40;assert(stm_adapter_feed(&a,raw,16,601,accept,&s)==STM_EXHAUSTED);
    assert(a.logical.needs_resync);
    assert(stm_adapter_resync(&a,602,accept,&s)==STM_OK);equal(&a,&s);
    assert(a.logical.sequence==UINT32_MAX);
    assert(stm_adapter_stop(&a,603,accept,&s)==STM_OK && a.logical.stopped);
    printf("{\"Samsung_layout_records\":%u,\"status_flag_variants\":8,\"reentry_apis\":4,\"lifecycle_groups\":3,\"hardware_io\":false}\n",checked);
    return 0;
}
