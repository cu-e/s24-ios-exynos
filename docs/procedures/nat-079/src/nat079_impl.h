/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-079: the receive phase of the delivery loader (loader-diag-xnu-rx-md1). The loader has laid out the window and filled the kernel;
 * this code takes the NAT-076 bulk-OUT engine from "advertised, nothing behind it" to "receives the root image into the md1 reserve",
 * waits until every byte is committed or the cap passes, and reports what happened. It never writes outside [pa, pa + bytes).
 *
 * Included by markerlib47.c (the loader build) and by the host fixture (tests/fixture79.c). The includer provides:
 *   N79_ENGINE()   struct usbmon *   the engine object (g_nat047.m in the loader)
 *   N79_UP()       int               nonzero while the engine may be polled (g_nat047.up; nat047_fault() clears it)
 *   N79_BARRIER()  statement         full memory barrier (dsb sy on aarch64)
 *   nat044_tick()  the watchdog pet / hard-cap reset, called once per loop round     nat047_poll()  one engine poll
 *   mk_cnt()       free-running counter     mk_freq()  its frequency in Hz
 * and, from usbmon.h, struct usbmon, usbmon_log() and the USBMON_RX_* constants. Nothing else is used, so the host build runs this
 * exact text. */

/* ---- pure helpers: no hardware access; the tests also run their compiled aarch64 code on its own ------------------------------ */

/* The arguments of the receive phase. 0, or NAT079_BAD_ARGS. self_lo/self_hi bound the engine's own memory (the DMA block must not
 * be inside the destination). */
static __attribute__((noinline)) int nat079_check_args(uint64_t win_base, uint64_t mem_end, uint64_t pa, uint64_t bytes,
						       uint64_t self_lo, uint64_t self_hi)
{
	if ((pa | bytes) & (NAT079_PAGE - 1))
		return NAT079_BAD_ARGS;
	if (bytes < (uint64_t)NAT079_PROBES * NAT079_PAGE)
		return NAT079_BAD_ARGS;
	if (pa + bytes < pa || pa < win_base || pa + bytes > mem_end)
		return NAT079_BAD_ARGS;
	if (self_lo < pa + bytes && self_hi > pa)
		return NAT079_BAD_ARGS;
	return 0;
}

/* Address of the first byte of self-test page i: the first page, the last page, then six interior pages spread over the range. */
static __attribute__((noinline)) uint64_t nat079_probe_pa(uint64_t pa, uint64_t bytes, unsigned int i)
{
	uint64_t pages = bytes / NAT079_PAGE;

	if (i == 0)
		return pa;
	if (i == 1)
		return pa + (pages - 1) * NAT079_PAGE;
	return pa + (pages * (i - 1) / (NAT079_PROBES - 1)) * NAT079_PAGE;
}

/* Word k of self-test page i, in pass 0 or its complement in pass 1. salt differs per boot, so stale memory cannot pass by luck. */
static __attribute__((noinline)) uint64_t nat079_word(uint64_t salt, unsigned int i, unsigned int k, unsigned int pass)
{
	uint64_t v = (salt + ((uint64_t)i << 32) + k) * 0x9E3779B97F4A7C15ull;

	v ^= v >> 29;
	return pass ? ~v : v;
}

/* Continue, or why to stop. DONE wins over everything else: the bytes are in. */
static __attribute__((noinline)) int nat079_decide(int up, uint64_t committed, uint64_t total, uint64_t elapsed, uint64_t cap)
{
	if (committed >= total)
		return NAT079_DONE;
	if (!up)
		return NAT079_ENGINE_DOWN;
	if (elapsed >= cap)
		return NAT079_TIMEOUT;
	return NAT079_RUNNING;
}

static char *n79_str(char *p, const char *s)
{
	while (*s)
		*p++ = *s++;
	return p;
}

static char *n79_dec(char *p, uint64_t u)
{
	char t[20];
	unsigned int n = 0;

	do {
		t[n++] = (char)('0' + u % 10u);
		u /= 10u;
	} while (u);
	while (n)
		*p++ = t[--n];
	return p;
}

/* "NAT079 rx MiB=<n> trbs=<n> err=<n> t=<n>s": decimal only, no libc, no table of pointers (the loader has no relocation step).
 * Returns the length: at most 109 for any four 64-bit values (NAT079_LINE_MAX bytes are reserved by the caller). */
static __attribute__((noinline)) unsigned int nat079_fmt(char *b, uint64_t mib, uint64_t trbs, uint64_t errs, uint64_t secs)
{
	char *p = n79_str(b, "NAT079 rx MiB=");

	p = n79_dec(p, mib);
	p = n79_str(p, " trbs=");
	p = n79_dec(p, trbs);
	p = n79_str(p, " err=");
	p = n79_dec(p, errs);
	p = n79_str(p, " t=");
	p = n79_dec(p, secs);
	*p++ = 's';
	return (unsigned int)(p - b);
}

