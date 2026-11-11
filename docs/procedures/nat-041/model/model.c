// SPDX-License-Identifier: GPL-2.0-only
/*
 * Host-side model for the NAT-041 engine tests: a simulated DWC3 device controller (EP0 only), a simulated non-coherent CPU
 * cache in front of the engine's DMA block, and a USB host that runs control transfers against both.
 *
 * What this is: my reading of the Linux dwc3 driver and the databook behaviour that driver relies on, written down as an
 * executable specification. What it is not: the silicon. A test that passes here shows the engine agrees with this reading
 * and obeys the DMA discipline below; it says nothing about how the S24's controller behaves. Every place the model checks
 * something the engine must do is a `viol()` call; the tests require the violation list to be empty on the good path and to
 * name the defect on seeded bad paths.
 *
 * Cache model: 64-byte lines over the registered DMA block. The CPU's loads and stores (usbmon_dma_*) go through the lines,
 * the controller's reads and writes go straight to memory, usbmon_dma_sync cleans and invalidates. Violations: a CPU load that
 * returns a line whose contents differ from memory (stale read), a controller read of bytes a dirty line holds a different
 * value for (missing clean), a controller write into a line that is dirty (the later write-back would clobber it).
 */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "usbmon.h"
#include "host_port.h"

#define MODEL_BASE	0x17900000UL
#define LINE		64u
#define MAXLINES	512u
#define MAXVIOL		64u
#define MAXTRACE	8192u

/* ------------------------------------------------------------------ violations */

static char viols[MAXVIOL][200];
static unsigned int nviol;
static unsigned int viol_total;

static void viol(const char *fmt, ...)
{
	char tmp[200];
	va_list ap;
	unsigned int i;

	va_start(ap, fmt);
	vsnprintf(tmp, sizeof(tmp), fmt, ap);
	va_end(ap);
	viol_total++;
	for (i = 0; i < nviol; i++)
		if (!strcmp(viols[i], tmp))
			return;
	if (nviol < MAXVIOL)
		strcpy(viols[nviol++], tmp);
}

int model_nviol(void) { return (int)nviol; }
int model_viol_total(void) { return (int)viol_total; }
int model_viol(int i, char *buf, int n)
{
	if (i < 0 || (unsigned int)i >= nviol)
		return -1;
	snprintf(buf, (size_t)n, "%s", viols[i]);
	return 0;
}
void model_clear_viol(void) { nviol = 0; viol_total = 0; }

/* ------------------------------------------------------------------ cache model */

struct line {
	int valid, dirty;
	uint8_t data[LINE];
};

static struct line lines[MAXLINES];
static uintptr_t reg_lo, reg_hi;

static int in_region(uintptr_t a, size_t n)
{
	return reg_lo && a >= reg_lo && a + n <= reg_hi;
}

static struct line *line_of(uintptr_t a, uintptr_t *base)
{
	uintptr_t idx = (a - reg_lo) / LINE;

	*base = reg_lo + idx * LINE;
	return &lines[idx];
}

static void line_fill(struct line *l, uintptr_t base)
{
	memcpy(l->data, (void *)base, LINE);
	l->valid = 1;
	l->dirty = 0;
}

static void cpu_read(void *dst, uintptr_t src, size_t n, const char *who)
{
	size_t i;
	int stale = 0;

	if (!in_region(src, n)) {
		viol("%s: CPU access outside the DMA block", who);
		memcpy(dst, (void *)src, n);
		return;
	}
	for (i = 0; i < n; i++) {
		uintptr_t base, a = src + i;
		struct line *l = line_of(a, &base);

		if (!l->valid)
			line_fill(l, base);
		else if (!l->dirty && l->data[a - base] != *(uint8_t *)a)
			stale = 1;
		((uint8_t *)dst)[i] = l->data[a - base];
	}
	if (stale)
		viol("%s: CPU read stale cache data (missing invalidate before reading what the controller wrote)", who);
}

static void cpu_write(uintptr_t dst, const void *src, size_t n, const char *who)
{
	size_t i;

	if (!in_region(dst, n)) {
		viol("%s: CPU access outside the DMA block", who);
		memcpy((void *)dst, src, n);
		return;
	}
	for (i = 0; i < n; i++) {
		uintptr_t base, a = dst + i;
		struct line *l = line_of(a, &base);

		if (!l->valid)
			line_fill(l, base);
		l->data[a - base] = ((const uint8_t *)src)[i];
		l->dirty = 1;
	}
}

static void dev_read(void *dst, uintptr_t src, size_t n, const char *what)
{
	size_t i;
	int dirty = 0;

	if (!in_region(src, n)) {
		viol("controller read of %s outside the DMA block", what);
		memset(dst, 0, n);
		return;
	}
	for (i = 0; i < n; i++) {
		uintptr_t base, a = src + i;
		struct line *l = line_of(a, &base);

		if (l->valid && l->dirty && l->data[a - base] != *(uint8_t *)a)
			dirty = 1;
	}
	if (dirty)
		viol("controller read %s while the CPU's dirty cache line differs from memory (missing clean before the doorbell)",
		     what);
	memcpy(dst, (void *)src, n);
}

