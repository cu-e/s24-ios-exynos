// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-045 host test platform. One simulated machine per process (global state), reset with plat_reset().
 *
 *  - a 32-bit register file keyed by address; `plat_def` declares an address (initial value), `plat_strict(1)` makes any
 *    access to an undeclared address a violation (so the test knows the ladder touches only what derive.py listed);
 *  - per register: read-only, stuck bits (forced on read), self-clearing bits (cleared after a write);
 *  - the HSI0 power domain: PMU config bit -> status bit after a delay (plat_follow); every access in the HSI0 block
 *    (CMU_HSI0 .. DWC3) while the status bit is 0 is a violation (the real bus would stall or fault);
 *  - virtual time advanced only by usbmon_delay_us; every access is logged with it;
 *  - the DWC3 window (0x17900000, 64 KiB) is the NAT-041 model.
 * Nothing here is the S24: the register semantics are exactly the ones above.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "usbmon.h"
#include "ladder.h"
#include "plat_port.h"

uint32_t model_rd32(uintptr_t addr);
void model_wr32(uintptr_t addr, uint32_t v);
void model_delay_us(uint32_t us);
uint64_t model_ticks(void);
void *t_new(uint32_t ring_size);
uint8_t *t_ring(void);

#define NREG	512
#define NLOG	262144
#define NVIOL	32

struct reg { uint32_t addr, val, stuck_mask, stuck_val, clr_mask, flip, flags, flip_from, nreads; };
#define RF_USED 1
#define RF_RO 2

static struct reg regs[NREG];
static unsigned nregs;
static int strict;
static uint64_t now_us;

struct follow { uint32_t cfg_addr, cfg_mask, st_addr, st_mask, delay_us; uint64_t due; uint32_t pending, active; } fol;
static uint32_t gate_status_addr, gate_status_mask, gate_on;
static uint32_t ov_off, ov_mask, ov_val, ov_on;		/* a read overlay on one DWC3 register: (v & ~mask) | val */
static uint32_t gate_lo = 0x17800000u, gate_hi = 0x17910000u;

struct logent { uint8_t kind; uint32_t addr, val; uint64_t t; };
static struct logent logv[NLOG];
static unsigned nlog;
static char violv[NVIOL][96];
static unsigned nviol, viol_total;

static void viol(const char *what, uint32_t addr)
{
	viol_total++;
	if (nviol < NVIOL)
		snprintf(violv[nviol++], sizeof(violv[0]), "%s @0x%08x t=%llu", what, addr, (unsigned long long)now_us);
}

void plat_reset(void)
{
	memset(regs, 0, sizeof(regs));
	nregs = 0;
	strict = 0;
	now_us = 0;
	memset(&fol, 0, sizeof(fol));
	gate_on = 0;
	ov_on = 0;
	nlog = 0;
	nviol = viol_total = 0;
	t_new(4096);			/* a fresh DWC3 model behind the DWC3 window (id 0x5533330a) */
}

static struct reg *find(uint32_t a)
{
	unsigned i;

	for (i = 0; i < nregs; i++)
		if (regs[i].addr == a)
			return &regs[i];
	return 0;
}

void plat_def(uint32_t addr, uint32_t val)
{
	struct reg *r = find(addr);

	if (!r) {
		if (nregs == NREG)
			abort();
		r = &regs[nregs++];
		memset(r, 0, sizeof(*r));
		r->addr = addr;
	}
	r->val = val;
}
void plat_strict(int on) { strict = on; }
void plat_ro(uint32_t addr) { struct reg *r = find(addr); if (r) r->flags |= RF_RO; }
void plat_stuck(uint32_t addr, uint32_t mask, uint32_t val) { struct reg *r = find(addr); if (r) { r->stuck_mask = mask; r->stuck_val = val; } }
void plat_flip(uint32_t addr, uint32_t mask) { struct reg *r = find(addr); if (r) { r->flip = mask; r->flip_from = 0; } }
/* the flip applies from the n-th read of this register on (1 = from the first read): a bit that changes only after the first checks */
void plat_flip_from(uint32_t addr, uint32_t mask, uint32_t n) { struct reg *r = find(addr); if (r) { r->flip = mask; r->flip_from = n; } }
void plat_selfclear(uint32_t addr, uint32_t mask) { struct reg *r = find(addr); if (r) r->clr_mask = mask; }
uint32_t plat_get(uint32_t addr) { struct reg *r = find(addr); return r ? r->val : 0xdeadbeef; }
int plat_defined(uint32_t addr) { return find(addr) != 0; }
void plat_follow(uint32_t cfg_addr, uint32_t cfg_mask, uint32_t st_addr, uint32_t st_mask, uint32_t delay_us)
{
	fol.cfg_addr = cfg_addr; fol.cfg_mask = cfg_mask; fol.st_addr = st_addr; fol.st_mask = st_mask; fol.delay_us = delay_us;
	fol.active = 1;
}
void plat_dwc3_overlay(uint32_t offset, uint32_t mask, uint32_t val) { ov_off = offset; ov_mask = mask; ov_val = val; ov_on = 1; }
void plat_gate(uint32_t status_addr, uint32_t status_mask) { gate_status_addr = status_addr; gate_status_mask = status_mask; gate_on = 1; }
uint64_t plat_now(void) { return now_us; }
unsigned plat_nlog(void) { return nlog; }
void plat_log(unsigned i, uint32_t *kind, uint32_t *addr, uint32_t *val, uint64_t *t)
{
	*kind = logv[i].kind; *addr = logv[i].addr; *val = logv[i].val; *t = logv[i].t;
}
unsigned plat_nviol(void) { return viol_total; }
const char *plat_viol(unsigned i) { return i < nviol ? violv[i] : ""; }

