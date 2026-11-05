/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Owned host-only boundary; selected Samsung ABOX declarations are attributed
 * to Linux source417484173abc2c4fa93e738ea82ad9f2e84911b1. No DSP submission. */
#ifndef S24_PCM_HOST_H
#define S24_PCM_HOST_H
#include <stddef.h>
#include <stdint.h>

#define PCM_AP_MESSAGE_BYTES 768u
#define PCM_HOST_MAX_PERIODS 32u /* owned fixed ownership-table limit */
enum pcm_direction { PCM_HOST_PLAYBACK, PCM_HOST_CAPTURE };
enum pcm_result { PCM_OK, PCM_INVALID, PCM_STALE, PCM_STATE, PCM_BUSY, PCM_DUPLICATE, PCM_LIMIT };
enum pcm_state { PCM_IDLE, PCM_READY, PCM_RUNNING, PCM_STOPPING, PCM_FAULT, PCM_QUIESCENT };

struct pcm_mapping { uint64_t iova, bytes; };
struct pcm_plan {
    uint32_t direction, channel, iova, period_bytes, periods;
    uint32_t rate, bits, channels, packed, frame_bytes;
    uint64_t ring_bytes, mapping_bytes;
};
/* Local host tokens: these fields do NOT exist in the donor IPC message.
 * A future serialized provider must associate callbacks with the live mapping
 * and drain old firmware traffic; the model is not wire replay protection. */
struct pcm_stamp { uint64_t epoch, sequence, stop_serial; };
struct pcm_lease { uint64_t epoch, serial; uint32_t slot, offset, bytes; };
struct pcm_stop_token { uint64_t epoch, serial; };
struct pcm_host {
    struct pcm_plan plan;
    uint64_t epoch, issued, dispatch, notifications, stop_serial;
    uint64_t slot_serial[PCM_HOST_MAX_PERIODS];
    uint32_t state, leased, closed;
    int32_t error;
};

/* Externally serialized calls. Input is an AP-side ABOX_IPC_MSG snapshot,
 * not an asserted raw DSP queue/wire ABI. Only ordinary DMA channel0 is in
 * this deliberately narrow profile; sync/RAM/ION/compressed paths are absent. */
int pcm_admit_plan(const void *set_buffer, size_t set_size,
                   const void *hw_params, size_t hw_size,
                   struct pcm_mapping mapping, struct pcm_plan *out);
int pcm_offset_frames(const struct pcm_plan *plan, uint32_t absolute_iova, uint64_t *out);
void pcm_host_init(struct pcm_host *host);
int pcm_host_bind(struct pcm_host *host, const struct pcm_plan *plan, uint64_t epoch);
int pcm_host_start(struct pcm_host *host, uint64_t epoch);
int pcm_host_claim(struct pcm_host *host, uint64_t epoch, uint32_t slot, struct pcm_lease *out);
int pcm_host_retire(struct pcm_host *host, const struct pcm_lease *lease, int32_t result);
int pcm_host_event(struct pcm_host *host, struct pcm_stamp stamp,
                   const void *message, size_t bytes, uint64_t *frames);
int pcm_host_fault(struct pcm_host *host, uint64_t epoch, int32_t error);
int pcm_host_stop(struct pcm_host *host, uint64_t epoch, struct pcm_stop_token *out);
/* This call is a future provider's explicit DMA AND old-callback-quiescence
 * attestation. A source CLOSED notification alone proves neither condition. */
int pcm_host_provider_fenced(struct pcm_host *host, struct pcm_stop_token token);
int pcm_host_release(struct pcm_host *host, uint64_t epoch);
#endif