static void dev_write(uintptr_t dst, const void *src, size_t n, const char *what)
{
	size_t i;
	int dirty = 0;

	if (!in_region(dst, n)) {
		viol("controller write of %s outside the DMA block", what);
		return;
	}
	for (i = 0; i < n; i++) {
		uintptr_t base, a = dst + i;
		struct line *l = line_of(a, &base);

		if (l->valid && l->dirty)
			dirty = 1;
	}
	if (dirty)
		viol("controller wrote %s into a cache line the CPU holds dirty (a later write-back would overwrite it)", what);
	memcpy((void *)dst, src, n);
}

uint32_t usbmon_dma_ld32(const volatile void *p)
{
	uint32_t v;

	cpu_read(&v, (uintptr_t)p, 4, "usbmon_dma_ld32");
	return v;
}
void usbmon_dma_st32(volatile void *p, uint32_t v) { cpu_write((uintptr_t)p, &v, 4, "usbmon_dma_st32"); }
void usbmon_dma_read(void *dst, const volatile void *src, size_t n) { cpu_read(dst, (uintptr_t)src, n, "usbmon_dma_read"); }
void usbmon_dma_write(volatile void *dst, const void *src, size_t n) { cpu_write((uintptr_t)dst, src, n, "usbmon_dma_write"); }
uint64_t usbmon_dma_addr(const volatile void *p) { return (uint64_t)(uintptr_t)p; }

void usbmon_dma_sync(const volatile void *p, size_t n)
{
	uintptr_t a = (uintptr_t)p, end = a + n, base;

	if (!n)
		return;
	if (!in_region(a, n)) {
		viol("usbmon_dma_sync outside the DMA block");
		return;
	}
	for (a &= ~(uintptr_t)(LINE - 1); a < end; a += LINE) {
		struct line *l = line_of(a, &base);

		if (l->valid && l->dirty)
			memcpy((void *)base, l->data, LINE);
		l->valid = 0;
		l->dirty = 0;
	}
}

/* ------------------------------------------------------------------ the controller */

struct ep {
	int cfg, xferres, started, stalled_unused, nrdy_sent;
	uint32_t mps;
	uint64_t trb_addr;
	uint32_t rsc;
	uint32_t par0, par1, par2, cmdreg;
	int cmdact_left;
};

static struct {
	uint32_t regs[0x10000 / 4];
	int sr_pending, sr_latency;
	int cmd_latency;
	int cfg_started;
	int run;
	int speed;
	uint32_t id;
	struct ep ep[2];
	int ctrl_stalled;
	int has_pending;		/* a SETUP packet is held in the controller until a SETUP TRB is started */
	uint8_t pending_setup[8];
	int nrdy_after_pending;
	uint32_t evt_pos, evt_count, evt_size;
	int attached;
	unsigned int host_addr;
	int fail_code;			/* next command with this code fails once without a violation (-1 = none) */
	unsigned int rsc_ctr;
	uint64_t ticks;
	uint32_t depcmd_count[16];
	uint32_t overflowed;
} hw;

static struct usbmon *g_m;

struct wr_entry { uint32_t off, val; };
static struct wr_entry wtrace[MAXTRACE];
static unsigned int nwtrace;
struct cmd_entry { uint32_t ep, cmd, p0, p1, p2, result; };
static struct cmd_entry ctrace[MAXTRACE];
static unsigned int nctrace;

static const uint32_t known_regs[] = {
	DWC3_GSBUSCFG0, DWC3_GCTL, DWC3_GSNPSID, DWC3_GUCTL, DWC3_GHWPARAMS7, DWC3_GUSB2PHYCFG(0), DWC3_GEVNTADRLO(0),
	DWC3_GEVNTADRHI(0), DWC3_GEVNTSIZ(0), DWC3_GEVNTCOUNT(0), DWC3_GFLADJ, DWC3_DCFG, DWC3_DCTL, DWC3_DEVTEN, DWC3_DSTS,
	DWC3_DALEPENA,
};

static int reg_known(uint32_t off)
{
	unsigned int i;

	for (i = 0; i < sizeof(known_regs) / sizeof(known_regs[0]); i++)
		if (known_regs[i] == off)
			return 1;
	if (off >= DWC3_DEP_BASE(0) && off < DWC3_DEP_BASE(2))
		return 1;
	return 0;
}

static void push_event(uint32_t e)
{
	uint64_t adr;

	if (!hw.evt_size)
		return;
	if (hw.evt_count + 4 > hw.evt_size) {
		viol("event buffer overflow: the engine let %u bytes of events pile up", hw.evt_count);
		hw.overflowed++;
		return;
	}
	adr = ((uint64_t)hw.regs[DWC3_GEVNTADRHI(0) / 4] << 32) | hw.regs[DWC3_GEVNTADRLO(0) / 4];
	dev_write((uintptr_t)(adr + hw.evt_pos), &e, 4, "an event");
	hw.evt_pos = (hw.evt_pos + 4) % hw.evt_size;
	hw.evt_count += 4;
}

