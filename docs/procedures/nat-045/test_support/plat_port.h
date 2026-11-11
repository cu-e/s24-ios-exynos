/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-test port for the NAT-045 ladder: MMIO goes to plat.c (a register file with a power-domain gate, an access log and
 * fault injection; the DWC3 window is forwarded to the NAT-041 model), DMA memory to the NAT-041 simulated cache. Not the
 * loader's port (that is NAT-041's port_aarch64.h, which the aarch64 test layer compiles unchanged). */
#ifndef PLAT_PORT_H
#define PLAT_PORT_H
#include <stddef.h>
#include <stdint.h>

uint32_t usbmon_rd32(uintptr_t addr);
void usbmon_wr32(uintptr_t addr, uint32_t v);
void usbmon_delay_us(uint32_t us);
uint64_t usbmon_ticks(void);
uint32_t usbmon_dma_ld32(const volatile void *p);
void usbmon_dma_st32(volatile void *p, uint32_t v);
void usbmon_dma_read(void *dst, const volatile void *src, size_t n);
void usbmon_dma_write(volatile void *dst, const void *src, size_t n);
void usbmon_dma_sync(const volatile void *p, size_t n);
uint64_t usbmon_dma_addr(const volatile void *p);
#endif
