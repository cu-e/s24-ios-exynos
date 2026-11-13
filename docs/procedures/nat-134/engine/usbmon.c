// SPDX-License-Identifier: GPL-2.0-only
/*
 * usbmon: polled EP0-only DWC3 device engine (NAT-041). See usbmon.h for the wire protocol.
 *
 * The control-endpoint state machine, the device-endpoint command sequences and the event decoding follow the Linux dwc3
 * driver in the pinned vendor kernel `s24-linux` 417484173abc2c4fa93e738ea82ad9f2e84911b1 (drivers/usb/dwc3/{core.c,
 * gadget.c,ep0.c}, GPL-2.0, Copyright (C) 2010-2011 Texas Instruments Incorporated - https://www.ti.com, Authors: Felipe
 * Balbi, Sebastian Andrzej Siewior). Function names below name the vendor function whose behaviour a function keeps.
 * What differs on purpose: no interrupts and no request queues (one reply buffer, one OUT buffer), high speed only, no
 * LPM, no U1/U2, no endpoint other than ep0 (physical endpoints 0 = OUT, 1 = IN).
 * Nothing in this file has run on the phone.
 */
#include "usbmon.h"
#define USBMON_ENGINE_TU 1	/* NAT-130: this unit owns the port's checksum-mode code */
#include "usbmon_port.h"

#define RD(m, off)	usbmon_rd32((m)->base + (off))
#define WR(m, off, v)	usbmon_wr32((m)->base + (off), (v))

/* ---------------------------------------------------------------- plain memory helpers (no libc) */

static void mcopy(void *dst, const void *src, size_t n)
{
	uint8_t *d = dst;
	const uint8_t *s = src;

	while (n--)
		*d++ = *s++;
}

static void mzero(void *dst, size_t n)
{
	uint8_t *d = dst;

	while (n--)
		*d++ = 0;
}

static size_t slen(const char *s)
{
	size_t n = 0;

	while (s[n])
		n++;
	return n;
}

uint8_t usbmon_crc8(const uint8_t *p, size_t n)
{
	uint8_t crc = 0;
	size_t i;
	int b;

	for (i = 0; i < n; i++) {
		crc ^= p[i];
		for (b = 0; b < 8; b++)
			crc = (crc & 0x80) ? (uint8_t)((crc << 1) ^ 0x07) : (uint8_t)(crc << 1);
	}
	return crc;
}

/* ---------------------------------------------------------------- the log stream */

static void ring_store(struct usbmon *m, uint64_t pos, const uint8_t *src, size_t n)
{
	size_t i;

	for (i = 0; i < n; i++)
		m->ring[(pos + i) % m->ring_size] = src[i];
}

static void ring_load(const struct usbmon *m, uint64_t pos, uint8_t *dst, size_t n)
{
	size_t i;

	for (i = 0; i < n; i++)
		dst[i] = m->ring[(pos + i) % m->ring_size];
}

static void rec_header(uint8_t *h, uint32_t seq, uint16_t len, uint8_t kind)
{
	h[0] = (uint8_t)seq;
	h[1] = (uint8_t)(seq >> 8);
	h[2] = (uint8_t)(seq >> 16);
	h[3] = (uint8_t)(seq >> 24);
	h[4] = (uint8_t)len;
	h[5] = (uint8_t)(len >> 8);
	h[6] = kind;
	h[7] = usbmon_crc8(h, 7);
}

/* Make room for `total` more bytes by dropping whole records from the old end, so the retained stream always begins at a
 * record header. */
static void ring_make_room(struct usbmon *m, uint32_t total)
{
	uint8_t h[USBMON_REC_HDR];

	while (m->written + total - m->oldest > m->ring_size) {
		ring_load(m, m->oldest, h, sizeof(h));
		m->oldest += USBMON_REC_HDR + ((uint32_t)h[4] | ((uint32_t)h[5] << 8));
	}
}

static void log_put(struct usbmon *m, uint8_t kind, const void *data, uint16_t len, uint32_t ncopied, int commit)
{
	uint8_t h[USBMON_REC_HDR];
	uint32_t total = USBMON_REC_HDR + len, seq;
	uint64_t pos;
	uint32_t n;

	if (len > USBMON_REC_MAX || total > m->ring_size) {
		m->dropped++;
		return;
	}
	ring_make_room(m, total);
	seq = m->seq++;		/* reserved first: an interrupted append leaves a sequence gap, never a duplicate */
	rec_header(h, seq, len, kind);
	pos = m->written;
	n = ncopied;
	if (n > USBMON_REC_HDR) {
		ring_store(m, pos, h, USBMON_REC_HDR);
		if (n - USBMON_REC_HDR > len)
			n = USBMON_REC_HDR + len;
		ring_store(m, pos + USBMON_REC_HDR, data, n - USBMON_REC_HDR);
	} else {
		ring_store(m, pos, h, n);
	}
	if (commit) {
		ring_store(m, pos, h, USBMON_REC_HDR);
		ring_store(m, pos + USBMON_REC_HDR, data, len);
		m->written = pos + total;	/* the commit point: nothing beyond `written` is ever served */
		if (m->dropped != m->dropped_reported && kind != USBMON_K_DROP) {
			uint32_t d = m->dropped;

			m->dropped_reported = d;	/* set first: the drop record itself must not recurse */
			log_put(m, USBMON_K_DROP, &d, sizeof(d), 0, 1);
		}
	}
}

void usbmon_log(struct usbmon *m, uint8_t kind, const void *data, uint16_t len)
{
	log_put(m, kind, data, len, 0, 1);
}

#ifdef USBMON_TESTING
void usbmon_log_interrupted(struct usbmon *m, uint8_t kind, const void *data, uint16_t len, uint32_t ncopied)
{
	log_put(m, kind, data, len, ncopied, 0);
}
#endif

void usbmon_text(struct usbmon *m, const char *s)
{
	size_t n = slen(s);

	if (n > USBMON_REC_MAX)
		n = USBMON_REC_MAX;
	usbmon_log(m, USBMON_K_TEXT, s, (uint16_t)n);
}

void usbmon_stage(struct usbmon *m, uint32_t stage, const char *text)
{
	uint8_t buf[4 + USBMON_REC_MAX];
	size_t n = slen(text);

	if (n > USBMON_REC_MAX - 4)
		n = USBMON_REC_MAX - 4;
	buf[0] = (uint8_t)stage;
	buf[1] = (uint8_t)(stage >> 8);
	buf[2] = (uint8_t)(stage >> 16);
	buf[3] = (uint8_t)(stage >> 24);
	mcopy(buf + 4, text, n);
	m->stage = stage;
	usbmon_log(m, USBMON_K_STAGE, buf, (uint16_t)(4 + n));
}

/* ---------------------------------------------------------------- exception frame */

void usbmon_fault_record(struct usbmon *m, const struct usbmon_exc_in *r)
{
	uint8_t p[28];
	int i;

	m->faults++;
	if (!m->exc.valid) {
		m->exc.stage = m->stage;
		m->exc.esr = r->esr;
		m->exc.elr = r->elr;
		m->exc.far = r->far;
		m->exc.spsr = r->spsr;
		m->exc.sp = r->sp;
		for (i = 0; i < 31; i++)
			m->exc.x[i] = r->x[i];
		__asm__ volatile("" ::: "memory");
		m->exc.valid = 1;	/* last: GET_EXC never serves a half-written frame as valid */
	}
	m->exc.count = m->faults;
	for (i = 0; i < 8; i++) {
		p[i] = (uint8_t)(r->esr >> (8 * i));
		p[8 + i] = (uint8_t)(r->elr >> (8 * i));
		p[16 + i] = (uint8_t)(r->far >> (8 * i));
	}
	for (i = 0; i < 4; i++)
		p[24 + i] = (uint8_t)(m->stage >> (8 * i));
	usbmon_log(m, USBMON_K_FAULT, p, sizeof(p));
	m->flags |= USBMON_F_FAULT | USBMON_F_HOLD;
}

void usbmon_hold(struct usbmon *m)
{
	m->flags |= USBMON_F_HOLD;
	for (;;)
		usbmon_poll(m);
}

void usbmon_fault(struct usbmon *m, const struct usbmon_exc_in *regs)
{
	usbmon_fault_record(m, regs);
	usbmon_hold(m);
}

/* ---------------------------------------------------------------- DWC3 device endpoint commands */

/* dwc3_send_gadget_ep_cmd(): parameters, then the command with CMDACT, then poll CMDACT. GUSB2PHYCFG SUSPHY and
 * ENBLSLPM are cleared once at init and never set again, which is the state the vendor function establishes around each
 * command at high speed. */
static int dep_cmd(struct usbmon *m, unsigned int ep, uint32_t cmd, uint32_t p0, uint32_t p1, uint32_t p2)
{
	uint32_t b = DWC3_DEP_BASE(ep), reg = 0;
	unsigned int i;

	WR(m, b + DWC3_DEPCMDPAR0, p0);
	WR(m, b + DWC3_DEPCMDPAR1, p1);
	WR(m, b + DWC3_DEPCMDPAR2, p2);
	cmd |= DWC3_DEPCMD_CMDACT;
	WR(m, b + DWC3_DEPCMD, cmd);
	for (i = 0; i < 5000; i++) {
		reg = RD(m, b + DWC3_DEPCMD);
		if (!(reg & DWC3_DEPCMD_CMDACT))
			break;
		usbmon_delay_us(1);
	}
	m->last_depcmd = reg;
	if (reg & DWC3_DEPCMD_CMDACT) {
		m->last_err = USBMON_E_CMD;
		return USBMON_E_CMD;
	}
	if (DWC3_DEPCMD_STATUS(reg)) {
		m->last_err = USBMON_E_CMD;
		return USBMON_E_CMD;
	}
	if (DWC3_DEPCMD_CMD(cmd) == DWC3_DEPCMD_STARTTRANSFER && ep < 3) {
		m->ep_started[ep] = 1;
		m->ep_rsc[ep] = (uint8_t)DWC3_DEPCMD_GET_RSC_IDX(reg);	/* dwc3_gadget_ep_get_transfer_index() */
	}
	return 0;
}