static uint32_t ev_ep(unsigned int ep, unsigned int type, unsigned int status, unsigned int params)
{
	return ((params & 0xffffu) << 16) | ((status & 0xfu) << 12) | ((type & 0xfu) << 6) | ((ep & 0x1fu) << 1);
}

static uint32_t ev_dev(unsigned int type) { return (type << 8) | 1u; }

static uint32_t depcmd_result(unsigned int ep, uint32_t status, uint32_t rsc)
{
	(void)ep;
	return (rsc << 16) | (status << 12);
}

static void trb_complete(unsigned int ep, uint64_t addr, uint32_t len, uint32_t xferred, uint32_t trbsts);

/* The armed ep0 OUT SETUP TRB receives the held SETUP packet. */
static void deliver_setup(void)
{
	struct ep *e0 = &hw.ep[0];
	uint32_t trb[4];
	uint64_t buf;

	dev_read(trb, (uintptr_t)e0->trb_addr, 16, "the SETUP TRB");
	buf = ((uint64_t)trb[1] << 32) | trb[0];
	dev_write((uintptr_t)buf, hw.pending_setup, 8, "the SETUP packet");
	trb_complete(0, e0->trb_addr, trb[2] & DWC3_TRB_SIZE_MASK, 8, DWC3_TRBSTS_OK);
	e0->started = 0;
	e0->nrdy_sent = 0;
	hw.has_pending = 0;
	hw.ctrl_stalled = 0;
	push_event(ev_ep(0, DWC3_DEPEVT_XFERCOMPLETE, 0, 0));
}

static void do_depcmd(unsigned int n, uint32_t cmd)
{
	struct ep *e = &hw.ep[n];
	uint32_t code = cmd & 0xf, status = 0, rsc = 0;
	int expect_fail = (hw.fail_code >= 0 && (uint32_t)hw.fail_code == code);

	hw.depcmd_count[code]++;
	if (expect_fail) {
		hw.fail_code = -1;
		status = 1;
		goto done;
	}
	switch (code) {
	case 9:		/* DEPSTARTCFG */
		if (n != 0) { viol("DEPSTARTCFG issued on ep %u (only ep0 takes it)", n); status = 1; break; }
		hw.cfg_started = 1;
		break;
	case 1: {	/* DEPCFG */
		uint32_t p0 = e->par0, p1 = e->par1;
		uint32_t action = p0 >> 30;

		if (!hw.cfg_started) { viol("DEPCFG before DEPSTARTCFG"); status = 1; break; }
		if (((p1 >> 25) & 0x1f) != n) viol("DEPCFG ep number field %u for physical ep %u", (p1 >> 25) & 0x1f, n);
		if (((p0 >> 1) & 3) != DWC3_DEPCMD_TYPE_CONTROL) viol("DEPCFG type is not control on ep %u", n);
		if (!(p1 & DWC3_DEPCFG_XFER_COMPLETE_EN)) viol("DEPCFG without XferComplete enable on ep %u", n);
		if (!(p1 & DWC3_DEPCFG_XFER_NOT_READY_EN)) viol("DEPCFG without XferNotReady enable on ep %u", n);
		if (n == 1 && ((p0 >> 17) & 0x1f) != 0) viol("DEPCFG fifo number %u on ep1", (p0 >> 17) & 0x1f);
		if (action == 0) {
			if (e->cfg) viol("DEPCFG INIT on an already configured ep %u", n);
		} else if (action == 2) {
			if (!e->cfg) viol("DEPCFG MODIFY before INIT on ep %u", n);
		} else {
			viol("DEPCFG action %u on ep %u", action, n);
		}
		e->cfg = 1;
		e->mps = (p0 >> 3) & 0x7ff;
		break;
	}
	case 2:		/* DEPXFERCFG */
		if (!e->cfg) { viol("DEPXFERCFG before DEPCFG on ep %u", n); status = 1; break; }
		if ((e->par0 & 0xffff) != 1) viol("DEPXFERCFG with %u transfer resources", e->par0 & 0xffff);
		e->xferres = 1;
		break;
	case 6: {	/* STARTTRANSFER */
		uint32_t trb[4];

		if (!e->cfg || !e->xferres) { viol("STARTTRANSFER on ep %u before DEPCFG/DEPXFERCFG", n); status = 1; break; }
		if (!(hw.regs[DWC3_DALEPENA / 4] & (1u << n))) { viol("STARTTRANSFER on ep %u not enabled in DALEPENA", n); status = 1; break; }
		if (e->started) { viol("STARTTRANSFER on ep %u with a transfer already started", n); status = 1; break; }
		e->trb_addr = ((uint64_t)e->par0 << 32) | e->par1;
		if (e->trb_addr & 0xf) viol("TRB address %llx not 16-byte aligned", (unsigned long long)e->trb_addr);
		dev_read(trb, (uintptr_t)e->trb_addr, 16, "the TRB at STARTTRANSFER");
		if (!(trb[3] & DWC3_TRB_CTRL_HWO)) { viol("STARTTRANSFER with a TRB whose HWO is clear"); status = 1; break; }
		e->started = 1;
		e->nrdy_sent = 0;
		e->rsc = (n == 0) ? 0 : 2 + (hw.rsc_ctr++ % 5);	/* ep0 OUT has resource index 0 (vendor ep0.c comment) */
		rsc = e->rsc;
		if (n == 0 && hw.has_pending && ((trb[3] >> 4) & 0x3f) == 2)
			deliver_setup();
		break;
	}
	case 8:		/* ENDTRANSFER */
		if (!e->started) { viol("ENDTRANSFER on ep %u with no transfer started", n); status = 1; break; }
		if (((cmd >> 16) & 0x7f) != e->rsc) {
			viol("ENDTRANSFER on ep %u with resource index %u, expected %u", n, (cmd >> 16) & 0x7f, e->rsc);
			status = 1;
			break;
		}
		e->started = 0;
		e->nrdy_sent = 0;
		if (cmd & DWC3_DEPCMD_CMDIOC)
			push_event(ev_ep(n, DWC3_DEPEVT_EPCMDCMPLT, 0, (DWC3_DEPCMD_ENDTRANSFER << 8) | e->rsc));
		break;
	case 4:		/* SETSTALL */
		if (n != 0) viol("SETSTALL on ep %u (the vendor driver stalls the control pair through ep0)", n);
		hw.ctrl_stalled = 1;
		break;
	default:
		viol("unknown device endpoint command %u", code);
		status = 1;
	}
done:
	e->cmdreg = depcmd_result(n, status, rsc);
	if (nctrace < MAXTRACE)
		ctrace[nctrace++] = (struct cmd_entry){ n, cmd, e->par0, e->par1, e->par2, e->cmdreg };
}

