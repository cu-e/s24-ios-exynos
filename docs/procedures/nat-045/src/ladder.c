// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-045: interpreter of the generated USB bring-up op table (see ladder.h). The sequences are in ladder_regs.h; the
 * only hardware contract is usbmon_port.h (the NAT-041 port): usbmon_rd32 / usbmon_wr32 / usbmon_delay_us.
 *
 * Without -DLAD_WRITING_RUNGS this file contains no store and no delay: lad_exec_write() is not compiled and lad_run()
 * refuses every rung above 2.
 */
#include "usbmon_port.h"
#include "ladder.h"

#ifdef LAD_WRITING_RUNGS
#define LAD_DEFAULT_STOP	LAD_LAST_RUNG
#else
#define LAD_DEFAULT_STOP	2
#endif

void lad_default_cfg(struct lad_cfg *c)
{
	c->stop_after = LAD_DEFAULT_STOP;
	c->allow_pd_poweron = 1;
	c->pd_wait_us = 0;
}

static int lad_fail(struct lad_state *st, unsigned rung, unsigned code, unsigned op)
{
	st->err = (int16_t)LAD_ERR(rung, code);
	st->err_op = (uint16_t)op;
	return st->err;
}

static void lad_rec_add(struct lad_state *st, unsigned op, uint32_t v0, uint32_t v1)
{
	struct lad_rec *r = &st->rec[st->nrec++];

	r->op = (uint16_t)op;
	r->pad = 0;
	r->v0 = v0;
	r->v1 = v1;
}

/* L0: the table is what the rungs rely on. Nothing is read or written. */
int lad_selfcheck(void)
{
	unsigned r, i;

	if (LAD_NOPS == 0 || lad_rung_start[1] != 0 || lad_rung_start[6] != LAD_NOPS)
		return LAD_ERR(0, LAD_E_CFG);
	for (r = 1; r <= 5; r++) {
		if (lad_rung_start[r] > lad_rung_start[r + 1])
			return LAD_ERR(0, LAD_E_CFG);
		for (i = lad_rung_start[r]; i < lad_rung_start[r + 1]; i++) {
			if (lad_ops[i].rung != r)
				return LAD_ERR(0, LAD_E_CFG);
			/* L1, L2 and L4 never write */
			if ((r == 1 || r == 2 || r == 4) && lad_ops[i].kind != LK_RD)
				return LAD_ERR(0, LAD_E_CFG);
		}
	}
	return LAD_OK;
}

/* A read of the table: record it and apply the checks the op asks for. */
static int lad_exec_read(struct lad_state *st, unsigned i)
{
	const struct lad_op *op = &lad_ops[i];
	uint32_t v = usbmon_rd32(op->addr);

	lad_rec_add(st, i, v, 0);
	if ((op->flags & LAD_F_NOTALIVE) && (v == op->val || v == op->val2))
		return lad_fail(st, op->rung, LAD_E_NOTALIVE, i);
	if (op->flags & LAD_F_DWC3ID) {
		uint32_t id = v & LAD_DWC3_ID_MASK;

		if (id != LAD_DWC3_ID_0 && id != LAD_DWC3_ID_1)
			return lad_fail(st, op->rung, LAD_E_NOTALIVE, i);
		st->gsnpsid = v;
	}
	return LAD_OK;
}

/* The op that waits for the domain: its address/mask/value define what "HSI0_STATUS says on" means. */
static unsigned lad_pd_wait_op(void)
{
	unsigned i;

	for (i = 0; i < LAD_NOPS; i++)
		if (lad_ops[i].kind == LK_WAIT && (lad_ops[i].flags & LAD_F_POWERON))
			return i;
	return LAD_NOPS;
}

