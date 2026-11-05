/* Owned synthetic host fixture. Callback stubs count accidental execution;
 * they implement no real platform service and are never hardware evidence. */
#include "e1s_wifi.h"
#include <stdio.h>
#include <string.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"check failed at %d: %s\n",__LINE__,#c); return 1; } } while (0)
static unsigned calls;
static uint64_t clock_stub(void) { ++calls; return 0; }
static void delay_stub(unsigned n) { (void)n; ++calls; }
static void void_stub(void) { ++calls; }
static void log_stub(int n, const char *s) { (void)n; (void)s; ++calls; }
static void *alloc_stub(size_t n) { (void)n; ++calls; return NULL; }
static void free_stub(void *p) { (void)p; ++calls; }
static void *dma_alloc_stub(size_t n, uint64_t *b) { (void)n; (void)b; ++calls; return NULL; }
static void dma_free_stub(size_t n, void *p, uint64_t b) { (void)n; (void)p; (void)b; ++calls; }
static uint64_t dma_map_stub(void *p, size_t n, int d) { (void)p; (void)n; (void)d; ++calls; return 0; }
static void dma_sync_stub(uint64_t b, size_t n, int d) { (void)b; (void)n; (void)d; ++calls; }
static int fw_stub(const char *s, const uint8_t **p, size_t *n) { (void)s; (void)p; (void)n; ++calls; return -1; }
static int cfg_read_stub(int o, int n, uint32_t *v) { (void)o; (void)n; (void)v; ++calls; return -1; }
static int cfg_write_stub(int o, int n, uint32_t v) { (void)o; (void)n; (void)v; ++calls; return -1; }
static int msi_stub(uint32_t *l, uint32_t *h, uint32_t *d) { (void)l; (void)h; (void)d; ++calls; return -1; }

int main(void)
{
    struct lx_platform p = { clock_stub, delay_stub, void_stub, log_stub, void_stub, alloc_stub, free_stub,
        dma_alloc_stub, dma_free_stub, dma_map_stub, dma_sync_stub, fw_stub, clock_stub, clock_stub, delay_stub, void_stub, void_stub };
    struct nw_board b = { (void *)(uintptr_t)0x500000, 0x100000, 0x1107, 0x50, 1000, cfg_read_stub, cfg_write_stub, msi_stub, NULL };
    struct e1s_wifi_profile profile = { E1S_WIFI_SYNTHETIC, E1S_WIFI_REQUIRED_FACTS, 0x17cb, 0x1107, 4096, 16, 32 };
    struct e1s_wifi_dma_window w = { 0x200000, 0x90000000, 16384 };
    struct e1s_wifi_binding out;
    uint64_t bus;
    unsigned i;
    CHECK(e1s_wifi_prepare(NULL, &w, &p, &b, &out) == E1S_WIFI_UNKNOWN_PROFILE);
    CHECK(out.origin == 0 && out.board.bar == NULL && out.platform.dma_map == NULL);
    for (i = 0; i < 9; ++i) {
        profile.facts = E1S_WIFI_REQUIRED_FACTS & ~(1u << i);
        CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_UNKNOWN_PROFILE);
    }
    profile.facts = E1S_WIFI_REQUIRED_FACTS;
    profile.device = 0x1103;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_UNSUPPORTED_ID);
    profile.device = 0x1107;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_VALID && out.origin == E1S_WIFI_SYNTHETIC);
    profile.cpu_vm_page = 16384;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_VALID);
    p.preempt_enable = NULL;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_MISSING_CALLBACK);
    CHECK(out.origin == 0 && out.board.bar == NULL);
    p.preempt_enable = void_stub;
    profile.msi_vectors = 32;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_BAD_BOARD);
    profile.msi_vectors = 16; profile.controller_msi_capacity = 8;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_BAD_BOARD);
    profile.controller_msi_capacity = 32;
    b.msi_cap = 0x51;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_BAD_BOARD);
    b.msi_cap = 0x50;
    b.irq_base = INT32_MAX;
    CHECK(e1s_wifi_prepare(&profile, &w, &p, &b, &out) == E1S_WIFI_BAD_BOARD);
    for (i = 0; i < w.bytes; ++i) {
        CHECK(e1s_wifi_translate(&w, w.cpu_start + i, w.bytes - i, &bus) == E1S_WIFI_VALID);
        CHECK(bus == w.bus_start + i);
        CHECK(e1s_wifi_translate(&w, w.cpu_start + i, w.bytes - i + 1, &bus) == E1S_WIFI_BAD_DMA && bus == 0);
    }
    CHECK(e1s_wifi_translate(&w, w.cpu_start - 1, 1, &bus) == E1S_WIFI_BAD_DMA && bus == 0);
    CHECK(e1s_wifi_translate(&w, w.cpu_start + w.bytes, 1, &bus) == E1S_WIFI_BAD_DMA);
    CHECK(e1s_wifi_translate(&w, w.cpu_start, SIZE_MAX, &bus) == E1S_WIFI_BAD_DMA);
    CHECK(e1s_wifi_translate(&w, w.cpu_start, 0, &bus) == E1S_WIFI_BAD_DMA);
    w.bus_start = UINT64_MAX - 10;
    CHECK(e1s_wifi_translate(&w, w.cpu_start, 1, &bus) == E1S_WIFI_BAD_DMA);
    w.bus_start = 0x90000000; w.cpu_start = UINTPTR_MAX - 10;
    CHECK(e1s_wifi_translate(&w, w.cpu_start, 1, &bus) == E1S_WIFI_BAD_DMA);
    CHECK(calls == 0);
    printf("{\"outcome\":\"pass\",\"environment\":\"synthetic-wifi-binding\",\"range_pairs\":16384,\"callback_calls\":0,\"device_io\":false}\n");
    return 0;
}
