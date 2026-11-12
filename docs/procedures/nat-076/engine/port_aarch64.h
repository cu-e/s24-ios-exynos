/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * The loader-side port: AArch64 EL1, identity mapped (virtual address == bus address for the engine's DMA block).
 * `dc civac` cleans and invalidates by virtual address to the point of coherency, which is correct whether the block is
 * mapped cacheable (the line is written back, then dropped) or not (the instruction is then a no-op for memory).
 * Nothing here has run on the phone (NAT-041 and NAT-076 are host work).
 */
#ifndef USBMON_PORT_AARCH64_H
#define USBMON_PORT_AARCH64_H
#include <stddef.h>
#include <stdint.h>

static inline uint32_t usbmon_rd32(uintptr_t addr)
{
	uint32_t v = *(volatile uint32_t *)addr;
	__asm__ volatile("" ::: "memory");
	return v;
}

static inline void usbmon_wr32(uintptr_t addr, uint32_t v)
{
	__asm__ volatile("dmb oshst" ::: "memory");	/* earlier stores to DMA memory are visible before the doorbell */
	*(volatile uint32_t *)addr = v;
	__asm__ volatile("dsb sy" ::: "memory");
}

static inline uint64_t usbmon_ticks(void)
{
	uint64_t t;
	__asm__ volatile("isb; mrs %0, cntpct_el0" : "=r"(t) :: "memory");
	return t;
}

static inline void usbmon_delay_us(uint32_t us)
{
	uint64_t freq, start, ticks;
	__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(freq));
	ticks = (freq / 1000000u) * us;
	if (!ticks)
		ticks = 1;
	start = usbmon_ticks();
	while (usbmon_ticks() - start < ticks)
		;
}

static inline uint32_t usbmon_dma_ld32(const volatile void *p) { return *(const volatile uint32_t *)p; }
static inline void usbmon_dma_st32(volatile void *p, uint32_t v) { *(volatile uint32_t *)p = v; }

static inline void usbmon_dma_read(void *dst, const volatile void *src, size_t n)
{
	uint8_t *d = dst;
	const volatile uint8_t *s = src;
	while (n--)
		*d++ = *s++;
}

static inline void usbmon_dma_write(volatile void *dst, const void *src, size_t n)
{
	volatile uint8_t *d = dst;
	const uint8_t *s = src;
	while (n--)
		*d++ = *s++;
}

static inline void usbmon_dma_sync(const volatile void *p, size_t n)
{
	uint64_t ctr;
	uintptr_t line, a, end = (uintptr_t)p + n;

	__asm__ volatile("mrs %0, ctr_el0" : "=r"(ctr));
	line = 4UL << ((ctr >> 16) & 0xf);	/* CTR_EL0.DminLine: log2 of words */
	for (a = (uintptr_t)p & ~(line - 1); a < end; a += line)
		__asm__ volatile("dc civac, %0" :: "r"(a) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
}

static inline uint64_t usbmon_dma_addr(const volatile void *p) { return (uint64_t)(uintptr_t)p; }

/* NAT-076: the receive destination (ordinary RAM outside the DMA block). Direct mode lets the controller write it, so the CPU
 * must clean+invalidate before arming and invalidate before reading what the controller wrote. */
static inline void usbmon_dest_sync(const void *p, size_t n) { usbmon_dma_sync((const volatile void *)p, n); }
static inline uint64_t usbmon_dest_ld64(const void *p) { return *(const volatile uint64_t *)p; }
static inline uint64_t usbmon_dest_addr(const void *p) { return (uint64_t)(uintptr_t)p; }
#endif