#ifdef LAD_WRITING_RUNGS
static int lad_exec_write(struct lad_state *st, const struct lad_cfg *cfg, unsigned i, uint32_t *reg, uint32_t *chk)
{
	const struct lad_op *op = &lad_ops[i];
	uint32_t v, rb, want;

	switch (op->kind) {
	case LK_WRP:
		usbmon_wr32(op->addr, op->val);
		rb = usbmon_rd32(op->addr);
		lad_rec_add(st, i, op->val, rb);
		if (rb != op->val)
			return lad_fail(st, op->rung, LAD_E_READBACK, i);
		return LAD_OK;
	case LK_WRM:
		v = usbmon_rd32(op->addr);
		want = (v & ~op->mask) | (op->val & op->mask);
		usbmon_wr32(op->addr, want);
		rb = usbmon_rd32(op->addr);
		lad_rec_add(st, i, v, rb);
		if ((rb ^ want) & op->mask)
			return lad_fail(st, op->rung, LAD_E_READBACK, i);
		return LAD_OK;
	case LK_WAIT: {
		uint32_t limit = cfg->pd_wait_us ? cfg->pd_wait_us : LAD_WAIT_TIMEOUT_US;
		uint32_t t = 0;

		for (;;) {
			v = usbmon_rd32(op->addr);
			if ((v & op->mask) == op->val)
				break;
			t++;
			usbmon_delay_us(1);
			if (t > limit) {
				lad_rec_add(st, i, v, t);
				return lad_fail(st, op->rung, LAD_E_TIMEOUT, i);
			}
		}
		lad_rec_add(st, i, v, t);
		return LAD_OK;
	}
	case LK_LOAD:
		*reg = usbmon_rd32(op->addr);
		*chk = 0;
		lad_rec_add(st, i, *reg, 0);
		return LAD_OK;
	case LK_SET:
		*reg = (*reg & ~op->mask) | op->val;
		*chk |= op->mask;
		return LAD_OK;
	case LK_CONST:
		*reg = op->val;
		*chk = 0xffffffffu;
		return LAD_OK;
	case LK_STORE:
		usbmon_wr32(op->addr, *reg);
		rb = usbmon_rd32(op->addr);
		lad_rec_add(st, i, *reg, rb);
		if ((rb ^ *reg) & *chk) {
			if (op->flags & LAD_F_SOFT) {
				st->soft_mismatch++;
				return LAD_OK;
			}
			return lad_fail(st, op->rung, LAD_E_READBACK, i);
		}
		return LAD_OK;
	case LK_RDLOG:
		lad_rec_add(st, i, usbmon_rd32(op->addr), 0);
		return LAD_OK;
	case LK_DELAY:
		usbmon_delay_us(op->val);
		return LAD_OK;
	default:
		return lad_fail(st, op->rung, LAD_E_CFG, i);
	}
}
#endif /* LAD_WRITING_RUNGS */

static int lad_rung(struct lad_state *st, const struct lad_cfg *cfg, unsigned r)
{
	unsigned i, end = lad_rung_start[r + 1];
	int rc;

#ifndef LAD_WRITING_RUNGS
	(void)cfg;
	if (r >= 3)
		return lad_fail(st, r, LAD_E_DISABLED, LAD_NOPS);
#else
	uint32_t reg = 0, chk = 0;
#endif

	for (i = lad_rung_start[r]; i < end; i++) {
		const struct lad_op *op = &lad_ops[i];

		if (op->kind == LK_RD) {
			rc = lad_exec_read(st, i);
			if (rc)
				return rc;
			if (r == 1) {
				unsigned w = lad_pd_wait_op();

				if (w < LAD_NOPS && op->addr == lad_ops[w].addr)
					st->pd_was_on = (st->rec[st->nrec - 1].v0 & lad_ops[w].mask) == lad_ops[w].val;
			}
			continue;
		}
#ifdef LAD_WRITING_RUNGS
		if (r == 3) {
			if (st->pd_was_on > 1)
				return lad_fail(st, r, LAD_E_STATE, i);
			if (op->flags & (LAD_F_POWERON | LAD_F_CMUINIT)) {
				if (st->pd_was_on)
					continue;	/* the domain is on: read-only */
				if (!cfg->allow_pd_poweron)
					return lad_fail(st, r, LAD_E_STATE, i);
			}
		}
		rc = lad_exec_write(st, cfg, i, &reg, &chk);
		if (rc)
			return rc;
#else
		return lad_fail(st, r, LAD_E_CFG, i);	/* a write op in a rung that is not supposed to write */
#endif
	}
	return LAD_OK;
}

int lad_run(struct lad_state *st, const struct lad_cfg *cfg)
{
	unsigned r;
	int rc;
	volatile char *p = (volatile char *)st;	/* not memset: this file must not need libc (and the compiler must not turn the loop into a call) */
	size_t n;

	for (n = 0; n < sizeof(*st); n++)
		p[n] = 0;
	st->pd_was_on = 0xff;
	st->err_op = LAD_NOPS;
	if (!cfg || cfg->stop_after > LAD_LAST_RUNG)
		return lad_fail(st, 0, LAD_E_CFG, LAD_NOPS);
	rc = lad_selfcheck();
	if (rc)
		return lad_fail(st, 0, LAD_E_CFG, LAD_NOPS);
	for (r = 1; r <= cfg->stop_after; r++) {
		rc = lad_rung(st, cfg, r);
		if (rc)
			return rc;
		st->rung_done = (uint8_t)r;
	}
	return LAD_OK;
}
