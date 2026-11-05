/* Independent field/range checks; this file calls no donor or board function. */
#include "e1s_wifi.h"

/* These assertions deliberately reject the stale catalog ABI. Pointer tables
 * are an in-process interface for the selected 64-bit targets, never wire data. */
#if defined(__cplusplus)
#define E1S_ASSERT(c) static_assert(c, #c)
#else
#define E1S_ASSERT(c) _Static_assert(c, #c)
#endif
E1S_ASSERT(sizeof(void *) == 8 && sizeof(size_t) == 8);
E1S_ASSERT(sizeof(struct lx_platform) == 136);
E1S_ASSERT(offsetof(struct lx_platform, preempt_enable) == 128);
E1S_ASSERT(sizeof(struct nw_board) == 56);
E1S_ASSERT(sizeof(struct nw_wifi_events) == 56);
E1S_ASSERT(offsetof(struct nw_wifi_events, link_update) == 48);

static int window_valid(const struct e1s_wifi_dma_window *w)
{
    return w && w->cpu_start && w->bus_start && w->bytes &&
        w->bytes <= UINTPTR_MAX - w->cpu_start && w->bytes <= UINT64_MAX - w->bus_start;
}

uint32_t e1s_wifi_translate(const struct e1s_wifi_dma_window *w, uintptr_t cpu, size_t bytes, uint64_t *bus)
{
    uintptr_t offset;
    if (!bus) return E1S_WIFI_BAD_DMA;
    *bus = 0;
    if (!window_valid(w) || !bytes || cpu < w->cpu_start) return E1S_WIFI_BAD_DMA;
    offset = cpu - w->cpu_start;
    if (offset >= w->bytes || bytes > w->bytes - offset) return E1S_WIFI_BAD_DMA;
    *bus = w->bus_start + offset;
    return E1S_WIFI_VALID;
}

uint32_t e1s_wifi_prepare(const struct e1s_wifi_profile *profile, const struct e1s_wifi_dma_window *dma,
                        const struct lx_platform *platform, const struct nw_board *board, struct e1s_wifi_binding *out)
{
    struct e1s_wifi_binding empty = {0};
    if (!out) return E1S_WIFI_UNKNOWN_PROFILE;
    *out = empty;
    /* The caller supplies trusted records; a bitmask cannot establish their
     * truth or grant hardware authorization. The public S24 profile is unknown. */
    if (!profile || (profile->origin != E1S_WIFI_SYNTHETIC && profile->origin != E1S_WIFI_RECORDED_INPUTS) ||
        profile->facts != E1S_WIFI_REQUIRED_FACTS) return E1S_WIFI_UNKNOWN_PROFILE;
    if (profile->vendor != 0x17cb || profile->device != 0x1107) return E1S_WIFI_UNSUPPORTED_ID;
    if ((profile->cpu_vm_page != 4096 && profile->cpu_vm_page != 16384) || !window_valid(dma) ||
        dma->cpu_start % profile->cpu_vm_page || dma->bytes % profile->cpu_vm_page || dma->bus_start % 4096) return E1S_WIFI_BAD_DMA;
    if (!board || !board->bar || !board->bar_len || board->device_id != profile->device ||
        board->msi_cap < 0x40 || board->msi_cap > 0xfc || board->msi_cap % 4 ||
        board->irq_base < 0 || board->irq_base > INT32_MAX - 15 || profile->msi_vectors != 16 ||
        profile->controller_msi_capacity < 16 || profile->controller_msi_capacity > 32) return E1S_WIFI_BAD_BOARD;
    if (!platform || !platform->now_ms || !platform->sleep_ms || !platform->poll || !platform->log || !platform->halt ||
        !platform->alloc || !platform->free || !platform->dma_alloc || !platform->dma_free || !platform->dma_map ||
        !platform->dma_sync || !platform->fw_get || !platform->now_ns || !platform->boottime_ns || !platform->busy_delay_us ||
        !platform->preempt_disable || !platform->preempt_enable || !board->cfg_read || !board->cfg_write || !board->msi_target) return E1S_WIFI_MISSING_CALLBACK;
    /* map_phys is optional in the pinned reference. No callback is invoked and
     * no nw_wifi_start call occurs; out only describes a structural binding. */
    out->platform = *platform; out->board = *board; out->dma = *dma; out->origin = profile->origin;
    return E1S_WIFI_VALID;
}