/* __dwc3_gadget_ep_enable() for the two control endpoints: DEPCFG, DEPXFERCFG, then DALEPENA. */
static int ep0_enable(struct usbmon *m, unsigned int ep, uint32_t action, int first)
{
	uint32_t p0, p1;
	int ret;

	p0 = DWC3_DEPCFG_EP_TYPE(DWC3_DEPCMD_TYPE_CONTROL) | DWC3_DEPCFG_MAX_PACKET_SIZE(m->mps) | action;
	if (ep & 1)
		p0 |= DWC3_DEPCFG_FIFO_NUMBER(ep >> 1);
	p1 = DWC3_DEPCFG_XFER_COMPLETE_EN | DWC3_DEPCFG_XFER_NOT_READY_EN | DWC3_DEPCFG_EP_NUMBER(ep);
	ret = dep_cmd(m, ep, DWC3_DEPCMD_SETEPCONFIG, p0, p1, 0);
	if (ret)
		return ret;
	if (first) {
		ret = dep_cmd(m, ep, DWC3_DEPCMD_SETTRANSFRESOURCE, DWC3_DEPXFERCFG_NUM_XFER_RES(1), 0, 0);
		if (ret)
			return ret;
		WR(m, DWC3_DALEPENA, RD(m, DWC3_DALEPENA) | DWC3_DALEPENA_EP(ep));
	}
	return 0;
}

/* ---------------------------------------------------------------- EP0 transfers */

static void trb_write(struct usbmon *m, unsigned int idx, uint64_t buf, uint32_t len, uint32_t type, int chain)
{
	volatile struct dwc3_trb *t = &m->dma.trb[idx];
	uint32_t ctrl = type | DWC3_TRB_CTRL_HWO | DWC3_TRB_CTRL_ISP_IMI;

	ctrl |= chain ? DWC3_TRB_CTRL_CHN : (DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_LST);
	usbmon_dma_st32(&t->bpl, (uint32_t)buf);
	usbmon_dma_st32(&t->bph, (uint32_t)(buf >> 32));
	usbmon_dma_st32(&t->size, len);
	usbmon_dma_st32(&t->ctrl, ctrl);
}

/* dwc3_ep0_start_trans(): publish the TRBs, then DEPSTARTXFER with the TRB address (param0 = high, param1 = low). */
static int ep0_start_trans(struct usbmon *m, unsigned int ep, unsigned int ntrb)
{
	uint64_t a;
	int ret;

	if (m->ep_started[ep])
		return 0;
	usbmon_dma_sync(m->dma.trb, ntrb * sizeof(struct dwc3_trb));
	a = usbmon_dma_addr(m->dma.trb);
	ret = dep_cmd(m, ep, DWC3_DEPCMD_STARTTRANSFER, (uint32_t)(a >> 32), (uint32_t)a, 0);
	if (ret)
		return ret;
	m->ep0_next = EP0_NEXT_COMPLETE;
	return 0;
}

/* dwc3_ep0_out_start(): a SETUP TRB on ep0 OUT. */
static int ep0_out_start(struct usbmon *m)
{
	usbmon_dma_sync(m->dma.setup, sizeof(m->dma.setup));
	trb_write(m, 0, usbmon_dma_addr(m->dma.setup), 8, DWC3_TRBCTL_CONTROL_SETUP, 0);
	return ep0_start_trans(m, 0, 1);
}

/* dwc3_ep0_end_control_data() */
static void ep0_end_control_data(struct usbmon *m, unsigned int ep)
{
	if (!m->ep_rsc[ep] && ep)
		return;
	(void)dep_cmd(m, ep, DWC3_DEPCMD_ENDTRANSFER | DWC3_DEPCMD_CMDIOC | DWC3_DEPCMD_PARAM(m->ep_rsc[ep]), 0, 0, 0);
	m->ep_started[ep] = 0;
	m->ep_rsc[ep] = 0;
}

/* dwc3_ep0_stall_and_restart(): stall ep0, forget any started transfer, go back to waiting for a SETUP. */
static void ep0_stall_and_restart(struct usbmon *m)
{
	m->stalls++;
	m->ep_started[1] = 0;
	(void)dep_cmd(m, 0, DWC3_DEPCMD_SETSTALL, 0, 0, 0);
	m->out_pending = 0;
	m->ep0state = EP0_SETUP_PHASE;
	(void)ep0_out_start(m);
}

/* dwc3_ep0_reset_state() */
static void ep0_reset_state(struct usbmon *m)
{
	unsigned int dir;

	if (m->ep0state != EP0_SETUP_PHASE) {
		dir = m->expect_in ? 1u : 0u;
		if (m->ep0state == EP0_DATA_PHASE)
			ep0_end_control_data(m, dir);
		else
			ep0_end_control_data(m, dir ? 0u : 1u);
		ep0_stall_and_restart(m);
	}
}

/* ---------------------------------------------------------------- bulk-OUT receive (NAT-076) */

/* The vendor sequence for a non-control endpoint, from drivers/usb/dwc3/ep0.c dwc3_ep0_set_config() and gadget.c
 * __dwc3_gadget_ep_enable(): DEPSTARTCFG(2) on ep0 at SET_CONFIGURATION, then DEPCFG (INIT), DEPXFERCFG(1), DALEPENA, the TRB
 * ring with a link TRB, and a STARTTRANSFER on the (still empty) first TRB so that every later TRB is queued with
 * UPDATETRANSFER. The completion of an IOC TRB arrives as XferInProgress (DEPCFG enables it for non-control endpoints) and
 * is handled like dwc3_gadget_endpoint_trbs_complete(). */

static uint32_t rx_chunk_max(const struct usbmon *m)
{
	return m->rx_direct ? USBMON_RX_DIRECT_MAX : USBMON_RX_STAGE_BYTES;
}

static void rx_ring_init(struct usbmon *m)
{
	unsigned int i;
	uint64_t a = usbmon_dma_addr(m->dma.rxtrb);
	volatile struct dwc3_trb *t;

	for (i = 0; i < USBMON_RX_TRBS; i++) {
		t = &m->dma.rxtrb[i];
		usbmon_dma_st32(&t->bpl, 0);
		usbmon_dma_st32(&t->bph, 0);
		usbmon_dma_st32(&t->size, 0);
		usbmon_dma_st32(&t->ctrl, 0);
	}
	/* the link TRB: back to slot 0, HWO set and never cleared (vendor __dwc3_gadget_ep_enable) */
	t = &m->dma.rxtrb[USBMON_RX_TRBS - 1];
	usbmon_dma_st32(&t->bpl, (uint32_t)a);
	usbmon_dma_st32(&t->bph, (uint32_t)(a >> 32));
	usbmon_dma_st32(&t->ctrl, DWC3_TRBCTL_LINK_TRB | DWC3_TRB_CTRL_HWO);
	usbmon_dma_sync(m->dma.rxtrb, sizeof(m->dma.rxtrb));
	m->rx_enq = 0;
	m->rx_deq = 0;
}

static int rx_start(struct usbmon *m)
{
	uint64_t a = usbmon_dma_addr(m->dma.rxtrb);

	return dep_cmd(m, USBMON_RX_EP, DWC3_DEPCMD_STARTTRANSFER, (uint32_t)(a >> 32), (uint32_t)a, 0);
}

/* dwc3_stop_active_transfer(): ENDTRANSFER with the resource index and CMDIOC; nothing new may be started on the endpoint
 * until its command-complete event has been handled (the vendor's DWC3_EP_END_TRANSFER_PENDING, which also makes a second
 * request while one is pending a no-op). */
static void rx_end(struct usbmon *m)
{
	if (!m->ep_started[USBMON_RX_EP] || m->rx_end_pending)
		return;
	(void)dep_cmd(m, USBMON_RX_EP, DWC3_DEPCMD_ENDTRANSFER | DWC3_DEPCMD_CMDIOC | DWC3_DEPCMD_PARAM(m->ep_rsc[USBMON_RX_EP]),
		      0, 0, 0);
	m->rx_end_pending = 1;
}

