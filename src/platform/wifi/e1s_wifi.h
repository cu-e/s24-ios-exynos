/* Project-owned admission/DMA boundary; external donor header is not vendored.
 * No power, PCI configuration, register, firmware or network operation here. */
#ifndef E1S_WIFI_H
#define E1S_WIFI_H
#include <stddef.h>
#include <stdint.h>
#include "nw_abi.h"

#define E1S_WIFI_DONOR_REV "28de7b91d7a880682b777e0e3564245a99dbc3f5"
enum e1s_wifi_status { E1S_WIFI_VALID = 0, E1S_WIFI_UNKNOWN_PROFILE = 1, E1S_WIFI_UNSUPPORTED_ID = 2, E1S_WIFI_BAD_DMA = 3, E1S_WIFI_MISSING_CALLBACK = 4, E1S_WIFI_BAD_BOARD = 5 };
enum e1s_wifi_origin { E1S_WIFI_SYNTHETIC = 1, E1S_WIFI_RECORDED_INPUTS = 2 };
enum e1s_wifi_fact {
    E1S_WIFI_ENDPOINT_RECORDED = 1, E1S_WIFI_REVISION_MATCHED = 2,
    E1S_WIFI_FIRMWARE_MATCHED = 4, E1S_WIFI_BOARD_DATA_MATCHED = 8,
    E1S_WIFI_PCIE_MAP_REVIEWED = 16, E1S_WIFI_DMA_MAP_REVIEWED = 32,
    E1S_WIFI_IRQ_ROUTE_REVIEWED = 64, E1S_WIFI_CACHE_REVIEWED = 128,
    E1S_WIFI_REGULATORY_MATCHED = 256
};
#define E1S_WIFI_REQUIRED_FACTS 511u
/* CPU virtual address and endpoint bus/IOVA are distinct. No inference about
 * physical addresses or identity IOMMU mappings is made by this structure. */
struct e1s_wifi_dma_window { uintptr_t cpu_start; uint64_t bus_start; size_t bytes; };
struct e1s_wifi_profile {
    uint32_t origin, facts;
    uint16_t vendor, device;
    uint32_t cpu_vm_page, msi_vectors, controller_msi_capacity;
};
struct e1s_wifi_binding {
    struct lx_platform platform;
    struct nw_board board;
    struct e1s_wifi_dma_window dma;
    uint32_t origin;
};
#if defined(__cplusplus)
extern "C" {
#endif
uint32_t e1s_wifi_translate(const struct e1s_wifi_dma_window *, uintptr_t, size_t, uint64_t *);
uint32_t e1s_wifi_prepare(const struct e1s_wifi_profile *, const struct e1s_wifi_dma_window *,
                        const struct lx_platform *, const struct nw_board *, struct e1s_wifi_binding *);
#if defined(__cplusplus)
}
#endif
#endif