/* ---- hardware side ---------------------------------------------------------------------------------------------------------- */

/* Write, read back and clear a few words of NAT079_PROBES pages of the reserve, twice (a pattern and its complement). 0, or
 * NAT079_SELFTEST with the address of the first word that read back wrong. The CPU path only: nothing here involves the controller. */
static __attribute__((noinline)) int nat079_selftest(uint64_t pa, uint64_t bytes, uint64_t salt, uint64_t *bad_pa)
{
	for (unsigned int i = 0; i < NAT079_PROBES; i++) {
		volatile uint64_t *p = (volatile uint64_t *)(uintptr_t)nat079_probe_pa(pa, bytes, i);

		for (unsigned int pass = 0; pass < 2; pass++) {
			for (unsigned int k = 0; k < NAT079_WORDS; k++)
				p[k] = nat079_word(salt, i, k, pass);
			N79_BARRIER();
			for (unsigned int k = 0; k < NAT079_WORDS; k++) {
				if (p[k] != nat079_word(salt, i, k, pass)) {
					*bad_pa = (uint64_t)(uintptr_t)&p[k];
					return NAT079_SELFTEST;
				}
			}
		}
		for (unsigned int k = 0; k < NAT079_WORDS; k++)
			p[k] = 0;
	}
	N79_BARRIER();
	return 0;
}

static void nat079_finish(struct nat079_result *r, const struct usbmon *m, int status, uint64_t elapsed, uint64_t freq)
{
	r->status = status;
	r->committed = m->rx_committed;
	r->rx_bytes = m->rx_bytes;
	r->trbs = m->rx_trbs;
	r->errors = m->rx_errors;
	r->resets = m->rx_resets;
	r->dups = m->rx_dups;
	r->gaps = m->rx_gaps;
	r->rejects = m->rx_rejects;
	r->aborts = m->rx_aborts;
	r->last_sum = m->rx_last_sum;
	r->elapsed_ticks = elapsed;
	r->freq = freq;
}

/* The phase. win_base/mem_end bound the window, [pa, pa + bytes) is the md1 reserve. Always returns (the hard-cap reset of
 * nat044_tick() does not return, by design). The status is also left in r->status. */
int nat079_receive_root(uint64_t win_base, uint64_t mem_end, uint64_t pa, uint64_t bytes, struct nat079_result *r)
{
	struct usbmon *m = N79_ENGINE();
	uint64_t freq = mk_freq(), t0, now, next, cap, every;
	uint64_t self = (uint64_t)(uintptr_t)m;
	int st;

	r->status = NAT079_NO_ENGINE;
	r->pa = pa;
	r->bytes = bytes;
	r->selftest_bad_pa = 0;
	r->committed = r->rx_bytes = r->trbs = r->errors = r->resets = r->dups = r->gaps = r->rejects = r->aborts = r->last_sum = 0;
	r->elapsed_ticks = 0;
	r->freq = freq;
	if (!N79_UP())
		return NAT079_NO_ENGINE;
	if (!m->rx_present)
		return r->status = NAT079_NOT_PRESENT;
	st = nat079_check_args(win_base, mem_end, pa, bytes, self, self + sizeof(*m));
	if (st)
		return r->status = st;
	/* Traffic before the destination was real: those bytes went to the placeholder, the committed offset is not ours. */
	if (m->rx_state == USBMON_RX_ARMED || m->rx_trbs || m->rx_committed || m->rx_bytes) {
		nat079_finish(r, m, NAT079_PREMATURE, 0, freq);
		return r->status;
	}
	st = nat079_selftest(pa, bytes, mk_cnt(), &r->selftest_bad_pa);
	if (st)
		return r->status = st;

	/* From here RX_BEGIN can be accepted (the host sees the capacity change through GET_RX). */
	m->rx_dest = (uint8_t *)(uintptr_t)pa;
	m->rx_size = bytes;

	cap = freq * NAT079_RX_CAP_S;
	every = freq * NAT079_REPORT_S;
	t0 = mk_cnt();
	next = t0 + every;
	for (;;) {
		nat044_tick();
		nat047_poll();
		now = mk_cnt();
		st = nat079_decide(N79_UP(), m->rx_committed, bytes, now - t0, cap);
		if (st != NAT079_RUNNING)
			break;
		if (now >= next) {
			char b[NAT079_LINE_MAX];

			usbmon_log(m, USBMON_K_TEXT, b, (uint16_t)nat079_fmt(b, m->rx_committed >> 20, m->rx_trbs, m->rx_errors, (now - t0) / freq));
			next = now + every;
		}
	}
	if (st == NAT079_DONE && (m->rx_bytes != m->rx_committed || m->rx_committed != bytes))
		st = NAT079_INCONSISTENT;
	nat079_finish(r, m, st, now - t0, freq);
	return st;
}
