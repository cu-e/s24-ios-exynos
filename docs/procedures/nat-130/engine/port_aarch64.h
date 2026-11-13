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

#ifdef USBMON_ENGINE_TU	/* only usbmon.c defines the NAT-130 port code (the loader's other units include this header too) */
/* ---- NAT-130: phase timing and checksum modes ---------------------------------------------------------------------------- */

static inline uint64_t usbmon_freq(void)
{
	uint64_t f;
	__asm__ volatile("mrs %0, cntfrq_el0" : "=r"(f));
	return f;
}

#define USBMON_PORT_SUM_CAPS	((1u << 1) | (1u << 2))

/* Mode FAST: the same sum with four independent pair loads per 64 bytes (the loader runs with SCTLR_EL1.M = 0, so every load
 * is a Device-nGnRnE access; this only lets the core issue them back to back). p 64-byte aligned, n a multiple of 64. */
static inline uint64_t usbmon_dest_sum_fast(const void *p, size_t n)
{
	const uint8_t *q = p;
	uint64_t s0 = 0, s1 = 0, i, k;

	for (i = 0; i < n / 8; i += 8) {
		uint64_t a, b, c, d, e, f, g, h;

		__asm__ volatile("ldp %0, %1, [%8]\n\tldp %2, %3, [%8, #16]\n\tldp %4, %5, [%8, #32]\n\tldp %6, %7, [%8, #48]"
				 : "=&r"(a), "=&r"(b), "=&r"(c), "=&r"(d), "=&r"(e), "=&r"(f), "=&r"(g), "=&r"(h)
				 : "r"(q + 8 * i) : "memory");
		k = 2 * i + 1;
		s0 += a * k + c * (k + 4) + e * (k + 8) + g * (k + 12);
		s1 += b * (k + 2) + d * (k + 6) + f * (k + 10) + h * (k + 14);
	}
	return s0 + s1;
}

/* Mode CACHED. For one sum the range is mapped read-only Normal write-back through a private stage-1 table of 4 KiB pages
 * (identity, nothing else mapped but the one page holding n130_vectors + n130_sum_mmu), the MMU and data cache are switched
 * on, the range is summed, MMU and cache are switched back off, and every line of the range and of that code page is cleaned
 * and invalidated. Table walks are non-cacheable, so no table line is ever cached. A synchronous exception inside the
 * window lands in n130_vectors, which switches the MMU off and continues at the loader's own vector (x16/x17 clobbered).
 * Interrupts are masked in the loader. Falls back to FAST when the range does not fit the tables or the MMU was already on. */
#define N130_L2N	3
#define N130_L3N	7
struct n130_ctx {
	uint64_t ttbr0, tcr, mair, vbar;
};
static uint64_t n130_l1[512] __attribute__((aligned(4096)));
static uint64_t n130_l2[N130_L2N][512] __attribute__((aligned(4096)));
static uint64_t n130_l3[N130_L3N][512] __attribute__((aligned(4096)));
static uint64_t n130_l2_of[N130_L2N], n130_l3_of[N130_L3N];
static unsigned int n130_l2_used, n130_l3_used;
static uint32_t n130_fallbacks;
extern const uint8_t n130_page[];
uint64_t n130_sum_mmu(const void *p, size_t n, const struct n130_ctx *c);

__asm__(
	".pushsection .text.n130, \"ax\"\n"
	".balign 4096\n"
	".globl n130_page\n"
	"n130_page:\n"
	".macro n130_vec off\n"
	".balign 128\n"
	"	mrs x17, sctlr_el1\n"
	"	bic x17, x17, #1\n"
	"	bic x17, x17, #4\n"
	"	msr sctlr_el1, x17\n"
	"	isb\n"
	"	mrs x16, tpidrro_el0\n"
	"	msr vbar_el1, x16\n"
	"	isb\n"
	"	add x16, x16, #\\off\n"
	"	br x16\n"
	".endm\n"
	"	n130_vec 0x000\n n130_vec 0x080\n n130_vec 0x100\n n130_vec 0x180\n"
	"	n130_vec 0x200\n n130_vec 0x280\n n130_vec 0x300\n n130_vec 0x380\n"
	"	n130_vec 0x400\n n130_vec 0x480\n n130_vec 0x500\n n130_vec 0x580\n"
	"	n130_vec 0x600\n n130_vec 0x680\n n130_vec 0x700\n n130_vec 0x780\n"
	".balign 128\n"
	".globl n130_sum_mmu\n"
	"n130_sum_mmu:\n"
	"	ldp x3, x4, [x2]\n"		/* ttbr0, tcr */
	"	ldp x5, x6, [x2, #16]\n"	/* mair, vbar (n130_page) */
	"	add x1, x0, x1\n"		/* end */
	"	mrs x7, sctlr_el1\n"
	"	mrs x8, vbar_el1\n"
	"	mrs x9, tpidrro_el0\n"
	"	mrs x10, ttbr0_el1\n"
	"	mrs x11, tcr_el1\n"
	"	mrs x12, mair_el1\n"
	"	msr tpidrro_el0, x8\n"
	"	msr mair_el1, x5\n"
	"	msr tcr_el1, x4\n"
	"	msr ttbr0_el1, x3\n"
	"	msr vbar_el1, x6\n"
	"	dsb sy\n"
	"	isb\n"
	"	tlbi vmalle1\n"
	"	dsb sy\n"
	"	isb\n"
	"	orr x3, x7, #1\n"
	"	orr x3, x3, #4\n"
	"	msr sctlr_el1, x3\n"
	"	isb\n"
	"	mov x13, #0\n"
	"	mov x14, #1\n"
	"1:	ldp x2, x3, [x0]\n"
	"	ldp x4, x5, [x0, #16]\n"
	"	madd x13, x2, x14, x13\n"
	"	add x14, x14, #2\n"
	"	madd x13, x3, x14, x13\n"
	"	add x14, x14, #2\n"
	"	madd x13, x4, x14, x13\n"
	"	add x14, x14, #2\n"
	"	madd x13, x5, x14, x13\n"
	"	add x14, x14, #2\n"
	"	add x0, x0, #32\n"
	"	cmp x0, x1\n"
	"	b.lo 1b\n"
	"	dsb sy\n"
	"	msr sctlr_el1, x7\n"
	"	isb\n"
	"	msr vbar_el1, x8\n"
	"	msr tpidrro_el0, x9\n"
	"	msr ttbr0_el1, x10\n"
	"	msr tcr_el1, x11\n"
	"	msr mair_el1, x12\n"
	"	isb\n"
	"	tlbi vmalle1\n"
	"	dsb sy\n"
	"	isb\n"
	"	mov x0, x13\n"
	"	ret\n"
	".globl n130_sum_mmu_end\n"
	"n130_sum_mmu_end:\n"
	".popsection\n");
