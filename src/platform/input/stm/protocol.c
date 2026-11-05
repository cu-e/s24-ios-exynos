#include "protocol.h"
_Static_assert(STM_CONTACTS==UI_MAX_CONTACTS,"STM/UI contact count mismatch");

static uint32_t config_valid(const struct stm_config *c)
{
    return c && c->max_x && c->max_x<=STM_RAW_MAX && c->max_y &&
        c->max_y<=STM_RAW_MAX && c->flip<=3 && c->rotation<=3;
}

uint32_t stm_decode(const uint8_t *p, size_t length, uint32_t max_x,
    uint32_t max_y, struct stm_coordinate *out)
{
    struct stm_coordinate value={0};
    uint32_t i, any=0, result=STM_OK, eid;
    if (!out) return STM_ARGUMENT;
    if (!p) { *out=value; return STM_ARGUMENT; }
    if (length!=STM_RECORD_BYTES) { *out=value; return STM_LENGTH; }
    if (!max_x || max_x>STM_RAW_MAX || !max_y || max_y>STM_RAW_MAX) {
        *out=value; return STM_ARGUMENT;
    }
    for (i=0;i<STM_RECORD_BYTES;i++) any|=p[i];
    if (!any) { *out=value; return STM_EMPTY; }
    eid=p[0]&3u;
    if (eid!=0) {
        /* Pinned Samsung status policy releases on queue-full, schedules
           reset on ESD/ready-reset. This boundary invalidates contacts but
           never performs that reset. Unknown status remains the bus owner's
           responsibility, not a fabricated coordinate. */
        uint32_t type=(p[0]>>2)&15u;
        result=(eid==1 && (type==1 ||
            (type==2 && p[1]==0 && p[2]==0x10))) ?
            STM_CONTROLLER_LOSS : STM_NOT_COORDINATE;
        *out=value; return result;
    }
    value.slot=(p[0]>>2)&15u;
    value.action=p[0]>>6;
    value.x=((uint32_t)p[1]<<4)|(p[3]>>4);
    value.y=((uint32_t)p[2]<<4)|(p[3]&15u);
    value.touch_type=((uint32_t)(p[6]>>6)<<2)|(p[7]>>6);
    value.pressure=p[6]&63u; value.major=p[4]; value.minor=p[5];
    value.remaining=p[7]&31u;
    if (!value.action) result=STM_FORMAT;
    else if (value.slot>=STM_CONTACTS || value.x>max_x || value.y>max_y) result=STM_RANGE;
    else if (value.touch_type!=0 && value.touch_type!=3 &&
        value.touch_type!=5 && value.touch_type!=6) result=STM_UNSUPPORTED;
    if (result!=STM_OK) { struct stm_coordinate empty={0}; value=empty; }
    *out=value;
    return result;
}

uint32_t stm_adapter_init(struct stm_adapter *s, const struct stm_config *c, uint32_t epoch)
{
    struct stm_adapter empty={0};
    if (!s) return STM_ARGUMENT;
    if (!config_valid(c) || !epoch) { *s=empty; return STM_ARGUMENT; }
    empty.config=*c;
    (void)ui_input_init(&empty.logical,epoch);
    *s=empty;
    return STM_OK;
}

static uint32_t ready(const struct stm_adapter *s, stm_emit_fn emit)
{
    if (!s || !emit || !s->logical.epoch || !config_valid(&s->config)) return STM_ARGUMENT;
    if (s->dispatching) return STM_BUSY;
    if (s->logical.stopped) return STM_STOPPED;
    return STM_OK;
}

uint32_t stm_adapter_retry(struct stm_adapter *s, stm_emit_fn emit, void *context)
{
    uint32_t r=ready(s,emit);
    int accepted;
    if (r) return r;
    if (!s->pending_valid) return STM_ARGUMENT;
    s->dispatching=1;
    accepted=emit(context,&s->pending);
    s->dispatching=0;
    if (accepted) return STM_DELIVERY;
    s->logical=s->candidate;
    s->pending_valid=0;
    if (s->stop_after) ui_input_stop(&s->logical);
    s->stop_after=0;
    return STM_OK;
}