/* dwc3_ep0_set_config() -> dwc3_gadget_start_config(dwc, 2), then dwc3_gadget_ep_enable() of the bulk endpoint */
static int rx_enable(struct usbmon *m)
{
	uint32_t p0, p1;
	int ret;

	if (!m->rx_present || m->rx_enabled)
		return 0;
	if (m->rx_end_pending)
		return USBMON_E_CMD;
	ret = dep_cmd(m, 0, DWC3_DEPCMD_DEPSTARTCFG | DWC3_DEPCMD_PARAM(2), 0, 0, 0);
	if (ret)
		return ret;
	/* dwc3_gadget_set_ep_config(): no FIFO number for an OUT endpoint, no XferNotReady for a bulk endpoint, XferInProgress on */
	p0 = DWC3_DEPCFG_EP_TYPE(DWC3_DEPCMD_TYPE_BULK) | DWC3_DEPCFG_MAX_PACKET_SIZE(USBMON_RX_MPS) | DWC3_DEPCFG_ACTION_INIT;
	p1 = DWC3_DEPCFG_XFER_IN_PROGRESS_EN | DWC3_DEPCFG_EP_NUMBER(USBMON_RX_EP);
	ret = dep_cmd(m, USBMON_RX_EP, DWC3_DEPCMD_SETEPCONFIG, p0, p1, 0);
	if (ret)
		return ret;
	ret = dep_cmd(m, USBMON_RX_EP, DWC3_DEPCMD_SETTRANSFRESOURCE, DWC3_DEPXFERCFG_NUM_XFER_RES(1), 0, 0);
	if (ret)
		return ret;
	WR(m, DWC3_DALEPENA, RD(m, DWC3_DALEPENA) | DWC3_DALEPENA_EP(USBMON_RX_EP));
	rx_ring_init(m);
	ret = rx_start(m);
	if (ret)
		return ret;
	m->rx_enabled = 1;
	m->rx_state = USBMON_RX_IDLE;
	return 0;
}

/* A transfer that was armed and is lost (reset, disconnect, configuration dropped) is an error; the committed offset stays. */
static void rx_disable(struct usbmon *m, int lost)
{
	if (!m->rx_present || !m->rx_enabled)
		return;
	if (m->rx_state == USBMON_RX_ARMED) {
		m->rx_state = USBMON_RX_FAILED;
		m->rx_errors++;
		if (lost)
			m->rx_resets++;
	}
	rx_end(m);
	WR(m, DWC3_DALEPENA, RD(m, DWC3_DALEPENA) & ~DWC3_DALEPENA_EP(USBMON_RX_EP));
	m->rx_enabled = 0;
}

/* End the transfer, then (when its command-complete event arrives) start an empty one again. */
static void rx_restart(struct usbmon *m)
{
	if (m->ep_started[USBMON_RX_EP]) {
		rx_end(m);
		m->rx_restart = 1;
	} else {
		rx_ring_init(m);
		if (rx_start(m))
			m->rx_enabled = 0;
	}
}

static void rx_epcmdcmplt(struct usbmon *m, uint32_t params)
{
	if (((params >> 8) & 0xf) != DWC3_DEPCMD_ENDTRANSFER)
		return;
	m->ep_started[USBMON_RX_EP] = 0;
	m->ep_rsc[USBMON_RX_EP] = 0;
	m->rx_end_pending = 0;
	if (m->rx_restart) {
		m->rx_restart = 0;
		if (m->rx_enabled) {
			rx_ring_init(m);
			if (rx_start(m))
				m->rx_enabled = 0;
		}
	}
}

static int rx_mode_ok(const struct usbmon *m, uint32_t mode, int commit);

/* RX_BEGIN: 0 = armed, -1 = refused (the caller stalls EP0). */
static int rx_begin(struct usbmon *m, const uint8_t *q)
{
	uint64_t off = 0, a, t0;
	uint32_t len, flags, i;
	volatile struct dwc3_trb *t;

	for (i = 0; i < 8; i++)
		off |= (uint64_t)q[i] << (8 * i);
	len = (uint32_t)q[8] | ((uint32_t)q[9] << 8) | ((uint32_t)q[10] << 16) | ((uint32_t)q[11] << 24);
	flags = (uint32_t)q[12] | ((uint32_t)q[13] << 8) | ((uint32_t)q[14] << 16) | ((uint32_t)q[15] << 24);

	if (!m->rx_enabled || m->rx_state == USBMON_RX_ARMED || m->rx_end_pending || m->rx_restart ||
	    (flags & ~USBMON_RXB_SUM_MASK) || !rx_mode_ok(m, flags & USBMON_RXB_SUM_MASK, 1)) {
		m->rx_rejects++;
		return -1;
	}
	if (off < m->rx_committed) {
		m->rx_dups++;
		return -1;
	}
	if (off > m->rx_committed) {
		m->rx_gaps++;
		return -1;
	}
	if (!len || (len % USBMON_RX_MPS) || len > rx_chunk_max(m) || len > m->rx_size - off) {
		m->rx_rejects++;
		return -1;
	}
	t0 = usbmon_ticks();
	if (m->rx_direct) {
		/* no dirty line of the destination may be written back over what the controller is about to store */
		usbmon_dest_sync(m->rx_dest + off, len);
		a = usbmon_dest_addr(m->rx_dest + off);
	} else {
		usbmon_dma_sync(m->dma.rxstage, len);
		a = usbmon_dma_addr(m->dma.rxstage);
	}
	/* dwc3_prepare_one_trb() for a non-stream bulk OUT: NORMAL | CSP | IOC, HWO written last */
	t = &m->dma.rxtrb[m->rx_enq];
	usbmon_dma_st32(&t->bpl, (uint32_t)a);
	usbmon_dma_st32(&t->bph, (uint32_t)(a >> 32));
	usbmon_dma_st32(&t->size, DWC3_TRB_SIZE_LENGTH(len));
	usbmon_dma_st32(&t->ctrl, DWC3_TRBCTL_NORMAL | DWC3_TRB_CTRL_CSP | DWC3_TRB_CTRL_IOC | DWC3_TRB_CTRL_HWO);
	usbmon_dma_sync(m->dma.rxtrb, sizeof(m->dma.rxtrb));
	if (dep_cmd(m, USBMON_RX_EP, DWC3_DEPCMD_UPDATETRANSFER | DWC3_DEPCMD_PARAM(m->ep_rsc[USBMON_RX_EP]), 0, 0, 0)) {
		m->rx_rejects++;
		return -1;
	}
	m->rx_armed_off = off;
	m->rx_armed_len = len;
	m->rx_state = USBMON_RX_ARMED;
	m->rx_mode = flags & USBMON_RXB_SUM_MASK;
	m->rx_t_arm0 = t0;
	m->rx_t_arm1 = usbmon_ticks();
	/* dwc3_ep_inc_enq(): the link TRB is skipped */
	m->rx_enq = (uint8_t)((m->rx_enq + 1) % (USBMON_RX_TRBS - 1));
	return 0;
}

/* NAT-130: is checksum mode `mode` usable? A commit (commit != 0) may also use NONE; any mode but PLAIN needs direct mode. */
static int rx_mode_ok(const struct usbmon *m, uint32_t mode, int commit)
{
	if (mode == USBMON_SUM_PLAIN)
		return 1;
	if (!m->rx_direct)
		return 0;
	if (mode == USBMON_SUM_NONE)
		return commit;
	return (USBMON_PORT_SUM_CAPS >> mode) & 1u;
}

/* The checksum of [p, p+n) of the destination in mode 0..2. The range has been synced (clean+invalidate) by the caller. */
static uint64_t rx_sum_mode(const uint8_t *p, size_t n, uint32_t mode)
{
	if (mode == USBMON_SUM_FAST)
		return usbmon_dest_sum_fast(p, n);
	if (mode == USBMON_SUM_CACHED)
		return usbmon_dest_sum_cached(p, n);
	return usbmon_rx_sum(p, n);
}

uint64_t usbmon_rx_sum(const uint8_t *p, size_t n)
{
	uint64_t sum = 0;
	size_t i;

	for (i = 0; i + 8 <= n; i += 8)
		sum = usbmon_rx_sum_step(sum, usbmon_dest_ld64(p + i), i / 8);
	return sum;
}

/* The committed chunk, staged mode: the controller wrote the DMA block; copy it to the destination 4 KiB at a time. */
static uint64_t rx_copy_staged(struct usbmon *m, uint64_t off, uint32_t len)
{
	uint8_t piece[4096];
	uint64_t sum = 0;
	uint32_t done, k, n;

	usbmon_dma_sync(m->dma.rxstage, len);	/* invalidate: the controller wrote these lines behind the CPU */
	for (done = 0; done < len; done += n) {
		n = len - done < sizeof(piece) ? len - done : (uint32_t)sizeof(piece);
		usbmon_dma_read(piece, m->dma.rxstage + done, n);
		mcopy(m->rx_dest + off + done, piece, n);
		for (k = 0; k + 8 <= n; k += 8) {
			uint64_t w = 0;
			unsigned int b;

			for (b = 0; b < 8; b++)
				w |= (uint64_t)piece[k + b] << (8 * b);
			sum = usbmon_rx_sum_step(sum, w, (done + k) / 8);
		}
	}
	return sum;
}