extern const uint8_t n130_sum_mmu_end[];

static inline void n130_st(uint64_t *p, uint64_t v) { *(volatile uint64_t *)p = v; }

/* 0 = table space exhausted */
static int n130_map(uint64_t pa, uint64_t attrs)
{
	uint64_t i1 = (pa >> 30) & 511, i2 = (pa >> 21) & 511, i3 = (pa >> 12) & 511, key = pa >> 21;
	unsigned int a, b;

	if (pa >> 39)
		return 0;
	for (a = 0; a < n130_l2_used && n130_l2_of[a] != (pa >> 30); a++)
		;
	if (a == n130_l2_used) {
		if (a == N130_L2N)
			return 0;
		n130_l2_of[a] = pa >> 30;
		n130_l2_used++;
		n130_st(&n130_l1[i1], (uint64_t)(uintptr_t)n130_l2[a] | 3u);
	}
	for (b = 0; b < n130_l3_used && n130_l3_of[b] != key; b++)
		;
	if (b == n130_l3_used) {
		if (b == N130_L3N)
			return 0;
		n130_l3_of[b] = key;
		n130_l3_used++;
		n130_st(&n130_l2[a][i2], (uint64_t)(uintptr_t)n130_l3[b] | 3u);
	}
	n130_st(&n130_l3[b][i3], (pa & ~0xfffull) | attrs);
	return 1;
}

static inline uint64_t usbmon_dest_sum_cached(const void *p, size_t n)
{
	/* L3 page: valid|page, AttrIndx 0, AP[2:1] = 10 (EL1 read-only: SCTLR.WXN is set), SH inner, AF, UXN; data also PXN */
	const uint64_t code = 3u | (2u << 6) | (3u << 8) | (1u << 10) | (1ull << 54);
	const uint64_t data = code | (1ull << 53);
	uint64_t a = (uint64_t)(uintptr_t)p, pg = (uint64_t)(uintptr_t)n130_page, sctlr, mmfr0, sum;
	uint64_t tlo = (uint64_t)(uintptr_t)n130_l1, thi = (uint64_t)(uintptr_t)&n130_l3[N130_L3N];
	struct n130_ctx c;
	unsigned int i;

	__asm__ volatile("mrs %0, sctlr_el1" : "=r"(sctlr));
	if ((sctlr & 1) || (a & 63) || (n & 511) || !n || a + n < a || (a < thi && a + n > tlo) ||
	    (uint64_t)(uintptr_t)n130_sum_mmu_end - pg > 4096 || (a < pg + 4096 && a + n > pg))
		goto fallback;
	for (i = 0; i < 512; i++)
		n130_st(&n130_l1[i], 0);
	for (i = 0; i < N130_L2N * 512; i++)
		n130_st(&n130_l2[0][0] + i, 0);
	for (i = 0; i < N130_L3N * 512; i++)
		n130_st(&n130_l3[0][0] + i, 0);
	n130_l2_used = n130_l3_used = 0;
	if (!n130_map(pg, code))
		goto fallback;
	for (uint64_t q = a & ~0xfffull; q < a + n; q += 4096)
		if (!n130_map(q, data))
			goto fallback;
	__asm__ volatile("mrs %0, id_aa64mmfr0_el1" : "=r"(mmfr0));
	c.ttbr0 = tlo;
	/* T0SZ 25 (39-bit, walk from level 1), walks non-cacheable outer shareable, 4 KiB granule, T1SZ 25 + EPD1, IPS = PARange */
	c.tcr = 25u | (2u << 12) | (25u << 16) | (1u << 23) | ((uint64_t)((mmfr0 & 15u) > 5u ? 5u : (mmfr0 & 15u)) << 32);
	c.mair = 0xffu;			/* attr0: Normal, inner/outer write-back read/write-allocate */
	c.vbar = pg;
	__asm__ volatile("dsb sy" ::: "memory");
	sum = n130_sum_mmu(p, n, &c);
	/* MMU and cache are off again: drop every line the window may have allocated */
	usbmon_dma_sync(p, n);
	usbmon_dma_sync(n130_page, 4096);
	return sum;
fallback:
	n130_fallbacks++;
	return usbmon_dest_sum_fast(p, n);
}

static inline uint32_t usbmon_port_sum_fallbacks(void) { return n130_fallbacks; }
#endif /* USBMON_ENGINE_TU */
#endif