static int prefetch_on = 1;
void model_set_prefetch(int on) { prefetch_on = on; }

/* A worst-case hardware prefetcher: between any two CPU-visible operations every line that is not cached is loaded from
 * memory. A CPU load of device-written data is then only correct if the line was invalidated after the device wrote it. */
static void prefetch_all(void)
{
	uintptr_t a;

	if (!prefetch_on || !reg_lo)
		return;
	for (a = reg_lo; a < reg_hi; a += LINE) {
		uintptr_t base;
		struct line *l = line_of(a, &base);

		if (!l->valid)
			line_fill(l, base);
	}
}

static uint32_t rd32_inner(uintptr_t addr);

uint32_t usbmon_rd32(uintptr_t addr)
{
	uint32_t v = rd32_inner(addr);

	prefetch_all();
	return v;
}

static uint32_t rd32_inner(uintptr_t addr)
{
	uint32_t off = (uint32_t)(addr - MODEL_BASE), v;

	if (addr < MODEL_BASE || off >= 0x10000 || (off & 3) || !reg_known(off)) {
		viol("read of unknown register %#lx", (unsigned long)addr);
		return 0;
	}
	if (off >= DWC3_DEP_BASE(0) && off < DWC3_DEP_BASE(2)) {
		struct ep *e = &hw.ep[(off - DWC3_DEP_BASE(0)) / 0x10];

		switch (off & 0xf) {
		case DWC3_DEPCMD:
			if (e->cmdact_left > 0) {
				e->cmdact_left--;
				return e->cmdreg | DWC3_DEPCMD_CMDACT;
			}
			return e->cmdreg;
		case DWC3_DEPCMDPAR0: return e->par0;
		case DWC3_DEPCMDPAR1: return e->par1;
		default: return e->par2;
		}
	}
	switch (off) {
	case DWC3_GSNPSID: return hw.id;
	case DWC3_DCTL:
		v = hw.regs[off / 4];
		if (hw.sr_pending > 0) {
			hw.sr_pending--;
			return v | DWC3_DCTL_CSFTRST;
		}
		hw.regs[off / 4] &= ~DWC3_DCTL_CSFTRST;
		return v & ~DWC3_DCTL_CSFTRST;
	case DWC3_DSTS:
		return (hw.run ? 0 : DWC3_DSTS_DEVCTRLHLT) | (uint32_t)hw.speed;
	case DWC3_GEVNTCOUNT(0):
		return hw.evt_count;
	case DWC3_GHWPARAMS7:
		return 0x0400u << 16;
	default:
		return hw.regs[off / 4];
	}
}

static void wr32_inner(uintptr_t addr, uint32_t v);

void usbmon_wr32(uintptr_t addr, uint32_t v)
{
	wr32_inner(addr, v);
	prefetch_all();
}

