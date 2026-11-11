/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * Host-test port of the engine's hardware contract (see engine/usbmon_port.h). Everything is implemented in model.c: MMIO
 * goes to a simulated DWC3 device controller, DMA memory goes through a simulated non-coherent cache. Nothing here is the
 * loader's port, and none of it models anything but the behaviour documented in README.md.
 */
#ifndef USBMON_HOST_PORT_H
#define USBMON_HOST_PORT_H
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