/* dwc3_gadget_endpoint_trbs_complete() for the one TRB in flight */
static void rx_complete(struct usbmon *m, uint32_t evt_status)
{
	volatile struct dwc3_trb *t = &m->dma.rxtrb[m->rx_deq];
	uint32_t ctrl, size, status, residual;
	int ok;

	if (m->rx_state != USBMON_RX_ARMED) {
		m->rx_spurious++;
		/* the controller ended the transfer behind our back (rx_event() has already forgotten it) while nothing was armed:
		 * begin a fresh empty one, or the next RX_BEGIN would UPDATETRANSFER an endpoint with no transfer started */
		if (m->rx_enabled && !m->ep_started[USBMON_RX_EP] && !m->rx_end_pending && !m->rx_restart)
			rx_restart(m);
		return;
	}
	usbmon_dma_sync(m->dma.rxtrb, sizeof(m->dma.rxtrb));
	ctrl = usbmon_dma_ld32(&t->ctrl);
	size = usbmon_dma_ld32(&t->size);
	if (ctrl & DWC3_TRB_CTRL_HWO)
		return;				/* the controller still owns it: not this TRB's completion */
	status = DWC3_TRB_SIZE_TRBSTS(size);
	residual = size & DWC3_TRB_SIZE_MASK;
	m->rx_last_trb_status = status;
	m->rx_last_residual = residual;
	m->rx_last_evt_status = evt_status;
	m->rx_deq = (uint8_t)((m->rx_deq + 1) % (USBMON_RX_TRBS - 1));	/* dwc3_ep_inc_deq() */
	ok = (status == DWC3_TRBSTS_OK) && !residual && !(evt_status & (DEPEVT_STATUS_BUSERR | DEPEVT_STATUS_SHORT));
	if (!ok) {
		m->rx_errors++;
		m->rx_state = USBMON_RX_FAILED;
		rx_restart(m);
		return;
	}
	m->rx_t_done = usbmon_ticks();
	if (m->rx_direct) {
		usbmon_dest_sync(m->rx_dest + m->rx_armed_off, m->rx_armed_len);	/* invalidate before reading */
		if (m->rx_mode == USBMON_SUM_NONE) {
			m->rx_last_sum = 0;
			m->rx_unsummed++;
		} else {
			m->rx_last_sum = rx_sum_mode(m->rx_dest + m->rx_armed_off, m->rx_armed_len, m->rx_mode);
		}
	} else {
		m->rx_last_sum = rx_copy_staged(m, m->rx_armed_off, m->rx_armed_len);
	}
	m->rx_last_off = m->rx_armed_off;
	m->rx_last_len = m->rx_armed_len;
	m->rx_committed = m->rx_armed_off + m->rx_armed_len;
	m->rx_bytes += m->rx_armed_len;
	m->rx_trbs++;
	m->rx_state = USBMON_RX_IDLE;
	/* NAT-130 phase ticks: the gap is the time from the previous commit's end to this chunk's RX_BEGIN */
	m->rx_t_sum1 = usbmon_ticks();
	m->rx_last_mode = m->rx_mode;
	m->rx_tot_arm += m->rx_t_arm1 - m->rx_t_arm0;
	m->rx_tot_wire += m->rx_t_done - m->rx_t_arm1;
	m->rx_tot_sum += m->rx_t_sum1 - m->rx_t_done;
	if (m->rx_timed)
		m->rx_tot_gap += m->rx_t_arm0 - m->rx_prev_sum1;
	m->rx_prev_sum1 = m->rx_t_sum1;
	m->rx_timed++;
}

/* NAT-130 SUM request: 0 = done (result in sreq_*), -1 = refused (the caller stalls EP0). */
static int rx_sum_req(struct usbmon *m, const uint8_t *q)
{
	uint64_t off = 0, t0;
	uint32_t len, mode, i;

	for (i = 0; i < 8; i++)
		off |= (uint64_t)q[i] << (8 * i);
	len = (uint32_t)q[8] | ((uint32_t)q[9] << 8) | ((uint32_t)q[10] << 16) | ((uint32_t)q[11] << 24);
	mode = (uint32_t)q[12] | ((uint32_t)q[13] << 8) | ((uint32_t)q[14] << 16) | ((uint32_t)q[15] << 24);
	if (m->rx_state == USBMON_RX_ARMED || mode > USBMON_SUM_CACHED || !rx_mode_ok(m, mode, 0) || !len ||
	    (len % USBMON_RX_MPS) || len > rx_chunk_max(m) || off > m->rx_committed || len > m->rx_committed - off) {
		m->sreq_status = USBMON_SREQ_REFUSED;
		m->sreq_refused++;
		return -1;
	}
	t0 = usbmon_ticks();
	usbmon_dest_sync(m->rx_dest + off, len);
	m->sreq_sum = rx_sum_mode(m->rx_dest + off, len, mode);
	m->sreq_ticks = usbmon_ticks() - t0;
	m->sreq_off = off;
	m->sreq_len = len;
	m->sreq_mode = mode;
	m->sreq_count++;
	m->sreq_status = USBMON_SREQ_OK;
	return 0;
}

static void rx_event(struct usbmon *m, uint32_t e)
{
	switch (DWC3_EVT_EP_EVENT(e)) {
	case DWC3_DEPEVT_XFERINPROGRESS:
	case DWC3_DEPEVT_XFERCOMPLETE:
		if (DWC3_EVT_EP_EVENT(e) == DWC3_DEPEVT_XFERCOMPLETE) {
			/* dwc3_gadget_endpoint_transfer_complete(): the controller ended the transfer */
			m->ep_started[USBMON_RX_EP] = 0;
			m->ep_rsc[USBMON_RX_EP] = 0;
		}
		if (m->rx_enabled)
			rx_complete(m, DWC3_EVT_EP_STATUS(e));
		break;
	case DWC3_DEPEVT_EPCMDCMPLT:
		rx_epcmdcmplt(m, DWC3_EVT_EP_PARAMS(e));
		break;
	default:
		break;
	}
}

static void rx_abort(struct usbmon *m)
{
	if (m->rx_state != USBMON_RX_ARMED)
		return;
	m->rx_state = USBMON_RX_IDLE;
	m->rx_aborts++;
	rx_restart(m);
}

static void fill_rxt(const struct usbmon *m, struct usbmon_rxt *r)
{
	uint32_t mode;

	mzero(r, sizeof(*r));
	r->magic[0] = 'S'; r->magic[1] = '2'; r->magic[2] = '4'; r->magic[3] = 'T';
	r->version = 1;
	r->size = sizeof(*r);
	r->now = usbmon_ticks();
	r->freq = usbmon_freq();
	for (mode = 0; mode <= USBMON_SUM_NONE; mode++)
		if (rx_mode_ok(m, mode, 1))
			r->caps |= 1u << mode;
	r->last_mode = m->rx_last_mode;
	r->t_arm0 = m->rx_t_arm0;
	r->t_arm1 = m->rx_t_arm1;
	r->t_done = m->rx_t_done;
	r->t_sum1 = m->rx_t_sum1;
	r->tot_arm = m->rx_tot_arm;
	r->tot_wire = m->rx_tot_wire;
	r->tot_sum = m->rx_tot_sum;
	r->tot_gap = m->rx_tot_gap;
	r->chunks = m->rx_timed;
	r->unsummed = m->rx_unsummed;
	r->sreq_off = m->sreq_off;
	r->sreq_len = m->sreq_len;
	r->sreq_mode = m->sreq_mode;
	r->sreq_sum = m->sreq_sum;
	r->sreq_ticks = m->sreq_ticks;
	r->sreq_count = m->sreq_count;
	r->sreq_status = m->sreq_status;
	r->sreq_refused = m->sreq_refused;
	r->sum_fallbacks = usbmon_port_sum_fallbacks();
}

static void fill_rx(const struct usbmon *m, struct usbmon_rx *r)
{
	mzero(r, sizeof(*r));
	r->magic[0] = 'S'; r->magic[1] = '2'; r->magic[2] = '4'; r->magic[3] = 'R';
	r->version = 1;
	r->size = sizeof(*r);
	r->state = m->rx_state;
	r->flags = (m->rx_present ? USBMON_RXF_PRESENT : 0) | (m->rx_enabled ? USBMON_RXF_ENABLED : 0) |
		   (m->rx_direct ? USBMON_RXF_DIRECT : 0);
	r->committed = m->rx_committed;
	r->armed_off = m->rx_armed_off;
	r->armed_len = m->rx_armed_len;
	r->chunk_max = rx_chunk_max(m);
	r->capacity = m->rx_size;
	r->rx_bytes = m->rx_bytes;
	r->rx_trbs = m->rx_trbs;
	r->rx_errors = m->rx_errors;
	r->rx_dups = m->rx_dups;
	r->rx_gaps = m->rx_gaps;
	r->rx_rejects = m->rx_rejects;
	r->rx_resets = m->rx_resets;
	r->rx_aborts = m->rx_aborts;
	r->last_trb_status = m->rx_last_trb_status;
	r->last_residual = m->rx_last_residual;
	r->last_evt_status = m->rx_last_evt_status;
	r->last_len = m->rx_last_len;
	r->last_off = m->rx_last_off;
	r->last_sum = m->rx_last_sum;
}

/* ---------------------------------------------------------------- descriptors and requests */

static const uint8_t dev_desc[18] = {
	18, 1, 0x00, 0x02, 0xff, 0x00, 0x00, 64,
	USBMON_VID & 0xff, USBMON_VID >> 8, USBMON_PID & 0xff, USBMON_PID >> 8,
	0x00, 0x01, 0, 0, 0, 1,
};

static const uint8_t cfg_desc[18] = {
	9, 2, 18, 0, 1, 1, 0, 0xc0, 0,		/* one interface, self powered, 0 mA */
	9, 4, 0, 0, 0, 0xff, 0, 0, 0,		/* interface 0, alternate 0, no endpoints, vendor class */
};

/* NAT-076: the same configuration plus one bulk-OUT endpoint (0x01, 512 bytes, no interval) */
static const uint8_t cfg_desc_rx[25] = {
	9, 2, 25, 0, 1, 1, 0, 0xc0, 0,
	9, 4, 0, 0, 1, 0xff, 0, 0, 0,		/* interface 0, alternate 0, one endpoint, vendor class */
	7, 5, 0x01, 0x02, 0x00, 0x02, 0,	/* endpoint 1 OUT, bulk, wMaxPacketSize 512, bInterval 0 */
};

