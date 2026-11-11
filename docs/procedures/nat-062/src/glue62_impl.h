/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-062: the code behind glue62.h. Included by markerlib52.c after glue52_impl.h, inside its translation unit (MK_LOADER with
 * MK_XNU_CKPT); the host test includes it with NAT062_HOST defined and supplies N62_UP / N62_EMIT / N62_WAIT / N62_BYTE and the
 * n47_s / n47_x / n47_d formatters (the host test takes those three from markerlib47.c's text). Runs where nat036_ckpt_c runs: the
 * MMU and caches are off, every access is by physical address. The log was cleaned to memory by the kernel's loader_jump before the
 * jump (`dc cvac` of [loader_log, loader_log + len)), and is read here byte by byte (device-type accesses with the MMU off must not be
 * unaligned; bytes are always fine). */
#include "glue62.h"

#if defined(NAT062_HOST) || (MK_LOADER && MK_XNU_CKPT)

#ifndef NAT062_HOST
#define N62_UP()	(g_nat047.up)
#define N62_EMIT(b, e)	n47_text((b), (e))
#define N62_WAIT()	mk_wait_tenths(NAT062_WAIT_TENTHS)
#define N62_BYTE(pa)	(*(volatile const uint8_t *)(uintptr_t)(pa))
#endif

#define NAT062_WAIT_TENTHS	5u	/* polling time after each burst */
#define NAT062_BURST		8192u	/* record bytes (payload + 16 for the header) between two waits; the ring is 32 KiB */
#define NAT062_RAW		96u	/* log bytes per record; escapes at most 4 characters each */
#define NAT062_REC_MAX		448u
/* "KL " + 6 hex digits + " " + 4 * NAT062_RAW must fit the record buffer, and a record must fit the engine's record size (1024). */
_Static_assert(3 + 6 + 1 + 4 * NAT062_RAW <= NAT062_REC_MAX && NAT062_REC_MAX <= 1024, "NAT-062: a log record can overflow its buffer");
_Static_assert(NAT062_LOG_MAX <= 0xffffffULL, "NAT-062: offsets are printed with 6 hex digits");

/* How much of the log each kind of dump sends: the newest bytes first (the deadline reset may cut a dump), then the oldest. */
#define NAT062_HEAD_FINAL	8192u
#define NAT062_TAIL_FINAL	8192u
#define NAT062_HEAD_RETURN	8192u
#define NAT062_TAIL_RETURN	32768u

static int n62_log_ok(uint64_t x0, uint64_t x1, uint64_t pa_minus_va)
{
	return x0 == NAT062_LOG_VA + pa_minus_va && x1 <= NAT062_LOG_MAX;
}

static char *n62_hex6(char *p, uint32_t v)
{
	static const char d[] = "0123456789abcdef";

	for (int i = 20; i >= 0; i -= 4)
		*p++ = d[(v >> i) & 0xfu];
	return p;
}

/* One byte of the log as text: printable ASCII as is, backslash, newline and carriage return as \\ \n \r, anything else as \xHH. */
static char *n62_esc(char *p, uint8_t c)
{
	static const char d[] = "0123456789abcdef";

	if (c == '\\') {
		*p++ = '\\';
		*p++ = '\\';
	} else if (c == '\n') {
		*p++ = '\\';
		*p++ = 'n';
	} else if (c == '\r') {
		*p++ = '\\';
		*p++ = 'r';
	} else if (c >= 0x20 && c < 0x7f) {
		*p++ = (char)c;
	} else {
		*p++ = '\\';
		*p++ = 'x';
		*p++ = d[c >> 4];
		*p++ = d[c & 0xfu];
	}
	return p;
}

struct n62_out {
	uint32_t sent;		/* record bytes since the last wait */
	uint32_t recs, bytes;	/* totals */
};

static void n62_range(struct n62_out *o, uint64_t log_pa, uint32_t from, uint32_t to)
{
	char b[NAT062_REC_MAX];

	for (uint32_t off = from; off < to; off += NAT062_RAW) {
		uint32_t n = to - off < NAT062_RAW ? to - off : NAT062_RAW;
		char *p = b;

		*p++ = 'K';
		*p++ = 'L';
		*p++ = ' ';
		p = n62_hex6(p, off);
		*p++ = ' ';
		for (uint32_t i = 0; i < n; i++)
			p = n62_esc(p, N62_BYTE(log_pa + off + i));
		N62_EMIT(b, p);
		o->recs++;
		o->bytes += n;
		o->sent += (uint32_t)(p - b) + 16u;
		if (o->sent >= NAT062_BURST) {
			N62_WAIT();
			o->sent = 0;
		}
	}
}

void nat062_dump_log(uint64_t x0, uint64_t x1, uint64_t pa_minus_va, uint32_t why)
{
	char b[160];
	char *p = b;
	struct n62_out o = { 0, 0, 0 };
	uint32_t len, hmax, tmax, head, tail;

	if (!N62_UP())
		return;
	p = n47_s(p, "KL ");
	if (!n62_log_ok(x0, x1, pa_minus_va)) {
		p = n47_s(p, "refused why=");
		p = n47_d(p, (int32_t)why);
		p = n47_s(p, " x0=");
		p = n47_x(p, x0);
		p = n47_s(p, " x1=");
		p = n47_x(p, x1);
		N62_EMIT(b, p);
		N62_WAIT();
		return;
	}
	len = (uint32_t)x1;
	hmax = why == NAT062_WHY_FINAL ? NAT062_HEAD_FINAL : NAT062_HEAD_RETURN;
	tmax = why == NAT062_WHY_FINAL ? NAT062_TAIL_FINAL : NAT062_TAIL_RETURN;
	head = len < hmax ? len : hmax;
	tail = len - head < tmax ? len - head : tmax;
	p = n47_s(p, "begin why=");
	p = n47_d(p, (int32_t)why);
	p = n47_s(p, " len=");
	p = n47_d(p, (int32_t)len);
	p = n47_s(p, " head=");
	p = n47_d(p, (int32_t)head);
	p = n47_s(p, " tail=");
	p = n47_d(p, (int32_t)tail);
	p = n47_s(p, " gap=");
	p = n47_d(p, (int32_t)(len - head - tail));
	p = n47_s(p, " x0=");
	p = n47_x(p, x0);
	N62_EMIT(b, p);
	n62_range(&o, x0, len - tail, len);	/* the newest text first */
	n62_range(&o, x0, 0, head);
	p = b;
	p = n47_s(p, "KL end why=");
	p = n47_d(p, (int32_t)why);
	p = n47_s(p, " recs=");
	p = n47_d(p, (int32_t)o.recs);
	p = n47_s(p, " bytes=");
	p = n47_d(p, (int32_t)o.bytes);
	N62_EMIT(b, p);
	N62_WAIT();	/* the end record and what is still in the ring must be read before the kernel runs or the hold starts */
}
#endif