static void settle(void)
{
	if (fol.active && fol.pending && now_us >= fol.due) {
		struct reg *s = find(fol.st_addr);
		struct reg *c = find(fol.cfg_addr);

		if (s && c)
			s->val = (s->val & ~fol.st_mask) | (c->val & fol.cfg_mask ? fol.st_mask : 0);
		fol.pending = 0;
	}
}

static int in_gate(uint32_t a) { return a >= gate_lo && a < gate_hi; }

static void gate_check(uint32_t a)
{
	if (gate_on && in_gate(a)) {
		struct reg *s = find(gate_status_addr);

		if (!s || !(s->val & gate_status_mask))
			viol("access to the HSI0 block while the domain is off", a);
	}
}

uint32_t usbmon_rd32(uintptr_t addr)
{
	uint32_t v;
	struct reg *r;

	settle();
	gate_check((uint32_t)addr);
	if (addr >= 0x17900000u && addr < 0x17910000u) {
		v = model_rd32(addr);
		if (ov_on && addr - 0x17900000u == ov_off)
			v = (v & ~ov_mask) | (ov_val & ov_mask);
	} else {
		r = find((uint32_t)addr);
		if (!r) {
			if (strict)
				viol("read of an undeclared register", (uint32_t)addr);
			v = 0;
		} else {
			r->nreads++;
			v = ((r->val & ~r->stuck_mask) | (r->stuck_val & r->stuck_mask)) ^ (r->nreads >= r->flip_from ? r->flip : 0);
		}
	}
	if (nlog < NLOG) {
		logv[nlog].kind = 0; logv[nlog].addr = (uint32_t)addr; logv[nlog].val = v; logv[nlog].t = now_us; nlog++;
	}
	return v;
}

void usbmon_wr32(uintptr_t addr, uint32_t v)
{
	struct reg *r;

	settle();
	gate_check((uint32_t)addr);
	if (nlog < NLOG) {
		logv[nlog].kind = 1; logv[nlog].addr = (uint32_t)addr; logv[nlog].val = v; logv[nlog].t = now_us; nlog++;
	}
	if (addr >= 0x17900000u && addr < 0x17910000u) {
		model_wr32(addr, v);
		return;
	}
	r = find((uint32_t)addr);
	if (!r) {
		if (strict)
			viol("write of an undeclared register", (uint32_t)addr);
		return;
	}
	if (!(r->flags & RF_RO))
		r->val = v & ~r->clr_mask;
	if (fol.active && (uint32_t)addr == fol.cfg_addr) {
		fol.pending = 1;
		fol.due = now_us + fol.delay_us;
		if (!fol.delay_us)
			settle();
	}
}

void usbmon_delay_us(uint32_t us) { now_us += us; model_delay_us(us); }
uint64_t usbmon_ticks(void) { return model_ticks(); }

/* ---- the test API of ladder.c / ladder_usb.c ---- */
static struct lad_state st;
static struct lad_cfg cfg;

int n_nops(void) { return LAD_NOPS; }
int n_default_stop(void) { struct lad_cfg c; lad_default_cfg(&c); return (int)c.stop_after; }
int n_default_poweron(void) { struct lad_cfg c; lad_default_cfg(&c); return (int)c.allow_pd_poweron; }
int n_selfcheck(void) { return lad_selfcheck(); }
int n_run(uint32_t stop, uint32_t allow_poweron, uint32_t pd_wait_us)
{
	cfg.stop_after = stop;
	cfg.allow_pd_poweron = allow_poweron;
	cfg.pd_wait_us = pd_wait_us;
	return lad_run(&st, &cfg);
}
int n_run_null(void) { return lad_run(&st, 0); }
int n_err(void) { return st.err; }
int n_err_op(void) { return st.err_op; }
int n_nrec(void) { return st.nrec; }
void n_rec(int i, uint32_t *op, uint32_t *v0, uint32_t *v1) { *op = st.rec[i].op; *v0 = st.rec[i].v0; *v1 = st.rec[i].v1; }
int n_rung_done(void) { return st.rung_done; }
int n_pd_was_on(void) { return st.pd_was_on; }
int n_soft(void) { return st.soft_mismatch; }
uint32_t n_gsnpsid(void) { return st.gsnpsid; }
uint32_t n_sizeof_state(void) { return sizeof(st); }
void n_poison_state(void) { memset(&st, 0xa5, sizeof(st)); }

static struct usbmon *um;
int n_usb_new(uint32_t ring_size) { um = t_new(ring_size); return um != 0; }
int n_usb_start(const uint8_t *boot_id, uint32_t ring_size)
{
	struct usbmon_cfg c;
	int e = 12345, rc;			/* a stop code the wrapper must write (12345 is not one) */

	memset(&c, 0, sizeof(c));
	c.dwc3_base = 0x17900000u;
	c.ring = t_ring();
	c.ring_size = ring_size;
	memcpy(c.boot_id, boot_id, 16);
	c.refclk_hz = 19200000;
	c.fladj = 0x20;
	c.gfladj_refclk_lpm_sel = 1;
	rc = lad_usb_start(um, &c, &e);
	return rc == e ? e : -9999;		/* the return value and the stored one must agree */
}
int n_usb_wait(unsigned rung, uint32_t flag, uint32_t max_polls, uint32_t delay) { return lad_usb_wait(um, rung, flag, max_polls, delay); }
uint32_t n_usb_flags(void) { return um->flags; }