static const uint8_t qual_desc[10] = { 10, 6, 0x00, 0x02, 0xff, 0x00, 0x00, 64, 1, 0 };

struct ctrl_req {
	uint8_t type, req;
	uint16_t value, index, length;
};

struct reply {
	const uint8_t *src;	/* ordinary memory */
	uint32_t len;
};

static void fill_info(struct usbmon *m, struct usbmon_info *i)
{
	mzero(i, sizeof(*i));
	i->magic[0] = 'S'; i->magic[1] = '2'; i->magic[2] = '4'; i->magic[3] = 'L';
	i->version = USBMON_PROTO_VERSION;
	i->size = sizeof(*i);
	i->flags = m->flags;
	i->stage = m->stage;
	mcopy(i->boot_id, m->boot_id, sizeof(i->boot_id));
	mcopy(i->nonce, m->nonce, sizeof(i->nonce));
	i->ring_size = m->ring_size;
	i->next_seq = m->seq;
	i->written = m->written;
	i->oldest = m->oldest;
	i->dropped = m->dropped;
	i->setups = m->setups;
	i->stalls = m->stalls;
	i->faults = m->faults;
	i->ticks = usbmon_ticks();
	i->last_err = m->last_err;
	i->last_depcmd = m->last_depcmd;
	i->events = m->events;
	i->resets = m->resets;
}

static void fill_exc(struct usbmon *m, struct usbmon_exc *e)
{
	mcopy(e, &m->exc, sizeof(*e));
	e->magic[0] = 'S'; e->magic[1] = '2'; e->magic[2] = '4'; e->magic[3] = 'X';
	e->version = USBMON_PROTO_VERSION;
	e->size = sizeof(*e);
	mcopy(e->boot_id, m->boot_id, sizeof(e->boot_id));
}

/* NAT-134: the read-only probe table (docs/procedures/nat-134/peek134.py TABLE, same order; test_nat134 compares). PEEK reads
 * exactly one of these per request; nothing else can be peeked and nothing is ever written through it. */
static const uint32_t peek_addr[] = {
	0x1286061cu,	/*  0 pmu: PMU USB2 PHY isolation (+0x61c) */
	0x12860620u,	/*  1 pmu: PMU USBDP PHY isolation (+0x620) */
	0x1790c120u,	/*  2 dwc3: GSNPSID */
	0x1790c1a0u,	/*  3 dwc3: VER_NUMBER */
	0x1790c1a4u,	/*  4 dwc3: VER_TYPE */
	0x1790c14cu,	/*  5 dwc3: GHWPARAMS3 */
	0x1790c2c0u,	/*  6 dwc3: GUSB3PIPECTL0 */
	0x1790c12cu,	/*  7 dwc3: GUCTL */
	0x1790c11cu,	/*  8 dwc3: GUCTL1 */
	0x1790d020u,	/*  9 dwc3: LSKIPFREQ */
	0x1790d024u,	/* 10 dwc3: LLUCTL0 */
	0x1790d060u,	/* 11 dwc3: LCSR_TX_DEEMPH */
	0x1790d064u,	/* 12 dwc3: LCSR_TX_DEEMPH_1 */
	0x1790d068u,	/* 13 dwc3: LCSR_TX_DEEMPH_2 */
	0x1790d06cu,	/* 14 dwc3: LCSR_TX_DEEMPH_3 */
	0x1790d800u,	/* 15 dwc3: BU31RHBDBG */
	0x1790c700u,	/* 16 dwc3: DCFG */
	0x1790c70cu,	/* 17 dwc3: DSTS */
	0x178a0000u,	/* 18 usbcon: USBCON VERSION */
	0x178a0004u,	/* 19 usbcon: LINKCTRL */
	0x178a000cu,	/* 20 usbcon: LINK_CLKRST */
	0x178a0014u,	/* 21 usbcon: USBCON +0x14 */
	0x178a0080u,	/* 22 usbcon: LTSTATE_HIS */
	0x178a0114u,	/* 23 usbcon: HSP_MISC */
	0x17802054u,	/* 24 cmu_hsi0: GAT EUSB_CTRL_PCLK */
	0x17802058u,	/* 25 cmu_hsi0: GAT USBDPPHY_CTRL_PCLK */
	0x1780205cu,	/* 26 cmu_hsi0: GAT USBDPPHY_TCA_APB_CLK */
	0x17802060u,	/* 27 cmu_hsi0: GAT USBLINK_ACLK */
	0x17802064u,	/* 28 cmu_hsi0: GAT USBSUBCTL_APB_PCLK */
	0x17803054u,	/* 29 cmu_hsi0: QCH USB32DRD S_CTRL */
	0x17803058u,	/* 30 cmu_hsi0: QCH USB32DRD S_EUSBCTL */
	0x1780305cu,	/* 31 cmu_hsi0: QCH USB32DRD S_LINK */
	0x17803060u,	/* 32 cmu_hsi0: QCH USB32DRD S_SUBCTRL */
	0x17803064u,	/* 33 cmu_hsi0: QCH USB32DRD S_TCA */
	0x17807064u,	/* 34 cmu_hsi0: DBG_NFO QCH S_TCA */
	0x178d0000u,	/* 35 usbdp: RST_CTRL */
	0x178d0004u,	/* 36 usbdp: CR_PARA_CON0 */
	0x178d0008u,	/* 37 usbdp: CR_PARA_CON1 */
	0x178d000cu,	/* 38 usbdp: CR_PARA_CON2 */
	0x178d0100u,	/* 39 usbdp: PHY_CONFIG0 */
	0x178d0108u,	/* 40 usbdp: PHY_CONFIG2 */
	0x178d0110u,	/* 41 usbdp: PHY_SRAM_CON */
	0x178d016cu,	/* 42 usbdp: TCA_CONFIG */
	0x178d0234u,	/* 43 usbdp: DP_CONFIG12 */
	0x178d0238u,	/* 44 usbdp: DP_CONFIG13 */
	0x178e0000u,	/* 45 tca: TCA +0x00 */
	0x178e0004u,	/* 46 tca: TCA +0x04 */
	0x178e0008u,	/* 47 tca: TCA +0x08 */
	0x178e000cu,	/* 48 tca: TCA +0x0c */
	0x178e0010u,	/* 49 tca: TCA +0x10 */
	0x178e0014u,	/* 50 tca: TCA +0x14 */
	0x178e0018u,	/* 51 tca: TCA +0x18 */
	0x178e001cu,	/* 52 tca: TCA +0x1c */
	0x178e0020u,	/* 53 tca: TCA +0x20 */
	0x178e0024u,	/* 54 tca: TCA +0x24 */
	0x178e0028u,	/* 55 tca: TCA +0x28 */
	0x178e002cu,	/* 56 tca: TCA +0x2c */
	0x178e0030u,	/* 57 tca: TCA +0x30 */
	0x178e0034u,	/* 58 tca: TCA +0x34 */
	0x178e00fcu,	/* 59 tca: TCA INFO */
	0x11802054u,	/* 60 cmu_peric2: GAT GPIO_PERIC2_PCLK */
	0x11803040u,	/* 61 cmu_peric2: QCH GPIO_PERIC2 */
	0x118301a0u,	/* 62 gpio: GPC7 CON */
	0x118301a4u,	/* 63 gpio: GPC7 DAT */
};
#define PEEK_COUNT ((uint16_t)(sizeof(peek_addr) / sizeof(peek_addr[0])))

/* The reply is built in ordinary memory first, then copied into the DMA block and synced. Returns the number of bytes the
 * request produces, or a negative value for "stall". */