static void wr32_inner(uintptr_t addr, uint32_t v)
{
	uint32_t off = (uint32_t)(addr - MODEL_BASE);

	if (addr < MODEL_BASE || off >= 0x10000 || (off & 3) || !reg_known(off)) {
		viol("write of unknown register %#lx", (unsigned long)addr);
		return;
	}
	if (nwtrace < MAXTRACE)
		wtrace[nwtrace++] = (struct wr_entry){ off, v };
	if (off >= DWC3_DEP_BASE(0) && off < DWC3_DEP_BASE(2)) {
		struct ep *e = &hw.ep[(off - DWC3_DEP_BASE(0)) / 0x10];
		unsigned int n = (off - DWC3_DEP_BASE(0)) / 0x10;

		switch (off & 0xf) {
		case DWC3_DEPCMDPAR0: e->par0 = v; break;
		case DWC3_DEPCMDPAR1: e->par1 = v; break;
		case DWC3_DEPCMDPAR2: e->par2 = v; break;
		case DWC3_DEPCMD:
			if (!(v & DWC3_DEPCMD_CMDACT)) { viol("DEPCMD write without CMDACT"); break; }
			do_depcmd(n, v);
			e->cmdact_left = hw.cmd_latency;
			break;
		}
		return;
	}
	switch (off) {
	case DWC3_GSNPSID:
	case DWC3_GHWPARAMS7:
	case DWC3_DSTS:
		viol("write to read-only register %#x", off);
		return;
	case DWC3_GEVNTCOUNT(0):
		if (v > hw.evt_count) {
			viol("event acknowledge of %u bytes with %u pending", v, hw.evt_count);
			hw.evt_count = 0;
		} else {
			hw.evt_count -= v;
		}
		return;
	case DWC3_GEVNTSIZ(0):
		hw.evt_size = v & 0xffff;
		hw.evt_pos = 0;
		hw.evt_count = 0;
		break;
	case DWC3_DCTL:
		if ((v & DWC3_DCTL_CSFTRST) && !(hw.regs[off / 4] & DWC3_DCTL_CSFTRST))
			hw.sr_pending = hw.sr_latency;
		if ((v & DWC3_DCTL_RUN_STOP) && !hw.run) {
			if (!hw.regs[DWC3_DEVTEN / 4])
				viol("RUN_STOP set with no device events enabled");
			if (!hw.ep[0].started)
				viol("RUN_STOP set before the SETUP TRB was started");
			hw.run = 1;
		} else if (!(v & DWC3_DCTL_RUN_STOP)) {
			hw.run = 0;
		}
		break;
	default:
		break;
	}
	hw.regs[off / 4] = v;
}

void usbmon_delay_us(uint32_t us) { hw.ticks += (uint64_t)us * 24; }
uint64_t usbmon_ticks(void) { return hw.ticks += 3; }

/* ------------------------------------------------------------------ the USB host */

#define H_OK		0
#define H_STALL		1
#define H_TIMEOUT	(-1)
#define H_NAKLOOP	(-2)	/* the device kept NAK-ing a stage the host expected to continue */
#define H_PROTO		(-3)

static int host_polls = 2;	/* engine polls per host step */
static int host_timeout = 40;	/* steps before a stage gives up */

static void step(void)
{
	int i;

	for (i = 0; i < host_polls; i++)
		usbmon_poll(g_m);
	hw.ticks += 2400;
}

static int addressed(void)
{
	return hw.attached && hw.run && hw.host_addr == (unsigned int)((hw.regs[DWC3_DCFG / 4] >> 3) & 0x7f);
}

static int wait_started(unsigned int ep, uint32_t want_type, int nrdy_status)
{
	int i;

	for (i = 0; i < host_timeout; i++) {
		if (hw.ctrl_stalled)
			return H_STALL;
		if (hw.ep[ep].started) {
			uint32_t trb[4];

			dev_read(trb, (uintptr_t)hw.ep[ep].trb_addr, 16, "the TRB being executed");
			if (((trb[3] >> 4) & 0x3f) != want_type) {
				viol("ep %u executes a TRB of type %u, the host stage needs type %u", ep, (trb[3] >> 4) & 0x3f, want_type);
				return H_PROTO;
			}
			return H_OK;
		}
		if (nrdy_status && !hw.ep[ep].nrdy_sent) {
			hw.ep[ep].nrdy_sent = 1;
			push_event(ev_ep(ep, DWC3_DEPEVT_XFERNOTREADY, (unsigned int)nrdy_status, 0));
		}
		step();
	}
	return H_TIMEOUT;
}

static void trb_complete(unsigned int ep, uint64_t addr, uint32_t len, uint32_t xferred, uint32_t trbsts)
{
	uint32_t sz = ((len - xferred) & DWC3_TRB_SIZE_MASK) | (trbsts << 28), ctrl;

	dev_read(&ctrl, (uintptr_t)addr + 12, 4, "the TRB control word");
	ctrl &= ~DWC3_TRB_CTRL_HWO;
	dev_write((uintptr_t)addr + 8, &sz, 4, "the TRB size word");
	dev_write((uintptr_t)addr + 12, &ctrl, 4, "the TRB control word");
	(void)ep;
}

