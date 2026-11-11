/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-047: the USB log transport of loader-diag-usbmon / loader-diag-usbmon-fault. This translation unit is NAT-044's
 * markerlib4.c (NAT-022's markerlib.c with the deadline and the reset report) as patched by patch_loader5.py, plus the routines
 * below, which need markerlib.c's static helpers (mk_draw, show, mk_cnt) and therefore live in the same unit. The build
 * compiles this file instead of markerlib4.c. The NAT-041 engine (usbmon.c) and the NAT-045 ladder (ladder.c, ladder_usb.c)
 * are linked from their own directories, unmodified.
 *
 * The loader is linked at address 0 and runs from wherever S-Boot loaded it: it has no relocation step, so nothing here holds
 * a pointer in static initialised data (pointers are assigned at run time, from PC-relative addresses). */
#include "markerlib4.c"
#include "usbmon.h"
#include "usbmon_port.h"
#include "ladder.h"

#ifndef NAT047_FAULT
#define NAT047_FAULT 0
#endif
#ifndef NAT047_TAG
#error "NAT047_TAG must be given by the build (the image name; it is hashed into the boot id)"
#endif

#define NAT047_DWC3_BASE	0x17900000UL	/* NAT-040: usb 0x17900000, the controller the ladder powers */
#define NAT047_RING_BYTES	32768u
#define NAT047_LINE_MAX		200u
#define NAT047_CHUNK		512u		/* replay of the RAM log: bytes per TEXT record */
#define NAT047_CONNECT_S	3u		/* bounded wait for the bus reset after the engine started; the run goes on without it */
#define NAT047_CONFIG_S		8u		/* fault image: bounded wait for the host to configure the device before the BRK */
#define NAT047_FLADJ		0x20u		/* vendor DT snps,quirk-frame-length-adjustment */
#define NAT047_LPM_SEL		1u		/* vendor DT snps,gfladj-refclk-lpm-sel-quirk */

/* g_nat047.phase */
enum { N47_IDLE = 0, N47_LAD_RO = 1, N47_LAD_W = 2, N47_START = 3, N47_CONNECT = 4, N47_UP = 5, N47_STOP = 6 };

/* Frame kind MK_USB idx; the status word is documented in README.md and decoded by decode47.py. */
enum { N47_I_STATUS = 0, N47_I_ERR = 1, N47_I_ERROP = 2, N47_I_NREC = 3, N47_I_WRITTEN = 5 };

#define N47_S_UP	0x0001u
#define N47_S_CONNECTED	0x0002u
#define N47_S_CONFIGURED 0x0004u
#define N47_S_NONCE	0x0008u
#define N47_S_FAULTED	0x0010u
#define N47_S_POLLFAULT	0x0020u
#define N47_S_PDWASON	0x0040u

struct nat047 {
	struct usbmon m;			/* first: the engine's DMA block must start on a 64-byte boundary */
	struct lad_state lad_ro;		/* L0-L2, read only */
	struct lad_state lad;			/* L0-L5, writes */
	uint8_t ring[NAT047_RING_BYTES];
	char line[NAT047_LINE_MAX];
	uint32_t line_len;
	uint32_t phase;
	uint32_t up, polling, log_on;
	uint32_t faulted, poll_faulted, in_fault;
	int32_t err;				/* the ladder stop code of the phase that stopped, 0 when the engine is up */
	uint32_t err_op;			/* its op index; 0xffff when not an op */
	uint32_t nrec;				/* records of the last ladder run */
	int32_t connect_err;			/* L7 result: 0, or LAD_ERR(7, TIMEOUT) */
	uint32_t holds;
};

struct nat047 g_nat047 __attribute__((aligned(64)));

static char *n47_s(char *p, const char *s)
{
	while (*s)
		*p++ = *s++;
	return p;
}

static char *n47_x(char *p, uint64_t v)
{
	static const char d[] = "0123456789abcdef";
	int started = 0;

	*p++ = '0';
	*p++ = 'x';
	for (int i = 60; i >= 0; i -= 4) {
		unsigned x = (unsigned)(v >> i) & 0xfu;
		if (x || started || i == 0) {
			*p++ = d[x];
			started = 1;
		}
	}
	return p;
}

static char *n47_d(char *p, int32_t v)
{
	char t[12];
	int n = 0;
	uint32_t u = v < 0 ? 0u - (uint32_t)v : (uint32_t)v;

	if (v < 0)
		*p++ = '-';
	do {
		t[n++] = (char)('0' + u % 10u);
		u /= 10u;
	} while (u);
	while (n)
		*p++ = t[--n];
	return p;
}

static void n47_text(const char *b, char *end)
{
	usbmon_log(&g_nat047.m, USBMON_K_TEXT, b, (uint16_t)(end - b));
}

static uint32_t n47_status(void)
{
	const struct nat047 *n = &g_nat047;
	uint32_t f = n->up ? n->m.flags : 0;

	return (n->up ? N47_S_UP : 0) | ((f & USBMON_F_CONNECTED) ? N47_S_CONNECTED : 0) |
	       ((f & USBMON_F_CONFIGURED) ? N47_S_CONFIGURED : 0) | ((f & USBMON_F_NONCE_SET) ? N47_S_NONCE : 0) |
	       (n->faulted ? N47_S_FAULTED : 0) | (n->poll_faulted ? N47_S_POLLFAULT : 0) |
	       ((n->lad.pd_was_on == 1 || n->lad_ro.pd_was_on == 1) ? N47_S_PDWASON : 0) | ((n->phase & 0xfu) << 8) |
	       ((uint32_t)(n->lad.rung_done & 0xf) << 12);
}

/* Drawn at once (no dwell): a hang inside the ladder leaves the phase on the screen until the watchdog. */
static void n47_draw_status(void)
{
	mk_draw(mk_frame(MK_USB, N47_I_STATUS, n47_status()), 0, 1);
}

void nat047_poll(void)
{
	struct nat047 *n = &g_nat047;

	if (!n->up || n->polling)
		return;
	n->polling = 1;
	usbmon_poll(&n->m);
	n->polling = 0;
}

static const char *n47_stage_name(uint32_t s)
{
	switch (s) {
	case MK_ST_ENTRY: return "entry";
	case MK_ST_LOADER_MAIN: return "loader_main";
	case MK_ST_LOADER_FB: return "fb";
	case MK_ST_LOADER_MEM: return "mem";
	case MK_ST_LOADER_ZERO: return "zero";
	case MK_ST_LOADER_COPY: return "copy";
	case MK_ST_LOADER_ADT: return "adt";
	case MK_ST_LOADER_CLEAN: return "clean";
	case MK_ST_LOADER_FAIL: return "fail";
	case MK_ST_PRE_JUMP: return "pre_jump";
	case MK_ST_RESET: return "reset";
	case MK_ST_EXC: return "exception";
	default: return "stage";
	}
}

void nat047_stage(uint32_t stage)
{
	if (!g_nat047.up)
		return;
	usbmon_stage(&g_nat047.m, stage, n47_stage_name(stage));
}

static void n47_flush_line(void)
{
	struct nat047 *n = &g_nat047;

	if (n->line_len)
		usbmon_log(&n->m, USBMON_K_TEXT, n->line, (uint16_t)n->line_len);
	n->line_len = 0;
}

void nat047_log_char(char c)
{
	struct nat047 *n = &g_nat047;

	if (!n->log_on)
		return;
	if (c == '\n') {
		n47_flush_line();
		return;
	}
	n->line[n->line_len++] = c;
	if (n->line_len >= NAT047_LINE_MAX)
		n47_flush_line();
}

/* The ladder's result, as text the host archives: a summary line and one line per hardware access. */
static void n47_report_ladder(char tag, const struct lad_state *s)
{
	char b[200];
	char *p = b;

	p = n47_s(p, "LAD ");
	*p++ = tag;
	p = n47_s(p, " err=");
	p = n47_d(p, s->err);
	p = n47_s(p, " err_op=");
	p = n47_d(p, s->err_op);
	p = n47_s(p, " rung=");
	p = n47_d(p, s->rung_done);
	p = n47_s(p, " pd_was_on=");
	p = n47_d(p, s->pd_was_on == 0xff ? -1 : s->pd_was_on);
	p = n47_s(p, " nrec=");
	p = n47_d(p, s->nrec);
	p = n47_s(p, " soft=");
	p = n47_d(p, s->soft_mismatch);
	p = n47_s(p, " gsnpsid=");
	p = n47_x(p, s->gsnpsid);
	n47_text(b, p);
	for (uint32_t i = 0; i < s->nrec && i < LAD_NOPS; i++) {
		p = b;
		p = n47_s(p, "LR ");
		*p++ = tag;
		*p++ = ' ';
		p = n47_d(p, s->rec[i].op);
		p = n47_s(p, " v0=");
		p = n47_x(p, s->rec[i].v0);
		p = n47_s(p, " v1=");
		p = n47_x(p, s->rec[i].v1);
		n47_text(b, p);
		nat047_poll();
	}
}

static void n47_note_stop(int32_t err, const struct lad_state *s)
{
	struct nat047 *n = &g_nat047;

	n->err = err;
	n->err_op = s ? s->err_op : 0xffffu;
	n->nrec = s ? s->nrec : 0;
	n->phase = N47_STOP;
}

void nat047_bringup(const char *log, uint32_t log_len)
{
	struct nat047 *n = &g_nat047;
	struct lad_cfg c;
	struct usbmon_cfg uc;
	uint64_t id = mk_cnt(), h = 0xcbf29ce484222325ull;
	int32_t e = 0;

	n->phase = N47_LAD_RO;
	n->err_op = 0xffffu;
	n47_draw_status();
	lad_default_cfg(&c);
	c.stop_after = 2;
	c.allow_pd_poweron = 0;
	e = lad_run(&n->lad_ro, &c);
	n->nrec = n->lad_ro.nrec;
	if (e) {
		n47_note_stop(e, &n->lad_ro);
		n47_draw_status();
		return;
	}
	n->phase = N47_LAD_W;
	n47_draw_status();
	c.stop_after = LAD_LAST_RUNG;
	c.allow_pd_poweron = 1;
	e = lad_run(&n->lad, &c);
	n->nrec = n->lad.nrec;
	if (e) {
		n47_note_stop(e, &n->lad);
		n47_draw_status();
		return;
	}
	n->phase = N47_START;
	n47_draw_status();
	for (const char *t = NAT047_TAG; *t; t++) {
		h ^= (uint8_t)*t;
		h *= 0x100000001b3ull;
	}
	for (unsigned i = 0; i < 8; i++) {
		uc.boot_id[i] = (uint8_t)(id >> (8 * i));
		uc.boot_id[8 + i] = (uint8_t)(h >> (8 * i));
	}
	uc.dwc3_base = NAT047_DWC3_BASE;
	uc.ring = n->ring;
	uc.ring_size = NAT047_RING_BYTES;
	uc.refclk_hz = 0;
	uc.fladj = NAT047_FLADJ;
	uc.gfladj_refclk_lpm_sel = NAT047_LPM_SEL;
	if (lad_usb_start(&n->m, &uc, &e)) {
		n47_note_stop(e, 0);
		n47_draw_status();
		return;
	}
	n->up = 1;
	n->err = 0;
	n->err_op = 0xffffu;
	{
		char b[160];
		char *p = b;

		p = n47_s(p, "NAT047 ");
		p = n47_s(p, NAT047_TAG);
		p = n47_s(p, " deadline_s=");
		p = n47_d(p, NAT044_DEADLINE_S);
		p = n47_s(p, " fault=");
		p = n47_d(p, NAT047_FAULT);
		usbmon_log(&n->m, USBMON_K_BOOT, b, (uint16_t)(p - b));
	}
	nat047_stage(MK_ST_LOADER_MAIN);	/* the stage that was current when the engine came up (mk_stage ran before it existed) */
	n47_report_ladder('R', &n->lad_ro);
	n47_report_ladder('W', &n->lad);
	for (uint32_t off = 0; off < log_len; off += NAT047_CHUNK) {
		uint32_t len = log_len - off < NAT047_CHUNK ? log_len - off : NAT047_CHUNK;

		usbmon_log(&n->m, USBMON_K_TEXT, log + off, (uint16_t)len);
		nat047_poll();
	}
	n->log_on = 1;
	n->phase = N47_CONNECT;
	n47_draw_status();
	/* L7, bounded in time (not in polls): the bus reset needs a host, and a phone with no cable must go on to the hold loop. */
	{
		uint64_t t0 = mk_cnt(), lim = mk_freq() * NAT047_CONNECT_S;

		while (!(n->m.flags & USBMON_F_CONNECTED) && mk_cnt() - t0 < lim) {
			nat044_tick();
			nat047_poll();
		}
	}
	n->connect_err = (n->m.flags & USBMON_F_CONNECTED) ? 0 : LAD_ERR(LAD_USB_RUNG_CONNECT, LAD_E_TIMEOUT);
	n->phase = N47_UP;
	n47_draw_status();
}

/* The exception loop calls this once with what loader_exception() read. The loader's vectors clobber x0 and save nothing else,
 * so the FAULT record carries ESR, ELR, FAR, SPSR and SP and leaves x0..x30 zero (README.md: not captured). A fault while the
 * engine itself was polling takes the engine out of service: its state is unknown and polling it again could fault forever. */
void nat047_fault(uint32_t slot, uint64_t esr, uint64_t elr, uint64_t far)
{
	struct nat047 *n = &g_nat047;
	struct usbmon_exc_in in;
	char b[160];
	char *p = b;
	uint64_t spsr, sp;

	n->faulted++;
	if (n->in_fault)
		return;
	n->in_fault = 1;
	if (n->polling) {
		n->up = 0;
		n->poll_faulted = 1;
		return;
	}
	if (!n->up)
		return;
	__asm__ volatile("mrs %0, spsr_el1" : "=r"(spsr));
	__asm__ volatile("mov %0, sp" : "=r"(sp));
	in.esr = esr;
	in.elr = elr;
	in.far = far;
	in.spsr = spsr;
	in.sp = sp;
	for (unsigned i = 0; i < 31; i++)
		in.x[i] = 0;
	usbmon_stage(&n->m, MK_ST_EXC, n47_stage_name(MK_ST_EXC));
	p = n47_s(p, "EXCEPTION slot=");
	p = n47_d(p, (int32_t)slot);
	p = n47_s(p, " esr=");
	p = n47_x(p, esr);
	p = n47_s(p, " elr=");
	p = n47_x(p, elr);
	p = n47_s(p, " far=");
	p = n47_x(p, far);
	p = n47_s(p, " spsr=");
	p = n47_x(p, spsr);
	n47_text(b, p);
	usbmon_fault_record(&n->m, &in);
}

void nat047_hold(uint32_t stage, uint32_t code)
{
	struct nat047 *n = &g_nat047;
	char b[96];
	char *p = b;

	n->holds++;
	if (!n->up)
		return;
	p = n47_s(p, "HOLD stage=");
	p = n47_x(p, stage);
	p = n47_s(p, " code=");
	p = n47_x(p, code);
	n47_text(b, p);
#if NAT047_FAULT
	if (stage == MK_ST_PRE_JUMP) {
		/* The controlled fault: the host gets a bounded time to configure the device, then BRK #0x1234 takes the loader's own
		 * vector, exception stack and exception loop. Only when the engine is up: without a log channel it proves nothing new. */
		uint64_t t0 = mk_cnt(), lim = mk_freq() * NAT047_CONFIG_S;

		while (!(n->m.flags & USBMON_F_CONFIGURED) && mk_cnt() - t0 < lim) {
			nat044_tick();
			nat047_poll();
		}
		usbmon_text(&n->m, "controlled BRK #0x1234 follows");
		__asm__ volatile("brk #0x1234");
	}
#endif
}

/* The report frames of the hold and exception loops: status word, ladder stop code, its op, record count, bytes written. */
void nat047_show(uint32_t *prev, struct mk_kick *k)
{
	const struct nat047 *n = &g_nat047;

	show(prev, mk_frame(MK_USB, N47_I_STATUS, n47_status()), k);
	show(prev, mk_frame(MK_USB, N47_I_ERR, (uint32_t)(-n->err) & 0xffffu), k);
	show(prev, mk_frame(MK_USB, N47_I_ERROP, n->err_op), k);
	show(prev, mk_frame(MK_USB, N47_I_NREC, n->nrec), k);
	show(prev, mk_frame(MK_USB, N47_I_WRITTEN, n->up ? (uint32_t)n->m.written : 0), k);
}