static int build_reply(struct usbmon *m, const struct ctrl_req *c, uint8_t *buf, uint32_t cap)
{
	uint32_t n = 0, want = c->length;
	uint64_t off, start, end;

	if (!(c->type & 0x80))
		return -1;
	switch (c->type & 0x7f) {
	case 0x00:	/* standard, device */
		if (c->req == 6) {	/* GET_DESCRIPTOR */
			const uint8_t *d = 0;

			switch (c->value >> 8) {
			case 1: d = dev_desc; n = sizeof(dev_desc); break;
			case 2:
				if (m->rx_present) { d = cfg_desc_rx; n = sizeof(cfg_desc_rx); }
				else { d = cfg_desc; n = sizeof(cfg_desc); }
				break;
			case 6: d = qual_desc; n = sizeof(qual_desc); break;
			default: return -1;
			}
			if ((c->value & 0xff) != 0 || c->index != 0)
				return -1;
			mcopy(buf, d, n);
		} else if (c->req == 0) {	/* GET_STATUS: self powered */
			if (c->value != 0 || c->index != 0 || want != 2)
				return -1;
			buf[0] = 1; buf[1] = 0; n = 2;
		} else if (c->req == 8) {	/* GET_CONFIGURATION */
			if (c->value != 0 || c->index != 0 || want != 1)
				return -1;
			buf[0] = m->configured; n = 1;
		} else {
			return -1;
		}
		break;
	case 0x01:	/* standard, interface */
		if (c->req == 10 && c->index == 0 && c->value == 0 && want == 1 && m->configured) {	/* GET_INTERFACE */
			buf[0] = 0; n = 1;
		} else if (c->req == 0 && c->value == 0 && c->index == 0 && want == 2) {		/* GET_STATUS */
			buf[0] = 0; buf[1] = 0; n = 2;
		} else {
			return -1;
		}
		break;
	case 0x02:	/* standard, endpoint 0, and (NAT-076) endpoint 0x01 OUT when the bulk endpoint exists */
		if (c->req == 0 && c->value == 0 && want == 2 &&
		    ((c->index & 0x7f) == 0 || (m->rx_present && m->rx_enabled && c->index == 0x01))) {
			buf[0] = 0; buf[1] = 0; n = 2;
		} else {
			return -1;
		}
		break;
	case 0x40:	/* vendor, device */
		switch (c->req) {
		case USBMON_REQ_GET_INFO: {
			struct usbmon_info i;

			if (c->value || c->index || !want)
				return -1;
			fill_info(m, &i);
			mcopy(buf, &i, sizeof(i));
			n = sizeof(i);
			break;
		}
		case USBMON_REQ_GET_EXC: {
			struct usbmon_exc e;

			if (c->value || c->index || !want)
				return -1;
			fill_exc(m, &e);
			mcopy(buf, &e, sizeof(e));
			n = sizeof(e);
			break;
		}
		case USBMON_REQ_GET_RX: {
			struct usbmon_rx r;

			if (!m->rx_present || c->value || c->index || !want)
				return -1;
			fill_rx(m, &r);
			mcopy(buf, &r, sizeof(r));
			n = sizeof(r);
			break;
		}
		case USBMON_REQ_PEEK: {
			struct usbmon_peek p;

			if (c->index != USBMON_PEEK_KEY || c->value >= PEEK_COUNT || want < sizeof(p))
				return -1;
			mcopy(p.magic, USBMON_PEEK_MAGIC, 4);
			p.index = c->value;
			p.count = PEEK_COUNT;
			p.addr = peek_addr[c->value];
			p.value = usbmon_peek32((uintptr_t)peek_addr[c->value]);
			mcopy(buf, &p, sizeof(p));
			n = sizeof(p);
			break;
		}
		case USBMON_REQ_GET_RXT: {
			struct usbmon_rxt r;

			if (!m->rx_present || c->value || c->index || !want)
				return -1;
			fill_rxt(m, &r);
			mcopy(buf, &r, sizeof(r));
			n = sizeof(r);
			break;
		}
		case USBMON_REQ_READ_RING: {
			struct usbmon_ring_reply rr;
			uint32_t room;

			if (want < sizeof(rr) || want > USBMON_READ_MAX)
				return -1;
			off = ((uint64_t)c->index << 16) | c->value;
			/* offsets are 32 bit on the wire; extend to the stream position nearest the current end */
			start = (m->written & ~0xffffffffULL) | off;
			if (start > m->written)
				start -= 0x100000000ULL;
			end = m->written;
			if (start < m->oldest)
				start = m->oldest;
			if (start > end)
				start = end;
			room = want - (uint32_t)sizeof(rr);
			if (end - start > room)
				end = start + room;
			rr.start = (uint32_t)start;
			rr.end = (uint32_t)m->written;
			mcopy(buf, &rr, sizeof(rr));
			ring_load(m, start, buf + sizeof(rr), (size_t)(end - start));
			n = (uint32_t)(sizeof(rr) + (end - start));
			break;
		}
		default:
			return -1;
		}
		break;
	default:
		return -1;
	}
	(void)cap;
	return (int)n;
}

/* Control-IN data stage: one TRB, plus a zero-length TRB when the reply ends on a packet boundary but is shorter than
 * what the host asked for (dwc3 __dwc3_ep0_do_control_data(): the `zero` case). */
static void ep0_start_data_in(struct usbmon *m, uint32_t len, uint32_t want)
{
	uint64_t a = usbmon_dma_addr(m->dma.reply);
	int zlp = (len && !(len % m->mps) && len < want);

	usbmon_dma_sync(m->dma.reply, (len + 63u) & ~63u);
	trb_write(m, 0, a, len, DWC3_TRBCTL_CONTROL_DATA, zlp);
	if (zlp)
		trb_write(m, 1, a, 0, DWC3_TRBCTL_CONTROL_DATA, 0);
	m->ep0state = EP0_DATA_PHASE;
	if (ep0_start_trans(m, 1, zlp ? 2 : 1))
		ep0_stall_and_restart(m);
	else
		m->ep0_next = EP0_NEXT_COMPLETE;
}

/* A control-OUT data stage always asks for a whole packet (dwc3_ep0_set_sel(): "this controller can't handle
 * non-wMaxPacketSize aligned transfers on the OUT direction"). */
static void ep0_start_data_out(struct usbmon *m, uint16_t want)
{
	usbmon_dma_sync(m->dma.out, USBMON_OUT_BUF);
	trb_write(m, 0, usbmon_dma_addr(m->dma.out), m->mps, DWC3_TRBCTL_CONTROL_DATA, 0);
	m->ep0state = EP0_DATA_PHASE;
	m->out_pending = 1;
	m->out_len = want;
	if (ep0_start_trans(m, 0, 1))
		ep0_stall_and_restart(m);
	else
		m->ep0_next = EP0_NEXT_COMPLETE;
}

/* dwc3_ep0_inspect_setup() with the gadget side folded in. */
static void ep0_inspect_setup(struct usbmon *m)
{
	uint8_t s[8];
	struct ctrl_req c;
	int n;

	usbmon_dma_sync(m->dma.setup, 64);
	usbmon_dma_read(s, m->dma.setup, 8);
	c.type = s[0];
	c.req = s[1];
	c.value = (uint16_t)(s[2] | (s[3] << 8));
	c.index = (uint16_t)(s[4] | (s[5] << 8));
	c.length = (uint16_t)(s[6] | (s[7] << 8));
	m->setups++;

	if (!m->connected)
		goto stall;
	if (!c.length) {
		m->three_stage = 0;
		m->expect_in = 0;
		m->ep0_next = EP0_NEXT_NRDY_STATUS;
	} else {
		m->three_stage = 1;
		m->expect_in = !!(c.type & 0x80);
		m->ep0_next = EP0_NEXT_NRDY_DATA;
	}

	if (!(c.type & 0x80)) {
		/* host-to-device requests */
		switch (c.type & 0x7f) {
		case 0x00:
			if (c.req == 5) {		/* SET_ADDRESS (dwc3_ep0_set_address) */
				if (c.value > 127 || c.index || c.length || m->configured)
					goto stall;
				WR(m, DWC3_DCFG, (RD(m, DWC3_DCFG) & ~DWC3_DCFG_DEVADDR_MASK) | DWC3_DCFG_DEVADDR(c.value));
				m->usb_addr = (uint8_t)c.value;
				return;
			}
			if (c.req == 9) {		/* SET_CONFIGURATION */
				if (c.index || c.length || c.value > 1 || !m->usb_addr)
					goto stall;
				if (c.value) {
					if (rx_enable(m)) {	/* dwc3_ep0_set_config(): a failing function enable fails the request */
						m->last_err = USBMON_E_CMD;
						goto stall;
					}
					m->configured = 1;
					m->flags |= USBMON_F_CONFIGURED;
				} else {
					rx_disable(m, 0);
					m->configured = 0;
					m->flags &= ~USBMON_F_CONFIGURED;
				}
				return;
			}
			goto stall;
		case 0x01:
			if (c.req == 11 && c.value == 0 && c.index == 0 && !c.length && m->configured)	/* SET_INTERFACE alt 0 */
				return;
			goto stall;
		case 0x02:
			/* CLEAR_FEATURE(ENDPOINT_HALT) of the bulk endpoint: it is never halted, so there is nothing to clear */
			if (c.req == 1 && c.value == 0 && c.index == 0x01 && !c.length && m->rx_enabled)
				return;
			goto stall;
		case 0x40:
			if (c.req == USBMON_REQ_SET_NONCE && !c.value && !c.index && c.length == USBMON_NONCE_LEN &&
			    c.length <= m->mps) {
				m->out_kind = 0;
				ep0_start_data_out(m, c.length);
				return;
			}
			if (c.req == USBMON_REQ_RX_BEGIN && !c.value && !c.index && c.length == sizeof(struct usbmon_rx_begin) &&
			    c.length <= m->mps && m->rx_enabled && m->configured) {
				m->out_kind = 1;
				ep0_start_data_out(m, c.length);
				return;
			}
			if (c.req == USBMON_REQ_SUM && !c.value && !c.index && c.length == sizeof(struct usbmon_sum_req) &&
			    c.length <= m->mps && m->rx_present && m->configured) {
				m->out_kind = 2;
				ep0_start_data_out(m, c.length);
				return;
			}
			if (c.req == USBMON_REQ_RX_ABORT && !c.value && !c.index && !c.length && m->rx_enabled && m->configured) {
				rx_abort(m);
				return;
			}
			goto stall;
		default:
			goto stall;
		}
	}

	n = build_reply(m, &c, m->scratch, sizeof(m->scratch));
	if (n < 0 || (uint32_t)n > USBMON_REPLY_BUF)
		goto stall;
	if (!c.length)
		return;
	if ((uint32_t)n > c.length)
		n = c.length;
	usbmon_dma_write(m->dma.reply, m->scratch, (size_t)n);
	ep0_start_data_in(m, (uint32_t)n, c.length);
	return;
stall:
	ep0_stall_and_restart(m);
}

static void ep0_do_control_status(struct usbmon *m, unsigned int ep)
{
	uint32_t type = m->three_stage ? DWC3_TRBCTL_CONTROL_STATUS3 : DWC3_TRBCTL_CONTROL_STATUS2;

	usbmon_dma_sync(m->dma.trb, sizeof(struct dwc3_trb));
	trb_write(m, 0, usbmon_dma_addr(m->dma.trb), 0, type, 0);
	if (ep0_start_trans(m, ep, 1))
		ep0_stall_and_restart(m);
}