/* SETUP stage. A SETUP packet is delivered into an armed SETUP TRB. If none is armed (the engine has not restarted it yet, or
 * a data/status transfer is still armed) the packet is held, the armed transfers complete with TRB status "setup pending", and
 * the packet is delivered when the engine next starts a SETUP TRB (the behaviour the vendor driver's setup_packet_pending
 * handling is written for). */
int model_setup(const uint8_t *s8)
{
	struct ep *e0 = &hw.ep[0], *e1 = &hw.ep[1];
	int i, armed = 0;
	uint32_t trb[4];

	if (!addressed())
		return H_TIMEOUT;
	if (e0->started) {
		dev_read(trb, (uintptr_t)e0->trb_addr, 16, "the armed ep0 OUT TRB");
		armed = (((trb[3] >> 4) & 0x3f) == 2);
	}
	memcpy(hw.pending_setup, s8, 8);
	hw.has_pending = 1;
	if (armed) {
		deliver_setup();
	} else {
		unsigned int stat_ep = 0;
		int interrupted = 0;

		if (e0->started) {
			trb_complete(0, e0->trb_addr, trb[2] & DWC3_TRB_SIZE_MASK, 0, DWC3_TRBSTS_SETUP_PENDING);
			e0->started = 0;
			push_event(ev_ep(0, DWC3_DEPEVT_XFERCOMPLETE, 0, 0));
			interrupted = 1;
			stat_ep = 1;
		}
		if (e1->started) {
			uint32_t t1[4];

			dev_read(t1, (uintptr_t)e1->trb_addr, 16, "the interrupted IN TRB");
			trb_complete(1, e1->trb_addr, t1[2] & DWC3_TRB_SIZE_MASK, 0, DWC3_TRBSTS_SETUP_PENDING);
			e1->started = 0;
			push_event(ev_ep(1, DWC3_DEPEVT_XFERCOMPLETE, 0, 0));
			interrupted = 1;
			stat_ep = 0;
		}
		if (interrupted && hw.nrdy_after_pending)
			push_event(ev_ep(stat_ep, DWC3_DEPEVT_XFERNOTREADY, DEPEVT_STATUS_CONTROL_STATUS, 0));
	}
	for (i = 0; i < host_timeout && hw.has_pending; i++)
		step();
	if (hw.has_pending)
		return H_TIMEOUT;
	step();
	return H_OK;
}

int model_data_in(unsigned int wlen, uint8_t *out, int *got)
{
	struct ep *e = &hw.ep[1];
	unsigned int total = 0, mps = hw.ep[1].mps ? hw.ep[1].mps : 64;
	int r, last_short = 0;

	*got = 0;
	while (total < wlen && !last_short) {
		uint64_t a;
		int idx = 0;

		r = wait_started(1, 5, DEPEVT_STATUS_CONTROL_DATA);
		if (r == H_TIMEOUT)
			return total ? H_NAKLOOP : H_TIMEOUT;
		if (r)
			return r;
		a = e->trb_addr;
		for (;;) {
			uint32_t trb[4], len, n;
			uint64_t buf;
			uint8_t tmp[4200];

			dev_read(trb, (uintptr_t)a + 16u * (unsigned int)idx, 16, "a data TRB");
			if (!(trb[3] & DWC3_TRB_CTRL_HWO)) { viol("data TRB %d without HWO", idx); return H_PROTO; }
			if (((trb[3] >> 4) & 0x3f) != 5) { viol("chained TRB %d is not a DATA TRB", idx); return H_PROTO; }
			len = trb[2] & DWC3_TRB_SIZE_MASK;
			buf = ((uint64_t)trb[1] << 32) | trb[0];
			if (len > wlen - total)
				viol("the device offered %u bytes to a host that asked for %u", len, wlen);
			n = len < wlen - total ? len : wlen - total;
			if (n > sizeof(tmp)) { viol("TRB length %u beyond the model's limit", n); return H_PROTO; }
			if (n)
				dev_read(tmp, (uintptr_t)buf, n, "reply data");
			memcpy(out + total, tmp, n);
			total += n;
			last_short = (n % mps) != 0 || n == 0;
			trb_complete(1, a + 16u * (unsigned int)idx, len, n, DWC3_TRBSTS_OK);
			if (trb[3] & DWC3_TRB_CTRL_CHN) {
				idx++;
				continue;
			}
			if (trb[3] & DWC3_TRB_CTRL_IOC)
				push_event(ev_ep(1, DWC3_DEPEVT_XFERCOMPLETE, 0, 0));
			break;
		}
		e->started = 0;
		e->nrdy_sent = 0;
		step();
	}
	*got = (int)total;
	return H_OK;
}

