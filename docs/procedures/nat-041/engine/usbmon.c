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
	if (DWC3_DEPCMD_CMD(cmd) == DWC3_DEPCMD_STARTTRANSFER && ep < 2) {
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
			case 2: d = cfg_desc; n = sizeof(cfg_desc); break;
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
	case 0x02:	/* standard, endpoint 0 (the only one) */
		if (c->req == 0 && c->value == 0 && (c->index & 0x7f) == 0 && want == 2) {
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
				m->configured = (uint8_t)c.value;
				if (c.value)
					m->flags |= USBMON_F_CONFIGURED;
				else
					m->flags &= ~USBMON_F_CONFIGURED;
				return;
			}
			goto stall;
		case 0x01:
			if (c.req == 11 && c.value == 0 && c.index == 0 && !c.length && m->configured)	/* SET_INTERFACE alt 0 */
				return;
			goto stall;
		case 0x40:
			if (c.req == USBMON_REQ_SET_NONCE && !c.value && !c.index && c.length == USBMON_NONCE_LEN &&
			    c.length <= m->mps) {
				ep0_start_data_out(m, c.length);
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
		usbmon_dma_read(m->nonce, m->dma.out, USBMON_NONCE_LEN);
		m->flags |= USBMON_F_NONCE_SET;
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
