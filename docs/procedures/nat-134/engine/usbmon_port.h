/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * The hardware contract of the engine. usbmon.c touches the platform only through the functions below; a port header
 * provides them. The default is port_aarch64.h (loader build); the host tests define USBMON_PORT_HEADER to the model's
 * port, which implements them on a simulated DWC3 and a simulated non-coherent cache.
 *
 *   uint32_t usbmon_rd32(uintptr_t addr)              32-bit MMIO read, device-ordered
 *   void     usbmon_wr32(uintptr_t addr, uint32_t v)  32-bit MMIO write, device-ordered
 *   void     usbmon_delay_us(uint32_t us)
 *   uint64_t usbmon_ticks(void)                       free-running counter, reported in GET_INFO
 *
 * DMA memory (the struct usbmon_dma block). The controller reads and writes it behind the CPU's back; the engine never
 * dereferences it directly:
 *   uint32_t usbmon_dma_ld32(const volatile void *p)
 *   void     usbmon_dma_st32(volatile void *p, uint32_t v)
 *   void     usbmon_dma_read(void *dst, const volatile void *src, size_t n)      DMA memory -> ordinary memory
 *   void     usbmon_dma_write(volatile void *dst, const void *src, size_t n)     ordinary memory -> DMA memory
 *   void     usbmon_dma_sync(const volatile void *p, size_t n)  clean AND invalidate every cache line of [p, p+n), then a
 *                                                               full barrier: the CPU's stores reach memory and the
 *                                                               CPU's next load comes from memory
 *   uint64_t usbmon_dma_addr(const volatile void *p)           the address the controller must use for p
 *
 * Receive destination (NAT-076; ordinary RAM outside the DMA block, written by the controller only in direct mode):
 *   void     usbmon_dest_sync(const void *p, size_t n)         clean AND invalidate [p, p+n), then a full barrier
 *   uint64_t usbmon_dest_ld64(const void *p)                   one 64-bit CPU load of destination memory
 *   uint64_t usbmon_dest_addr(const void *p)                   the address the controller must use for p
 *
 * NAT-130 (checksum modes and phase timing):
 *   uint64_t usbmon_freq(void)                                 ticks of usbmon_ticks() per second
 *   USBMON_PORT_SUM_CAPS                                       bit m set: checksum mode m (1 FAST, 2 CACHED) is implemented
 *   uint64_t usbmon_dest_sum_fast(const void *p, size_t n)     usbmon_rx_sum() of a synced range, faster loads; p 64-byte
 *                                                              aligned, n a multiple of 512
 *   uint64_t usbmon_dest_sum_cached(const void *p, size_t n)   the same with the range temporarily readable through the
 *                                                              cache; leaves no line of the range (or of anything else it
 *                                                              mapped) in the cache, and the translation state as found
 *
 * NAT-134 (read-only register probe):
 *   uint32_t usbmon_peek32(uintptr_t addr)                     one 32-bit device-ordered read of a peek-table address
 */
#ifndef USBMON_PORT_H
#define USBMON_PORT_H
#ifdef USBMON_PORT_HEADER
#include USBMON_PORT_HEADER
#else
#include "port_aarch64.h"
#endif
#endif