/* dwc3_ep0_complete_data() */
static void ep0_complete_data(struct usbmon *m, unsigned int ep)
{
	uint32_t sz, status, remaining;

	m->ep0_next = EP0_NEXT_NRDY_STATUS;
	usbmon_dma_sync(m->dma.trb, sizeof(struct dwc3_trb));
	sz = usbmon_dma_ld32(&m->dma.trb[0].size);
	status = DWC3_TRB_SIZE_TRBSTS(sz);
	if (status == DWC3_TRBSTS_SETUP_PENDING) {
		/* A new SETUP packet is waiting in the controller. The vendor driver notes it and waits for the NRDY(STATUS) that
		 * follows; this engine restarts at once, so it cannot be left waiting for an event that does not come. */
		m->setup_pending = 1;
		m->out_pending = 0;
		ep0_stall_and_restart(m);
		return;
	}
	remaining = sz & DWC3_TRB_SIZE_MASK;
	if (ep == 0 && m->out_pending) {
		uint32_t got = m->mps - remaining;

		m->out_pending = 0;
		if (got != m->out_len) {
			ep0_stall_and_restart(m);
			return;
		}
		usbmon_dma_sync(m->dma.out, USBMON_OUT_BUF);
		if (m->out_kind == 1) {
			uint8_t q[sizeof(struct usbmon_rx_begin)];

			usbmon_dma_read(q, m->dma.out, sizeof(q));
			if (rx_begin(m, q))
				ep0_stall_and_restart(m);
		} else if (m->out_kind == 2) {
			uint8_t q[sizeof(struct usbmon_sum_req)];

			usbmon_dma_read(q, m->dma.out, sizeof(q));
			if (rx_sum_req(m, q))
				ep0_stall_and_restart(m);
		} else {
			usbmon_dma_read(m->nonce, m->dma.out, USBMON_NONCE_LEN);
			m->flags |= USBMON_F_NONCE_SET;
		}
	} else if (ep == 1 && remaining) {
		/* dwc3_ep0_complete_data(): `(epnum & 1) && ur->actual < ur->length` -> stall */
		ep0_stall_and_restart(m);
	}
}

/* dwc3_ep0_complete_status() */
static void ep0_complete_status(struct usbmon *m)
{
	uint32_t sz;

	usbmon_dma_sync(m->dma.trb, sizeof(struct dwc3_trb));
	sz = usbmon_dma_ld32(&m->dma.trb[0].size);
	if (DWC3_TRB_SIZE_TRBSTS(sz) == DWC3_TRBSTS_SETUP_PENDING)
		m->setup_pending = 1;
	m->ep0state = EP0_SETUP_PHASE;
	(void)ep0_out_start(m);
}

/* dwc3_ep0_xfer_complete() */
static void ep0_xfer_complete(struct usbmon *m, unsigned int ep)
{
	m->ep_started[ep] = 0;
	m->ep_rsc[ep] = 0;
	m->setup_pending = 0;
	switch (m->ep0state) {
	case EP0_SETUP_PHASE:
		ep0_inspect_setup(m);
		break;
	case EP0_DATA_PHASE:
		ep0_complete_data(m, ep);
		break;
	case EP0_STATUS_PHASE:
		ep0_complete_status(m);
		break;
	default:
		break;
	}
}

/* dwc3_ep0_xfernotready() */
static void ep0_xfernotready(struct usbmon *m, unsigned int ep, uint32_t status)
{
	switch (status) {
	case DEPEVT_STATUS_CONTROL_DATA:
		if (!m->connected)
			return;
		/* the data stage was started when the SETUP was handled; an NRDY for the other direction is an error */
		if (m->expect_in != ep && m->ep0state == EP0_DATA_PHASE) {
			ep0_end_control_data(m, m->expect_in);
			ep0_stall_and_restart(m);
		}
		break;
	case DEPEVT_STATUS_CONTROL_STATUS:
		if (m->ep0_next != EP0_NEXT_NRDY_STATUS)
			return;
		if (m->setup_pending) {
			ep0_stall_and_restart(m);
			return;
		}
		m->ep0state = EP0_STATUS_PHASE;
		ep0_do_control_status(m, ep);
		break;
	default:
		break;
	}
}

/* ---------------------------------------------------------------- device events */

static void conndone(struct usbmon *m)
{
	uint32_t speed = RD(m, DWC3_DSTS) & DWC3_DSTS_CONNECTSPD;

	m->mps = (speed == DWC3_DSTS_SUPERSPEED) ? 512 : 64;
	m->flags |= USBMON_F_CONNECTED;
	if (ep0_enable(m, 0, DWC3_DEPCFG_ACTION_MODIFY, 0) || ep0_enable(m, 1, DWC3_DEPCFG_ACTION_MODIFY, 0))
		m->last_err = USBMON_E_CMD;
}

static void reset_event(struct usbmon *m)
{
	uint32_t reg;

	m->resets++;
	m->connected = 0;
	rx_disable(m, 1);	/* dwc3_gadget_reset_interrupt(): dwc3_stop_active_transfers() */
	ep0_reset_state(m);
	m->connected = 1;
	reg = RD(m, DWC3_DCTL) & ~DWC3_DCTL_TSTCTRL_MASK;
	WR(m, DWC3_DCTL, reg);
	WR(m, DWC3_DCFG, RD(m, DWC3_DCFG) & ~DWC3_DCFG_DEVADDR_MASK);
	m->usb_addr = 0;
	m->configured = 0;
	m->flags &= ~USBMON_F_CONFIGURED;
}

static void disconnect_event(struct usbmon *m)
{
	rx_disable(m, 1);
	m->connected = 0;
	m->usb_addr = 0;
	m->configured = 0;
	m->flags &= ~(USBMON_F_CONNECTED | USBMON_F_CONFIGURED);
}

static void handle_event(struct usbmon *m, uint32_t e)
{
	m->events++;
	if (!DWC3_EVT_IS_DEVSPEC(e)) {
		unsigned int ep = DWC3_EVT_EP_NUM(e);

		if (ep == USBMON_RX_EP && m->rx_present) {
			rx_event(m, e);
			return;
		}
		if (ep > 1)
			return;
		switch (DWC3_EVT_EP_EVENT(e)) {
		case DWC3_DEPEVT_XFERCOMPLETE:
			ep0_xfer_complete(m, ep);
			break;
		case DWC3_DEPEVT_XFERNOTREADY:
			ep0_xfernotready(m, ep, DWC3_EVT_EP_STATUS(e));
			break;
		case DWC3_DEPEVT_EPCMDCMPLT:
			if (((DWC3_EVT_EP_PARAMS(e) >> 8) & 0xf) == DWC3_DEPCMD_ENDTRANSFER) {
				m->ep_started[ep] = 0;
				m->ep_rsc[ep] = 0;
			}
			break;
		default:
			break;
		}
		return;
	}
	if (DWC3_EVT_DEV_RAWTYPE(e) != 0)
		return;
	switch (DWC3_EVT_DEV_TYPE(e)) {
	case DWC3_DEVICE_EVENT_DISCONNECT:
		disconnect_event(m);
		break;
	case DWC3_DEVICE_EVENT_RESET:
		reset_event(m);
		break;
	case DWC3_DEVICE_EVENT_CONNECT_DONE:
		conndone(m);
		break;
	case DWC3_DEVICE_EVENT_OVERFLOW:
		/* events were lost: forget the control state and wait for the next SETUP */
		m->last_err = USBMON_E_CMD;
		ep0_stall_and_restart(m);
		break;
	default:
		break;
	}
}

void usbmon_poll(struct usbmon *m)
{
	uint32_t count = RD(m, DWC3_GEVNTCOUNT(0)) & DWC3_GEVNTCOUNT_MASK;
	uint32_t evt[USBMON_EVT_BYTES / 4];
	uint32_t i, n, bytes = USBMON_EVT_BYTES;

	if (!count)
		return;
	if (count > bytes)
		count = bytes;
	n = count / 4;
	/* dwc3_check_event_buf(): copy the events out of the buffer, then acknowledge them */
	usbmon_dma_sync(m->dma.events, bytes);
	for (i = 0; i < n; i++) {
		evt[i] = usbmon_dma_ld32(&m->dma.events[m->evt_lpos / 4]);
		m->evt_lpos = (m->evt_lpos + 4) % bytes;
	}
	WR(m, DWC3_GEVNTCOUNT(0), count);
	for (i = 0; i < n; i++)
		handle_event(m, evt[i]);
}

/* ---------------------------------------------------------------- initialisation */

static int soft_reset(struct usbmon *m, uint32_t id)
{
	uint32_t reg = RD(m, DWC3_DCTL);
	unsigned int retries, i;
	int slow = ((id & DWC3_GSNPSID_MASK) == 0x33310000u);	/* DWC_usb31/32: poll 10 x 20 ms (core.c dwc3_core_soft_reset) */

	reg |= DWC3_DCTL_CSFTRST;
	reg &= ~DWC3_DCTL_RUN_STOP;
	WR(m, DWC3_DCTL, reg);
	retries = slow ? 10 : 1000;
	for (i = 0; i < retries; i++) {
		if (!(RD(m, DWC3_DCTL) & DWC3_DCTL_CSFTRST))
			return 0;
		usbmon_delay_us(slow ? 20000 : 1);
	}
	return USBMON_E_RESET;
}

