/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "pcm_host.h"

enum { IPC_PLAY = 2, IPC_CAPTURE = 3, SET_BUFFER = 20, HW_PARAMS = 14,
       POINTER = 18, CLOSED = 23 };

static uint32_t u32(const unsigned char *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static int plan_valid(const struct pcm_plan *p)
{
    uint32_t width;
    if (!p || p->direction > PCM_HOST_CAPTURE || p->channel != 0 ||
        p->iova != (p->direction == PCM_HOST_PLAYBACK ? 0x91000000u : 0x92000000u) ||
        !p->rate || p->rate > INT32_MAX || !p->channels || p->channels > 8 || p->packed > 1 ||
        (p->bits != 16 && p->bits != 24 && p->bits != 32) || (p->packed && p->bits != 24))
        return 0;
    width = p->bits == 24 && !p->packed ? 32 : p->bits;
    if (p->frame_bytes != width / 8 * p->channels || p->period_bytes < 16 ||
        p->period_bytes > 0x80000u || p->period_bytes % p->frame_bytes ||
        p->periods < 2 || p->periods > PCM_HOST_MAX_PERIODS ||
        !p->mapping_bytes || p->mapping_bytes > 0x100000u)
        return 0;
    return p->ring_bytes == (uint64_t)p->period_bytes * p->periods &&
        p->ring_bytes <= 0x100000u && p->ring_bytes <= p->mapping_bytes;
}

static int envelope(const void *message, size_t bytes, uint32_t ipcid, uint32_t type, int config)
{
    const unsigned char *p = message;
    return p && bytes == PCM_AP_MESSAGE_BYTES && u32(p) == ipcid && u32(p + 8) == type &&
        u32(p + 12) == 0 && (!config || u32(p + 4) == 0);
}

int pcm_admit_plan(const void *set_buffer, size_t set_size, const void *hw_params,
                   size_t hw_size, struct pcm_mapping mapping, struct pcm_plan *out)
{
    const unsigned char *s = set_buffer, *h = hw_params;
    struct pcm_plan p = {0};
    uint32_t ipcid;
    if (!out || !s || !h || set_size != PCM_AP_MESSAGE_BYTES || hw_size != PCM_AP_MESSAGE_BYTES)
        return PCM_INVALID;
    ipcid = u32(s);
    if (ipcid != IPC_PLAY && ipcid != IPC_CAPTURE) return PCM_INVALID;
    if (!envelope(s, set_size, ipcid, SET_BUFFER, 1) || !envelope(h, hw_size, ipcid, HW_PARAMS, 1))
        return PCM_INVALID;
    p.direction = ipcid == IPC_PLAY ? PCM_HOST_PLAYBACK : PCM_HOST_CAPTURE;
    p.iova = u32(s + 16); p.period_bytes = u32(s + 20); p.periods = u32(s + 24);
    p.rate = u32(h + 16); p.bits = u32(h + 20); p.channels = u32(h + 24); p.packed = u32(h + 28);
    if (p.bits == 16 || p.bits == 24 || p.bits == 32)
        p.frame_bytes = (p.bits == 24 && !p.packed ? 4 : p.bits / 8) * p.channels;
    p.ring_bytes = (uint64_t)p.period_bytes * p.periods;
    p.mapping_bytes = mapping.bytes;
    if (mapping.iova != p.iova || !plan_valid(&p)) return PCM_INVALID;
    *out = p;
    return PCM_OK;
}

int pcm_offset_frames(const struct pcm_plan *p, uint32_t pointer, uint64_t *out)
{
    uint64_t delta;
    if (!out || !plan_valid(p) || pointer < p->iova) return PCM_INVALID;
    delta = (uint64_t)pointer - p->iova;
    if (delta >= p->ring_bytes || delta % p->frame_bytes) return PCM_INVALID;
    *out = delta / p->frame_bytes;
    return PCM_OK;
}

void pcm_host_init(struct pcm_host *h)
{
    if (h) *h = (struct pcm_host){0};
}

int pcm_host_bind(struct pcm_host *h, const struct pcm_plan *p, uint64_t epoch)
{
    if (!h || !plan_valid(p)) return PCM_INVALID;
    if (h->state != PCM_IDLE) return PCM_STATE;
    if (!epoch || epoch <= h->epoch) return PCM_STALE;
    *h = (struct pcm_host){ .plan = *p, .epoch = epoch, .state = PCM_READY,
                           .stop_serial = h->stop_serial };
    return PCM_OK;
}

int pcm_host_start(struct pcm_host *h, uint64_t epoch)
{
    if (!h) return PCM_INVALID;
    if (epoch != h->epoch) return PCM_STALE;
    if (h->state != PCM_READY) return PCM_STATE;
    h->state = PCM_RUNNING;
    return PCM_OK;
}

int pcm_host_claim(struct pcm_host *h, uint64_t epoch, uint32_t slot, struct pcm_lease *out)
{
    uint32_t bit;
    if (!h || !out) return PCM_INVALID;
    if (epoch != h->epoch) return PCM_STALE;
    if (h->state != PCM_RUNNING) return PCM_STATE;
    if (slot >= h->plan.periods) return PCM_INVALID;
    bit = (uint32_t)1 << slot;
    if (h->leased & bit) return PCM_BUSY;
    if (h->issued == UINT64_MAX) return PCM_LIMIT;
    *out = (struct pcm_lease){ .epoch = epoch, .serial = ++h->issued, .slot = slot,
        .offset = slot * h->plan.period_bytes, .bytes = h->plan.period_bytes };
    h->leased |= bit; h->slot_serial[slot] = out->serial;
    return PCM_OK;
}

int pcm_host_retire(struct pcm_host *h, const struct pcm_lease *l, int32_t result)
{
    uint32_t bit;
    if (!h || !l || result > 0) return PCM_INVALID;
    if (l->epoch != h->epoch) return PCM_STALE;
    if (h->state != PCM_RUNNING && h->state != PCM_STOPPING && h->state != PCM_FAULT) return PCM_STATE;
    if (l->slot >= h->plan.periods) return PCM_INVALID;
    bit = (uint32_t)1 << l->slot;
    if (!(h->leased & bit)) return PCM_DUPLICATE;
    if (!l->serial || h->slot_serial[l->slot] != l->serial) return PCM_STALE;
    if (l->offset != l->slot * h->plan.period_bytes || l->bytes != h->plan.period_bytes) return PCM_INVALID;
    h->leased &= ~bit; h->slot_serial[l->slot] = 0;
    if (result < 0) { h->state = PCM_FAULT; h->error = result; h->closed = 0; }
    return PCM_OK;
}

int pcm_host_event(struct pcm_host *h, struct pcm_stamp stamp,
                   const void *message, size_t bytes, uint64_t *frames)
{
    const unsigned char *p = message;
    uint32_t type, ipcid;
    uint64_t value;
    if (!h || !p || bytes != PCM_AP_MESSAGE_BYTES) return PCM_INVALID;
    if (stamp.epoch != h->epoch) return PCM_STALE;
    if (!stamp.sequence || stamp.sequence <= h->dispatch) return PCM_DUPLICATE;
    type = u32(p + 8); ipcid = h->plan.direction == PCM_HOST_PLAYBACK ? IPC_PLAY : IPC_CAPTURE;
    if (!envelope(p, bytes, ipcid, type, 0)) return PCM_INVALID;
    if (type == POINTER) {
        if (h->state != PCM_RUNNING || stamp.stop_serial) return PCM_STATE;
        if (!frames || pcm_offset_frames(&h->plan, u32(p + 16), &value) != PCM_OK) return PCM_INVALID;
        if (h->notifications == UINT64_MAX) return PCM_LIMIT;
        *frames = value; ++h->notifications;
    } else if (type == CLOSED) {
        if (h->state != PCM_STOPPING) return PCM_STATE;
        if (!stamp.stop_serial || stamp.stop_serial != h->stop_serial) return PCM_STALE;
        if (h->closed) return PCM_DUPLICATE;
        h->closed = 1;
    } else return PCM_INVALID;
    h->dispatch = stamp.sequence;
    return PCM_OK;
}

int pcm_host_fault(struct pcm_host *h, uint64_t epoch, int32_t error)
{
    if (!h || error >= 0) return PCM_INVALID;
    if (epoch != h->epoch) return PCM_STALE;
    if (h->state != PCM_RUNNING && h->state != PCM_READY && h->state != PCM_STOPPING && h->state != PCM_FAULT)
        return PCM_STATE;
    h->state = PCM_FAULT; h->error = error; h->closed = 0;
    return PCM_OK;
}

int pcm_host_stop(struct pcm_host *h, uint64_t epoch, struct pcm_stop_token *out)
{
    if (!h || !out) return PCM_INVALID;
    if (epoch != h->epoch) return PCM_STALE;
    if (h->state != PCM_RUNNING && h->state != PCM_READY && h->state != PCM_FAULT && h->state != PCM_STOPPING)
        return PCM_STATE;
    if (h->state != PCM_STOPPING) {
        if (h->stop_serial == UINT64_MAX) return PCM_LIMIT;
        ++h->stop_serial; h->closed = 0; h->state = PCM_STOPPING;
    }
    *out = (struct pcm_stop_token){ epoch, h->stop_serial };
    return PCM_OK;
}

int pcm_host_provider_fenced(struct pcm_host *h, struct pcm_stop_token token)
{
    if (!h) return PCM_INVALID;
    if (token.epoch != h->epoch || !token.serial || token.serial != h->stop_serial) return PCM_STALE;
    if (h->state != PCM_STOPPING) return PCM_STATE;
    if (!h->closed || h->leased) return PCM_BUSY;
    h->state = PCM_QUIESCENT;
    return PCM_OK;
}

int pcm_host_release(struct pcm_host *h, uint64_t epoch)
{
    uint64_t serial;
    if (!h) return PCM_INVALID;
    if (epoch != h->epoch) return PCM_STALE;
    if (h->state != PCM_QUIESCENT || h->leased) return PCM_BUSY;
    serial = h->stop_serial;
    *h = (struct pcm_host){ .epoch = epoch, .stop_serial = serial };
    return PCM_OK;
}