int model_data_out(const uint8_t *data, unsigned int len)
{
	struct ep *e = &hw.ep[0];
	int r;
	uint32_t trb[4], tlen, n;
	uint64_t buf;

	r = wait_started(0, 5, DEPEVT_STATUS_CONTROL_DATA);
	if (r)
		return r;
	dev_read(trb, (uintptr_t)e->trb_addr, 16, "the OUT data TRB");
	tlen = trb[2] & DWC3_TRB_SIZE_MASK;
	buf = ((uint64_t)trb[1] << 32) | trb[0];
	if (tlen % e->mps)
		viol("OUT TRB length %u is not a multiple of wMaxPacketSize %u", tlen, e->mps);
	n = len < tlen ? len : tlen;
	dev_write((uintptr_t)buf, data, n, "OUT data");
	trb_complete(0, e->trb_addr, tlen, n, DWC3_TRBSTS_OK);
	e->started = 0;
	e->nrdy_sent = 0;
	push_event(ev_ep(0, DWC3_DEPEVT_XFERCOMPLETE, 0, 0));
	step();
	return n == len ? H_OK : H_NAKLOOP;
}

int model_status(int status_in, int three_stage)
{
	unsigned int ep = status_in ? 1u : 0u;
	struct ep *e = &hw.ep[ep];
	int r = wait_started(ep, three_stage ? 4u : 3u, DEPEVT_STATUS_CONTROL_STATUS);
	uint32_t trb[4];

	if (r)
		return r;
	dev_read(trb, (uintptr_t)e->trb_addr, 16, "the status TRB");
	if ((trb[2] & DWC3_TRB_SIZE_MASK) != 0)
		viol("status TRB with length %u", trb[2] & DWC3_TRB_SIZE_MASK);
	trb_complete(ep, e->trb_addr, 0, 0, DWC3_TRBSTS_OK);
	e->started = 0;
	e->nrdy_sent = 0;
	push_event(ev_ep(ep, DWC3_DEPEVT_XFERCOMPLETE, 0, 0));
	step();
	return H_OK;
}

/* A whole control transfer. *got receives the IN data length. */
int model_ctrl(uint8_t type, uint8_t req, uint16_t value, uint16_t index, uint16_t length, const uint8_t *out, uint8_t *in,
	       int *got)
{
	uint8_t s[8] = { type, req, (uint8_t)value, (uint8_t)(value >> 8), (uint8_t)index, (uint8_t)(index >> 8),
			 (uint8_t)length, (uint8_t)(length >> 8) };
	int r;

	*got = 0;
	r = model_setup(s);
	if (r)
		return r;
	if (length) {
		if (type & 0x80)
			r = model_data_in(length, in, got);
		else
			r = model_data_out(out, length);
		if (r)
			return r;
	}
	r = model_status((length && (type & 0x80)) ? 0 : 1, length != 0);
	if (r)
		return r;
	if (!(type & 0x80) && (type & 0x60) == 0 && req == 5) {	/* SET_ADDRESS takes effect after the status stage */
		if (((hw.regs[DWC3_DCFG / 4] >> 3) & 0x7f) != value)
			viol("SET_ADDRESS(%u) completed but DCFG holds address %u", value, (hw.regs[DWC3_DCFG / 4] >> 3) & 0x7f);
		hw.host_addr = value;
	}
	step();
	return H_OK;
}

void model_attach(void)
{
	hw.attached = 1;
	hw.host_addr = 0;
	push_event(ev_dev(DWC3_DEVICE_EVENT_RESET));
	push_event(ev_dev(DWC3_DEVICE_EVENT_CONNECT_DONE));
	step();
}

void model_bus_reset(int conndone)
{
	hw.host_addr = 0;
	hw.ctrl_stalled = 0;
	push_event(ev_dev(DWC3_DEVICE_EVENT_RESET));
	if (conndone)
		push_event(ev_dev(DWC3_DEVICE_EVENT_CONNECT_DONE));
	step();
}

void model_detach(void)
{
	hw.attached = 0;
	push_event(ev_dev(DWC3_DEVICE_EVENT_DISCONNECT));
	step();
}

void model_set_host(int polls_per_step, int timeout_steps) { host_polls = polls_per_step; host_timeout = timeout_steps; }
void model_set_nrdy_after_pending(int on) { hw.nrdy_after_pending = on; }
void model_set_speed(int s) { hw.speed = s; }
void model_set_id(uint32_t id) { hw.id = id; }
void model_set_sr_latency(int n) { hw.sr_latency = n; }
void model_set_cmd_latency(int n) { hw.cmd_latency = n; }
void model_fail_next_cmd(int code) { hw.fail_code = code; }
int model_ep_started(int ep) { return hw.ep[ep].started; }
int model_stalled(void) { return hw.ctrl_stalled; }
int model_run(void) { return hw.run; }
int model_events_pending(void) { return (int)hw.evt_count; }
int model_cmd_count(int code) { return (int)hw.depcmd_count[code & 0xf]; }
int model_host_addr(void) { return (int)hw.host_addr; }
int model_overflowed(void) { return (int)hw.overflowed; }

