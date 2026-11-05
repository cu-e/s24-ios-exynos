#include "observe.h"
static uint32_t le32(const uint8_t *p)
{ return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
uint32_t power_source_domain_id(uint32_t index,uint32_t *out)
{
    if (!out) return POWER_ARGUMENT;
    *out=0;
    if (index>=POWER_DVFS_DOMAINS) return POWER_UNSUPPORTED;
    *out=UINT32_C(0x0b040000)+index;
    return POWER_OK;
}
uint32_t power_fvmap_extent(const uint8_t *p,size_t bytes,uint32_t index,
    uint32_t profile,struct power_extent *out)
{
    struct power_extent value={0};
    uint32_t header,offset,count,result=POWER_OK;
    if (!out) return POWER_ARGUMENT;
    if (!p || index>=POWER_DVFS_DOMAINS) result=POWER_ARGUMENT;
    else if (profile!=POWER_SOURCE_S5E9945) result=POWER_UNAVAILABLE;
    else if (bytes!=POWER_FVMAP_COPY_BYTES) result=POWER_LENGTH;
    else {
        header=index*52; /* actual public struct size, independently compiled */
        offset=(uint32_t)p[header+20]|((uint32_t)p[header+21]<<8);
        count=p[header+1];
        if (!count) result=POWER_UNAVAILABLE;
        else if (offset<POWER_DVFS_DOMAINS*52 || offset>bytes || count*4>bytes-offset)
            result=POWER_LENGTH;
        else {
            value.selected_index=index; value.reported_domain=p[header];
            value.levels=count; value.offset=offset; value.bytes=count*4;
        }
    }
    *out=value;
    return result;
}
uint32_t power_decode_tmu(const uint8_t *p,size_t bytes,uint32_t zone,
    uint32_t unit,struct power_value *out)
{
    struct power_value value={0};
    uint32_t result=POWER_OK;
    if (!out) return POWER_ARGUMENT;
    if (!p || zone>=POWER_TMU_ZONES) result=POWER_ARGUMENT;
    else if (bytes!=POWER_MESSAGE_BYTES) result=POWER_LENGTH;
    else if (unit!=POWER_CELSIUS_U8) result=POWER_UNIT;
    else if (p[4]!=2) result=POWER_UNSUPPORTED;
    else if (p[6]!=zone) result=POWER_STALE;
    /* Signed firmware return must be zero; stat/context remain opaque. */
    else if (p[5]) result=POWER_FIRMWARE_ERROR;
    else {
        value.value=(uint64_t)p[7]*1000;
        value.kind=POWER_TMU; value.source_id=zone; value.unit=POWER_MILLI_CELSIUS;
        value.status=p[8];
    }
    *out=value;
    return result;
}
uint32_t power_decode_clock_request(const uint8_t *p,size_t bytes,uint32_t domain,
    uint32_t unit,struct power_value *out)
{
    struct power_value value={0};
    uint32_t result=POWER_OK;
    if (!out) return POWER_ARGUMENT;
    if (!p || domain>1) result=POWER_ARGUMENT;
    else if (bytes!=POWER_MESSAGE_BYTES) result=POWER_LENGTH;
    else if (unit!=POWER_KHZ_U32) result=POWER_UNIT;
    else if (le32(p+8)>1) result=POWER_UNSUPPORTED;
    else if (le32(p+8)!=domain) result=POWER_STALE;
    else if (le32(p+4)==UINT32_MAX) result=POWER_UNAVAILABLE; /* QoS DEFAULT_VALUE=-1 */
    else if (le32(p+4)>INT32_MAX) result=POWER_UNSUPPORTED; /* signed target API */
    else {
        /* Source callback requests QoS in kHz, never measured frequency.
           Nonnegative s32 input multiplied in 64 bits cannot overflow. */
        value.value=(uint64_t)le32(p+4)*1000;
        value.kind=POWER_CLOCK_REQUEST; value.source_id=domain; value.unit=POWER_HZ;
    }
    *out=value;
    return result;
}
static uint32_t policy_valid(const struct power_policy *p)
{
    if (!p || !p->epoch || !p->max_age_ns) return POWER_ARGUMENT;
    if (p->profile!=POWER_SOURCE_S5E9945) return POWER_UNAVAILABLE;
    if (p->kind!=POWER_TMU && p->kind!=POWER_CLOCK_REQUEST) return POWER_UNAVAILABLE;
    if ((p->kind==POWER_TMU && p->source_id>=POWER_TMU_ZONES) ||
        (p->kind==POWER_CLOCK_REQUEST && p->source_id>1)) return POWER_ARGUMENT;
    return POWER_OK;
}
uint32_t power_observer_init(struct power_observer *s,const struct power_policy *p)
{
    struct power_observer value={0};
    uint32_t result;
    if (!s) return POWER_ARGUMENT;
    result=policy_valid(p);
    if (result) { *s=value; return result; }
    value.policy=*p; value.ticket.epoch=p->epoch; *s=value;
    return POWER_OK;
}
static uint32_t invalidate(struct power_observer *s,uint32_t result)
{
    s->waiting=0; s->valid=0; s->last_error=result;
    return result;
}
uint32_t power_observer_begin(struct power_observer *s,uint64_t now)
{
    uint32_t result;
    if (!s) return POWER_ARGUMENT;
    result=policy_valid(&s->policy); if (result) return result;
    if (s->stopped) return POWER_STOPPED;
    if (s->waiting) return POWER_BUSY;
    if (!now || now<s->last_ns) return invalidate(s,POWER_CLOCK);
    if (s->policy.max_age_ns>UINT64_MAX-now) return invalidate(s,POWER_OVERFLOW);
    if (s->ticket.generation==UINT32_MAX) return invalidate(s,POWER_EXHAUSTED);
    s->ticket.generation++; s->start_ns=now; s->deadline_ns=now+s->policy.max_age_ns;
    s->last_ns=now; s->waiting=1; s->valid=0; s->last_error=0;
    return POWER_OK;
}
uint32_t power_observer_accept(struct power_observer *s,const struct power_ticket *ticket,
    const uint8_t *p,size_t bytes,uint32_t unit,uint32_t transport,uint64_t sampled,uint64_t now)
{
    struct power_value value;
    uint32_t result;
    if (!s || !ticket || !s->policy.epoch) return POWER_ARGUMENT;
    if (s->stopped) return POWER_STOPPED;
    if (!s->waiting || !ticket->generation || ticket->epoch!=s->ticket.epoch ||
        ticket->generation!=s->ticket.generation) return POWER_STALE;
    if (!now || now<s->last_ns) return invalidate(s,POWER_CLOCK);
    s->last_ns=now;
    if (now>=s->deadline_ns) return invalidate(s,POWER_STALE);
    if (transport==POWER_TRANSPORT_MISSING) return invalidate(s,POWER_UNAVAILABLE);
    if (transport==POWER_TRANSPORT_FAILED) return invalidate(s,POWER_TRANSPORT_ERROR);
    if (transport!=POWER_TRANSPORT_OK) return invalidate(s,POWER_ARGUMENT);
    if (!sampled || sampled<s->start_ns || sampled>now) return invalidate(s,POWER_CLOCK);
    if (now-sampled>=s->policy.max_age_ns) return invalidate(s,POWER_STALE);
    result=s->policy.kind==POWER_TMU ?
        power_decode_tmu(p,bytes,s->policy.source_id,unit,&value) :
        power_decode_clock_request(p,bytes,s->policy.source_id,unit,&value);
    if (result) return invalidate(s,result);
    s->sample=value; s->sample_ns=sampled; s->valid=1; s->waiting=0; s->last_error=0;
    return POWER_OK;
}
uint32_t power_observer_read(struct power_observer *s,uint64_t now,struct power_value *out)
{
    struct power_value empty={0},value;
    if (!out) return POWER_ARGUMENT;
    if (!s) { *out=empty; return POWER_ARGUMENT; }
    value=s->sample;
    *out=empty;
    if (!s->policy.epoch) return POWER_ARGUMENT;
    if (s->stopped) return POWER_STOPPED;
    if (!now || now<s->last_ns) return invalidate(s,POWER_CLOCK);
    s->last_ns=now;
    if (s->waiting && now>=s->deadline_ns) return invalidate(s,POWER_STALE);
    if (!s->valid) return POWER_UNAVAILABLE;
    if (now<s->sample_ns) return invalidate(s,POWER_CLOCK);
    if (now-s->sample_ns>=s->policy.max_age_ns) return invalidate(s,POWER_STALE);
    *out=value;
    return POWER_OK;
}
uint32_t power_observer_stop(struct power_observer *s)
{
    if (!s || !s->policy.epoch) return POWER_ARGUMENT;
    s->stopped=1; s->waiting=0; s->valid=0; s->last_error=POWER_STOPPED;
    return POWER_OK;
}