static uint32_t queue(struct stm_adapter *s, struct ui_event *event,
    uint32_t stop, stm_emit_fn emit, void *context)
{
    uint32_t r;
    /* Keep the final sequence for an acknowledged cancellation. */
    if (s->logical.sequence==UINT32_MAX ||
        (event->kind!=UI_CANCEL_ALL && s->logical.sequence==UINT32_MAX-1)) {
        s->logical.needs_resync=1; return STM_EXHAUSTED;
    }
    if (!event->time_ns || event->time_ns<s->logical.time_ns) {
        s->logical.needs_resync=1; return STM_CLOCK;
    }
    event->epoch=s->logical.epoch;
    event->sequence=s->logical.sequence+1;
    s->candidate=s->logical;
    r=ui_input_apply(&s->candidate,event);
    if (r) {
        s->logical.needs_resync=1;
        return r==UI_DESYNC ? STM_DESYNC : STM_TRANSITION;
    }
    s->pending=*event; s->pending_valid=1; s->stop_after=stop;
    return stm_adapter_retry(s,emit,context);
}

static uint32_t cancel(struct stm_adapter *s, uint64_t now, uint32_t stop,
    stm_emit_fn emit, void *context)
{
    struct ui_event event={0};
    uint32_t r=ready(s,emit);
    if (r) return r;
    if (s->pending_valid && s->stop_after && !stop) return STM_BUSY;
    /* A declined synchronous delivery published nothing. Replace it with a
       cancellation for the last acknowledged contact set, using its next
       sequence. There is no asynchronous stale acknowledgement API. */
    if (!now || now<s->logical.time_ns) return STM_CLOCK;
    if (stop && s->logical.sequence==UINT32_MAX && !s->logical.active &&
        !s->logical.needs_resync && !s->pending_valid) {
        ui_input_stop(&s->logical); return STM_OK;
    }
    event.kind=UI_CANCEL_ALL; event.time_ns=now;
    return queue(s,&event,stop,emit,context);
}

uint32_t stm_adapter_resync(struct stm_adapter *s, uint64_t now, stm_emit_fn emit, void *context)
{ return cancel(s,now,0,emit,context); }
uint32_t stm_adapter_stop(struct stm_adapter *s, uint64_t now, stm_emit_fn emit, void *context)
{ return cancel(s,now,1,emit,context); }

uint32_t stm_adapter_feed(struct stm_adapter *s, const uint8_t *p, size_t length,
    uint64_t now, stm_emit_fn emit, void *context)
{
    struct stm_coordinate coordinate;
    struct ui_point point;
    struct ui_event event={0};
    uint32_t r=ready(s,emit);
    if (r) return r;
    if (s->pending_valid) return STM_BUSY;
    r=stm_decode(p,length,s->config.max_x,s->config.max_y,&coordinate);
    if (r) {
        if (r!=STM_EMPTY && r!=STM_NOT_COORDINATE) s->logical.needs_resync=1;
        return r;
    }
    if (s->logical.needs_resync) return STM_DESYNC;
    if (ui_map_point(coordinate.x,coordinate.y,s->config.max_x,s->config.max_y,
        s->config.flip,s->config.rotation,&point)) return STM_RANGE;
    event.time_ns=now; event.slot=coordinate.slot;
    event.x=point.x; event.y=point.y;
    event.kind=coordinate.action==1 ? UI_DOWN : coordinate.action==2 ? UI_MOVE : UI_UP;
    return queue(s,&event,0,emit,context);
}

static void wr16(uint8_t *p, uint32_t v) { p[0]=(uint8_t)v; p[1]=(uint8_t)(v>>8); }
static void wr32(uint8_t *p, uint32_t v) { wr16(p,v); wr16(p+2,v>>16); }
uint32_t stm_event_wire(const struct ui_event *e, uint8_t *wire, size_t length)
{
    uint32_t i;
    struct ui_event check, value;
    if (!e || !wire) return STM_ARGUMENT;
    if (length!=UI_INPUT_BYTES) return STM_LENGTH;
    value=*e;
    if (value.kind>UINT16_MAX || value.slot>UINT16_MAX) return STM_RANGE;
    for (i=0;i<UI_INPUT_BYTES;i++) wire[i]=0;
    wr32(wire,UINT32_C(0x49483145)); wr16(wire+4,1); wr16(wire+6,UI_INPUT_BYTES);
    wr32(wire+8,value.epoch); wr32(wire+12,value.sequence);
    wr32(wire+16,(uint32_t)value.time_ns); wr32(wire+20,(uint32_t)(value.time_ns>>32));
    wr16(wire+24,value.kind); wr16(wire+26,value.slot); wr32(wire+28,value.x); wr32(wire+32,value.y);
    if (ui_event_decode(wire,length,&check)) {
        for (i=0;i<UI_INPUT_BYTES;i++) wire[i]=0;
        return STM_FORMAT;
    }
    return STM_OK;
}