int model_wtrace_n(void) { return (int)nwtrace; }
int model_wtrace(int i, uint32_t *off, uint32_t *val)
{
	if (i < 0 || (unsigned int)i >= nwtrace)
		return -1;
	*off = wtrace[i].off;
	*val = wtrace[i].val;
	return 0;
}
int model_ctrace_n(void) { return (int)nctrace; }
int model_ctrace(int i, uint32_t *ep, uint32_t *cmd, uint32_t *p0, uint32_t *p1, uint32_t *p2, uint32_t *result)
{
	if (i < 0 || (unsigned int)i >= nctrace)
		return -1;
	*ep = ctrace[i].ep; *cmd = ctrace[i].cmd; *p0 = ctrace[i].p0; *p1 = ctrace[i].p1; *p2 = ctrace[i].p2;
	*result = ctrace[i].result;
	return 0;
}

/* ------------------------------------------------------------------ test fixture API (ctypes) */

static uint8_t *g_ring;

static void model_reset(void)
{
	memset(&hw, 0, sizeof(hw));
	memset(lines, 0, sizeof(lines));
	hw.id = 0x5533330au;
	hw.fail_code = -1;
	hw.sr_latency = 2;
	hw.cmd_latency = 1;
	hw.nrdy_after_pending = 1;
	prefetch_on = 1;
	nwtrace = nctrace = 0;
	nviol = viol_total = 0;
	host_polls = 2;
	host_timeout = 40;
}

void *t_new(uint32_t ring_size)
{
	struct usbmon *m = aligned_alloc(64, (sizeof(struct usbmon) + 63) & ~63UL);

	memset(m, 0xa5, sizeof(*m));	/* a driver that relies on zeroed memory is a bug */
	free(g_ring);
	g_ring = malloc(ring_size);
	memset(g_ring, 0xa5, ring_size);
	model_reset();
	reg_lo = (uintptr_t)&m->dma;
	reg_hi = reg_lo + sizeof(m->dma);
	g_m = m;
	return m;
}

void t_free(void)
{
	free(g_m);
	free(g_ring);
	g_m = 0;
	g_ring = 0;
	reg_lo = reg_hi = 0;
}

int t_init(const uint8_t *boot_id, uint32_t ring_size, uint32_t refclk, uint8_t fladj, uint8_t lpm)
{
	struct usbmon_cfg cfg;

	memset(&cfg, 0, sizeof(cfg));
	cfg.dwc3_base = MODEL_BASE;
	cfg.ring = g_ring;
	cfg.ring_size = ring_size;
	memcpy(cfg.boot_id, boot_id, 16);
	cfg.refclk_hz = refclk;
	cfg.fladj = fladj;
	cfg.gfladj_refclk_lpm_sel = lpm;
	return usbmon_init(g_m, &cfg);
}

void t_poll(int n) { while (n-- > 0) usbmon_poll(g_m); }
void t_log(uint8_t kind, const uint8_t *d, uint16_t len) { usbmon_log(g_m, kind, d, len); }
void t_text(const char *s) { usbmon_text(g_m, s); }
void t_stage(uint32_t stage, const char *s) { usbmon_stage(g_m, stage, s); }
void t_log_interrupted(uint8_t kind, const uint8_t *d, uint16_t len, uint32_t n) { usbmon_log_interrupted(g_m, kind, d, len, n); }
void t_fault(const uint64_t *regs36)
{
	struct usbmon_exc_in r;

	r.esr = regs36[0]; r.elr = regs36[1]; r.far = regs36[2]; r.spsr = regs36[3]; r.sp = regs36[4];
	memcpy(r.x, regs36 + 5, sizeof(r.x));
	usbmon_fault_record(g_m, &r);
}
uint64_t t_written(void) { return g_m->written; }
uint64_t t_oldest(void) { return g_m->oldest; }
uint32_t t_seq(void) { return g_m->seq; }
uint32_t t_flags(void) { return g_m->flags; }
uint32_t t_dropped(void) { return g_m->dropped; }
uint32_t t_stalls(void) { return g_m->stalls; }
int32_t t_last_err(void) { return g_m->last_err; }
uint8_t *t_ring(void) { return g_ring; }
int t_ring_copy(uint64_t pos, uint8_t *dst, uint32_t n)
{
	uint32_t i;

	for (i = 0; i < n; i++)
		dst[i] = g_m->ring[(pos + i) % g_m->ring_size];
	return 0;
}
void t_set_stream_base(uint64_t v) { g_m->written = v; g_m->oldest = v; }
uint32_t t_sizeof_usbmon(void) { return (uint32_t)sizeof(struct usbmon); }
uint32_t t_dma_misaligned(void)
{
	uintptr_t a = (uintptr_t)&g_m->dma;

	return (uint32_t)(a & 63) | (uint32_t)(((uintptr_t)g_m->dma.events | (uintptr_t)g_m->dma.trb | (uintptr_t)g_m->dma.setup |
						(uintptr_t)g_m->dma.out | (uintptr_t)g_m->dma.reply) & 63);
}