/* dwc3_ref_clk_period(): GUCTL.REFCLKPER and the GFLADJ reference-clock fields from the controller's "ref" clock rate. */
static void ref_clk_period(struct usbmon *m, const struct usbmon_cfg *cfg)
{
	uint32_t rate = cfg->refclk_hz, period, reg, decr;
	uint64_t fladj;

	if (!rate)
		return;
	period = 1000000000u / rate;
	reg = RD(m, DWC3_GUCTL);
	reg &= ~DWC3_GUCTL_REFCLKPER_MASK;
	reg |= period << DWC3_GUCTL_REFCLKPER_SEL;
	WR(m, DWC3_GUCTL, reg);
	/* 125000 * (NSEC_PER_SEC / (rate * period) - 1), rearranged exactly as the vendor does */
	fladj = (125000ULL * 1000000000ULL) / ((uint64_t)rate * period);
	fladj -= 125000;
	decr = 480000000u / rate;
	reg = RD(m, DWC3_GFLADJ);
	reg &= ~(DWC3_GFLADJ_REFCLK_FLADJ_MASK | DWC3_GFLADJ_240MHZDECR | DWC3_GFLADJ_240MHZDECR_PLS1);
	reg |= ((uint32_t)fladj << 8) & DWC3_GFLADJ_REFCLK_FLADJ_MASK;
	reg |= ((decr >> 1) << 24) & DWC3_GFLADJ_240MHZDECR;
	reg |= (decr & 1) ? DWC3_GFLADJ_240MHZDECR_PLS1 : 0;
	if (cfg->gfladj_refclk_lpm_sel)
		reg |= DWC3_GFLADJ_REFCLK_LPM_SEL;
	WR(m, DWC3_GFLADJ, reg);
}

int usbmon_init(struct usbmon *m, const struct usbmon_cfg *cfg)
{
	uint32_t id, reg, ram2, nump, i;
	int ret;

	if (!cfg || !cfg->dwc3_base || !cfg->ring || cfg->ring_size < 2 * (USBMON_REC_HDR + USBMON_REC_MAX))
		return USBMON_E_ARG;
	mzero(m, sizeof(*m));
	usbmon_dma_sync(&m->dma, sizeof(m->dma));	/* the zeroing above may sit in dirty cache lines */
	m->base = cfg->dwc3_base;
	m->ring = cfg->ring;
	m->ring_size = cfg->ring_size;
	mcopy(m->boot_id, cfg->boot_id, sizeof(m->boot_id));
	m->mps = 512;			/* vendor __dwc3_gadget_start(): ep0 starts at 512 and is modified at CONNECTDONE */
	if (cfg->rx_dest) {
		if (!cfg->rx_size || (cfg->rx_size % USBMON_RX_MPS))
			return USBMON_E_CFG;
		m->rx_present = 1;
		m->rx_dest = cfg->rx_dest;
		m->rx_size = cfg->rx_size;
		m->rx_direct = cfg->rx_direct ? 1 : 0;
	}

	/* 5.00: dwc3_core_is_valid() */
	id = RD(m, DWC3_GSNPSID);
	if ((id & DWC3_GSNPSID_MASK) != 0x55330000u && (id & DWC3_GSNPSID_MASK) != 0x33310000u)
		return m->last_err = USBMON_E_ID;
	/* 5.01-5.02: dwc3_hs_phy_setup(): SUSPHY and ENBLSLPM cleared; U2_FREECLK_EXISTS cleared (the DT's
	 * snps,dis-u2-freeclk-exists-quirk). PHYIF/USBTRDTIM stay at their reset values, as hsphy_mode is not set in the DT. */
	reg = RD(m, DWC3_GUSB2PHYCFG(0));
	reg &= ~(DWC3_GUSB2PHYCFG_SUSPHY | DWC3_GUSB2PHYCFG_ENBLSLPM | DWC3_GUSB2PHYCFG_U2_FREECLK_EXISTS);
	WR(m, DWC3_GUSB2PHYCFG(0), reg);
	/* 5.04-5.05 */
	ret = soft_reset(m, id);
	if (ret)
		return m->last_err = ret;
	/* 5.07: dwc3_core_setup_global_control(): scale-down off, U2EXIT_LFPS off */
	reg = RD(m, DWC3_GCTL);
	reg &= ~DWC3_GCTL_SCALEDOWN_MASK;
	reg &= ~DWC3_GCTL_U2EXIT_LFPS;
	/* 5.14-5.15: the glue's GCTL / GSBUSCFG0 settings: clock gating stays as the core's PWROPT chose */
	reg &= ~(3u << 12);
	reg |= DWC3_GCTL_PRTCAPDIR(DWC3_GCTL_PRTCAP_DEVICE);	/* dwc3_set_prtcap(device) */
	WR(m, DWC3_GCTL, reg);
	/* 5.08: dwc3_frame_length_adjustment() */
	if (cfg->fladj) {
		reg = RD(m, DWC3_GFLADJ);
		if ((reg & DWC3_GFLADJ_30MHZ_MASK) != cfg->fladj) {
			reg &= ~DWC3_GFLADJ_30MHZ_MASK;
			reg |= DWC3_GFLADJ_30MHZ_SDBND_SEL | cfg->fladj;
			WR(m, DWC3_GFLADJ, reg);
		}
	}
	/* 5.09 */
	ref_clk_period(m, cfg);
	/* 5.14: Exynos glue: INCR burst enables */
	reg = RD(m, DWC3_GSBUSCFG0);
	reg |= DWC3_GSBUSCFG0_INCRBRSTENA;
	WR(m, DWC3_GSBUSCFG0, reg);

	/* 5.11-5.13: dwc3_event_buffers_setup(); the interrupt stays masked, the engine polls */
	for (i = 0; i < USBMON_EVT_BYTES / 4; i++)
		usbmon_dma_st32(&m->dma.events[i], 0);
	usbmon_dma_sync(m->dma.events, USBMON_EVT_BYTES);
	m->evt_lpos = 0;
	WR(m, DWC3_GEVNTADRLO(0), (uint32_t)usbmon_dma_addr(m->dma.events));
	WR(m, DWC3_GEVNTADRHI(0), (uint32_t)(usbmon_dma_addr(m->dma.events) >> 32));
	WR(m, DWC3_GEVNTSIZ(0), DWC3_GEVNTSIZ_SIZE(USBMON_EVT_BYTES) | DWC3_GEVNTSIZ_INTMASK);
	reg = RD(m, DWC3_GEVNTCOUNT(0));
	WR(m, DWC3_GEVNTCOUNT(0), reg);

	/* 6.01: __dwc3_gadget_start(): NUMP from RAM2 depth, IGNSTRMPP */
	ram2 = DWC3_GHWPARAMS7_RAM2_DEPTH(RD(m, DWC3_GHWPARAMS7));
	nump = ((ram2 * (uint32_t)32 / 8) - 24 - 16) / 1024;	/* MDWIDTH is 32 on the controllers this was written for */
	if (nump > 16)
		nump = 16;
	reg = RD(m, DWC3_DCFG);
	reg &= ~DWC3_DCFG_NUMP_MASK;
	reg |= nump << DWC3_DCFG_NUMP_SHIFT;
	reg |= DWC3_DCFG_IGNSTRMPP;
	/* 6.10: __dwc3_gadget_set_speed(): high speed only */
	reg &= ~DWC3_DCFG_SPEED_MASK;
	reg |= DWC3_DCFG_HIGHSPEED;
	WR(m, DWC3_DCFG, reg);

	/* 6.02-6.05: DEPSTARTCFG (resource index 0) on ep0, then both control endpoints */
	ret = dep_cmd(m, 0, DWC3_DEPCMD_DEPSTARTCFG | DWC3_DEPCMD_PARAM(0), 0, 0, 0);
	if (ret)
		return ret;
	ret = ep0_enable(m, 0, DWC3_DEPCFG_ACTION_INIT, 1);
	if (ret)
		return ret;
	ret = ep0_enable(m, 1, DWC3_DEPCFG_ACTION_INIT, 1);
	if (ret)
		return ret;
	/* 6.07: the SETUP TRB before the device is connected */
	m->ep0state = EP0_SETUP_PHASE;
	ret = ep0_out_start(m);
	if (ret)
		return m->last_err = ret;
	/* 6.09: dwc3_gadget_enable_irq(), as event enables (the interrupt line is masked) */
	WR(m, DWC3_DEVTEN, DWC3_DEVTEN_EVNTOVERFLOWEN | DWC3_DEVTEN_CMDCMPLTEN | DWC3_DEVTEN_ERRTICERREN |
	   DWC3_DEVTEN_WKUPEVTEN | DWC3_DEVTEN_CONNECTDONEEN | DWC3_DEVTEN_USBRSTEN | DWC3_DEVTEN_DISCONNEVTEN);
	/* 6.10-6.11: dwc3_gadget_run_stop(on) */
	reg = RD(m, DWC3_DCTL);
	reg &= ~DWC3_DCTL_KEEP_CONNECT;
	reg |= DWC3_DCTL_RUN_STOP;
	WR(m, DWC3_DCTL, reg);
	for (i = 0; i < 500; i++) {
		if (!(RD(m, DWC3_DSTS) & DWC3_DSTS_DEVCTRLHLT))
			break;
		usbmon_delay_us(1);
	}
	if (RD(m, DWC3_DSTS) & DWC3_DSTS_DEVCTRLHLT)
		return m->last_err = USBMON_E_HALT;
	m->magic_ok = 1;
	return USBMON_OK;
}
