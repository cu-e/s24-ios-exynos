// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-047 test glue: the NAT-041 DWC3 host model (model/model.c, included unmodified) with ONE change of wiring: every place the
 * model calls the engine's usbmon_poll() (a USB host step lets the device side run) calls guest_poll() instead, which the Python
 * harness points at the *aarch64* usbmon_poll of the built loader.elf running in unicorn. The model's MMIO functions
 * (usbmon_rd32 / usbmon_wr32) are exported as h_rd32 / h_wr32 so the unicorn MMIO window of the DWC3 block can reach them.
 *
 * The guest's memory is a host mmap at the SAME address as the guest sees (sim47.py), so the model's raw-pointer DMA accesses
 * (events, TRBs, SETUP/OUT/reply buffers, all inside struct usbmon's dma block) reach the very bytes the guest code loads and
 * stores. The model's simulated non-coherent cache is not exercised here (the guest does plain loads and stores; the cache
 * discipline of the engine is NAT-041's x86 test), so h_reset() only registers the DMA block as the controller's memory region.
 *
 * Nothing here is the S24: this is NAT-041's reading of the DWC3 databook, driven by the loader's real instruction stream.
 */
#include <stdint.h>
#include <stddef.h>

#include "usbmon.h"
#include "host_port.h"

static void (*guest_poll_cb)(void);

static void guest_poll(struct usbmon *m)
{
	(void)m;
	if (guest_poll_cb)
		guest_poll_cb();
}

#define usbmon_poll(m) guest_poll(m)
#include "model.c"
#undef usbmon_poll

void h_set_poll_cb(void (*cb)(void)) { guest_poll_cb = cb; }

/* A fresh controller + host; lo..hi is the guest address range of the engine's DMA block. */
void h_reset(uint64_t lo, uint64_t hi)
{
	model_reset();
	model_set_prefetch(0);
	reg_lo = (uintptr_t)lo;
	reg_hi = (uintptr_t)hi;
	g_m = (struct usbmon *)(uintptr_t)1;	/* only ever passed to guest_poll(), which ignores it */
}

uint32_t h_rd32(uint64_t addr) { return usbmon_rd32((uintptr_t)addr); }
void h_wr32(uint64_t addr, uint32_t v) { usbmon_wr32((uintptr_t)addr, v); }
uint32_t h_sizeof_dma(void) { return (uint32_t)sizeof(((struct usbmon *)0)->dma); }
uint32_t h_sizeof_usbmon(void) { return (uint32_t)sizeof(struct usbmon); }
uint32_t h_offsetof_dma(void) { return (uint32_t)offsetof(struct usbmon, dma); }
