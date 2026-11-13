/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-113: pixel evidence sent by the loader at the payload kernel's own return (why=2), before the KL log dump and before the
 * loader draws anything on the panel again. Included by glue62_impl.h (same translation unit: n47_* formatters, N62_EMIT,
 * N62_WAIT, NAT062_BURST, struct n62_out). Runs with the MMU and caches off: every read is a physical, aligned, read-only access.
 *
 * Two kinds of TEXT records:
 *   PX ...  the panel memory the display DMA scans (0xfa200000, 1080x2340, stride 4320: the loader's DTB framebuffer and the
 *           kernel's e1s-display line of NAT-111): one summary record (non-zero pixels, FNV-1a of all words) and 234 rows of a
 *           108x234 thumbnail (one pixel of every 10 in each direction, RGB332, two hex digits a pixel).
 *   PR ...  the kernel's screen recording (MiniIOMobileFramebuffer, boot-arg rec_secs): where loader_recording[] says it is, after
 *           range checks against the 4 GiB XNU window; its RWREC003 header and, per frame, its time, non-zero bytes and FNV-1a.
 * Nothing is written. What the panel memory holds is what the DMA reads from RAM; lines still dirty in the kernel's cache are not
 * in it (for the panel or for this report). */
#ifndef NAT113_GLUE113_H
#define NAT113_GLUE113_H

#ifndef N113_R32
#define N113_R32(pa)	(*(volatile const uint32_t *)(uintptr_t)(pa))
#endif
#ifndef N113_TICK
#define N113_TICK()	nat044_tick()	/* the loader's watchdog pet / hard-cap poll (markerlib4.c, same unit) */
#endif

#define NAT113_PANEL_PA		0xfa200000ULL
#define NAT113_PANEL_W		1080u
#define NAT113_PANEL_H		2340u
#define NAT113_PANEL_STRIDE	4320u
#define NAT113_STEP		10u
#define NAT113_REC_VA		0xfffffff007d10a08ULL	/* _loader_recording in kernel.no-storage (NAT-029 symbol reader) */
#define NAT113_RAM_LO		0x8fe400000ULL		/* the XNU window the loader chose in NAT-111 (window_begin, from the DTB) ... */
#define NAT113_RAM_HI		0x9fe400000ULL		/* ... window_end (4 GiB); a recording outside it is refused */
#define NAT113_REC_MAX		((64ULL << 20) + 64u)	/* rec_mb=64 plus the header */
#define NAT113_FRAMES_MAX	96u
#define NAT113_MAGIC0		0x45525752u		/* "RWRE" */
#define NAT113_MAGIC1		0x33303043u		/* "C003" */

static void n113_emit(struct n62_out *q, const char *b, char *p)
{
	N62_EMIT(b, p);
	q->recs++;
	q->sent += (uint32_t)(p - b) + 16u;
	if (q->sent >= NAT062_BURST) {
		N62_WAIT();
		q->sent = 0;
	}
}

static uint64_t n113_r64(uint64_t pa)
{
	return (uint64_t)N113_R32(pa) | ((uint64_t)N113_R32(pa + 4u) << 32);
}

static char *n113_hex2(char *p, uint32_t v)
{
	static const char d[] = "0123456789abcdef";

	*p++ = d[(v >> 4) & 0xfu];
	*p++ = d[v & 0xfu];
	return p;
}

static void n113_panel(struct n62_out *q)
{
	char b[NAT062_REC_MAX];
	char *p;
	uint32_t nz = 0, h = 2166136261u;

	for (uint32_t y = 0; y < NAT113_PANEL_H; y++) {
		uint64_t row = NAT113_PANEL_PA + (uint64_t)y * NAT113_PANEL_STRIDE;

		if ((y & 63u) == 0)
			N113_TICK();
		for (uint32_t x = 0; x < NAT113_PANEL_W; x++) {
			uint32_t v = N113_R32(row + 4u * x);

			nz += (v & 0xffffffu) != 0;
			h = (h ^ v) * 16777619u;
		}
	}
	p = b;
	p = n47_s(p, "PX panel pa=");
	p = n47_x(p, NAT113_PANEL_PA);
	p = n47_s(p, " w=");
	p = n47_d(p, (int32_t)NAT113_PANEL_W);
	p = n47_s(p, " h=");
	p = n47_d(p, (int32_t)NAT113_PANEL_H);
	p = n47_s(p, " stride=");
	p = n47_d(p, (int32_t)NAT113_PANEL_STRIDE);
	p = n47_s(p, " step=");
	p = n47_d(p, (int32_t)NAT113_STEP);
	p = n47_s(p, " nonzero=");
	p = n47_d(p, (int32_t)nz);
	p = n47_s(p, " fnv=");
	p = n47_x(p, h);
	n113_emit(q, b, p);
	for (uint32_t y = NAT113_STEP / 2u; y < NAT113_PANEL_H; y += NAT113_STEP) {
		uint64_t row = NAT113_PANEL_PA + (uint64_t)y * NAT113_PANEL_STRIDE;

		p = b;
		p = n47_s(p, "PX r=");
		p = n47_d(p, (int32_t)(y / NAT113_STEP));
		*p++ = ' ';
		for (uint32_t x = NAT113_STEP / 2u; x < NAT113_PANEL_W; x += NAT113_STEP) {
			uint32_t v = N113_R32(row + 4u * x);	/* B G R A in memory */
			uint32_t r = (v >> 16) & 0xffu, g = (v >> 8) & 0xffu, bl = v & 0xffu;

			p = n113_hex2(p, (r & 0xe0u) | ((g & 0xe0u) >> 3) | (bl >> 6));
		}
		n113_emit(q, b, p);
	}
}

static void n113_recording(uint64_t pa_minus_va, struct n62_out *q)
{
	char b[NAT062_REC_MAX];
	char *p = b;
	uint64_t at = NAT113_REC_VA + pa_minus_va;
	uint64_t rpa = n113_r64(at), rlen = n113_r64(at + 8u);
	uint32_t w, hgt, frames, oldest;
	uint64_t fsize, pix;

	p = n47_s(p, "PR rec pa=");
	p = n47_x(p, rpa);
	p = n47_s(p, " bytes=");
	p = n47_x(p, rlen);
	if (rpa == 0 && rlen == 0) {	/* nothing asked for (rec_secs=0) or no memory; a half-set slot is refused below */
		p = n47_s(p, " none");
		n113_emit(q, b, p);
		return;
	}
	if ((rpa & 3u) || rpa < NAT113_RAM_LO || rlen < 32u || rlen > NAT113_REC_MAX || rpa > NAT113_RAM_HI - rlen) {
		p = n47_s(p, " refused");
		n113_emit(q, b, p);
		return;
	}
	w = N113_R32(rpa + 8u);
	hgt = N113_R32(rpa + 12u);
	frames = N113_R32(rpa + 16u);
	oldest = N113_R32(rpa + 20u);
	pix = (uint64_t)w * hgt * 3u;
	fsize = 8u + pix;
	p = n47_s(p, " w=");
	p = n47_d(p, (int32_t)w);
	p = n47_s(p, " h=");
	p = n47_d(p, (int32_t)hgt);
	p = n47_s(p, " frames=");
	p = n47_d(p, (int32_t)frames);
	p = n47_s(p, " oldest=");
	p = n47_d(p, (int32_t)oldest);
	p = n47_s(p, " began=");
	p = n47_x(p, n113_r64(rpa + 24u));
	if (N113_R32(rpa) != NAT113_MAGIC0 || N113_R32(rpa + 4u) != NAT113_MAGIC1 || w == 0 || hgt == 0 || w > 4096u ||
	    hgt > 4096u || (pix & 3u) || 32u + (uint64_t)frames * fsize > rlen) {
		p = n47_s(p, " bad-header");
		n113_emit(q, b, p);
		return;
	}
	n113_emit(q, b, p);
	for (uint32_t i = 0; i < frames && i < NAT113_FRAMES_MAX; i++) {
		uint64_t f = rpa + 32u + (uint64_t)i * fsize;
		uint32_t nzb = 0, h = 2166136261u;

		N113_TICK();
		for (uint64_t o = 0; o < pix; o += 4u) {
			uint32_t v = N113_R32(f + 8u + o);

			nzb += ((v & 0xffu) != 0) + ((v & 0xff00u) != 0) + ((v & 0xff0000u) != 0) + ((v >> 24) != 0);
			h = (h ^ v) * 16777619u;
		}
		p = b;
		p = n47_s(p, "PR f=");
		p = n47_d(p, (int32_t)i);
		p = n47_s(p, " ns=");
		p = n47_x(p, n113_r64(f));
		p = n47_s(p, " nzb=");
		p = n47_d(p, (int32_t)nzb);
		p = n47_s(p, " of=");
		p = n47_d(p, (int32_t)pix);
		p = n47_s(p, " fnv=");
		p = n47_x(p, h);
		n113_emit(q, b, p);
	}
}

/* Both reports, then an end record with the count; paced like the KL dump. */
static void nat113_pixels(uint64_t pa_minus_va)
{
	char b[64];
	char *p;
	struct n62_out q = { 0, 0, 0 };

	N113_TICK();
	n113_panel(&q);
	n113_recording(pa_minus_va, &q);
	p = b;
	p = n47_s(p, "PX end recs=");
	p = n47_d(p, (int32_t)q.recs);
	N62_EMIT(b, p);
	N62_WAIT();
}
#endif
