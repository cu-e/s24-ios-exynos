/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-only harness: runs the real markerlib.c against a RAM buffer.
 * usage: host_mk SCENARIO MAXDRAWS OUTFILE
 * It prints one "DRAW %08x" per completed draw and dumps the buffer at exit. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "marker.h"
#if defined(MK_XNU_CKPT) && MK_XNU_CKPT
#include "ckpt.h"
#endif
volatile uint64_t *mk_host_fb;
uint64_t mk_host_cnt = 0x1234abcdULL;
static int maxdraws, ndraws;
/* Fake DECON0 register file for the canary-trig scenarios. Any access outside the
 * contract aborts the run and prints BAD*, which the tests treat as failure. */
#if defined(MK_TRIG) && MK_TRIG
int mk_host_mmu_on;
extern volatile uint32_t mk_kick_state;
static uint32_t fake_gc, fake_tc, fake_shd, fake_fc;
uint32_t mk_host_rd(uint32_t off)
{
	uint32_t v;
	switch (off) {
	case 0x04: v = fake_fc; break;
	case 0x20: v = fake_gc; break;
	case 0x30: v = fake_tc; break;
	case 0x50: v = fake_shd; break;
	default: printf("BADRD %x\n", off); exit(5);
	}
	printf("RD %x %08x\n", off, v);
	return v;
}
void mk_host_wr(uint32_t off, uint32_t v)
{
	if (off != 0x30 && off != 0x50) { printf("BADWR %x\n", off); exit(5); }
	printf("WR %x %08x\n", off, v);
	if (off == 0x30) fake_tc = v;
	else { fake_shd = v; fake_fc++; }
}
#endif
static const char *outfile;
void mk_host_drawn(uint32_t frame)
{
	printf("DRAW %08x\n", frame);
	if (++ndraws >= maxdraws) {
		FILE *f = fopen(outfile, "wb");
		fwrite((const void *)mk_host_fb, 1, MK_BANDS * MK_BAND_BYTES, f);
		fclose(f);
		exit(0);
	}
}
int main(int argc, char **argv)
{
	if (argc == 5 && !strcmp(argv[1], "fbsafe")) {
		/* fbsafe IMG_START IMG_END DTBSIZE: DTB lives in a heap buffer (magic d00dfeed). */
		static uint8_t dtb[64] __attribute__((aligned(8))) = {0xd0, 0x0d, 0xfe, 0xed};
		uint32_t sz = (uint32_t)strtoul(argv[4], 0, 0);
		dtb[4] = sz >> 24; dtb[5] = sz >> 16; dtb[6] = sz >> 8; dtb[7] = sz;
		printf("%d\n", mk_fb_safe(strtoull(argv[2], 0, 0), strtoull(argv[3], 0, 0), (uint64_t)(uintptr_t)dtb));
		return 0;
	}
#if defined(MK_TRIG) && MK_TRIG
	if (argc >= 6 && !strcmp(argv[1], "trig")) {
		/* trig MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON [mmu] [poison] */
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		for (int i = 6; i < argc; i++) {
			if (!strcmp(argv[i], "mmu")) mk_host_mmu_on = 1;
			if (!strcmp(argv[i], "poison")) mk_kick_state = 1;
		}
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		mk_canary_loop(4, 0x30d00800, 0x30d00800, 1, 0);
		return 4;
	}
	if (argc >= 6 && !strcmp(argv[1], "trigexc")) {
		/* trigexc MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON [mmu] [poison]: the exception loop of a
		 * canary-trig-fault image (what BRK #0x1234 reaches), against the fake DECON0. */
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		for (int i = 6; i < argc; i++) {
			if (!strcmp(argv[i], "mmu")) mk_host_mmu_on = 1;
			if (!strcmp(argv[i], "poison")) mk_kick_state = 1;
		}
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		mk_exception_loop(4, 0xf2001234ULL, 0xffffff8000123456ULL, 0x00000000deadbeefULL);
		return 4;
	}
#endif
#if defined(MK_LOADER) && MK_LOADER
	if (argc >= 6 && !strcmp(argv[1], "ldstages")) {
		/* ldstages MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON [mmu] [poison]: what the loader calls in order
		 * (ENTRY frame, then the stage markers), then mk_hold(PRE_JUMP) with the fake DECON0. */
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		for (int i = 6; i < argc; i++) {
			if (!strcmp(argv[i], "mmu")) mk_host_mmu_on = 1;
			if (!strcmp(argv[i], "poison")) mk_kick_state = 1;
		}
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		mk_entry_frame(8, 0x30d00800, 0x30d00800);
		mk_stage(MK_ST_LOADER_MAIN); mk_stage(MK_ST_LOADER_FB); mk_stage(MK_ST_LOADER_MEM);
		mk_stage(MK_ST_LOADER_ZERO); mk_stage(MK_ST_LOADER_COPY); mk_stage(MK_ST_LOADER_ADT);
		mk_stage(MK_ST_LOADER_CLEAN); mk_stage(MK_ST_PRE_JUMP);
		mk_hold(MK_ST_PRE_JUMP, 0);
	}
	if (argc >= 7 && !strcmp(argv[1], "ldfail")) {
		/* ldfail MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON MESSAGE: stages up to ZERO, then the fail() hold. */
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		mk_entry_frame(8, 0x30d00800, 0x30d00800);
		mk_stage(MK_ST_LOADER_MAIN); mk_stage(MK_ST_LOADER_FB); mk_stage(MK_ST_LOADER_MEM);
		mk_stage(MK_ST_LOADER_ZERO);
		mk_hold(MK_ST_LOADER_FAIL, mk_hash16(argv[6]));
	}
#if defined(MK_XNU_ENTRY) && MK_XNU_ENTRY
	if (argc >= 6 && !strcmp(argv[1], "xnuentry")) {
		/* xnuentry MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON [full]: only what the stub's marker routine draws
		 * (mk_xnu_report with fixed register values), or, with "full", after the loader's stage markers. */
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		if (argc >= 7 && !strcmp(argv[6], "full")) {
			mk_entry_frame(8, 0x30d00800, 0x30d00800);
			mk_stage(MK_ST_LOADER_MAIN); mk_stage(MK_ST_LOADER_FB); mk_stage(MK_ST_LOADER_MEM);
			mk_stage(MK_ST_LOADER_ZERO); mk_stage(MK_ST_LOADER_COPY); mk_stage(MK_ST_LOADER_ADT);
			mk_stage(MK_ST_LOADER_CLEAN); mk_stage(MK_ST_PRE_JUMP);
		}
		mk_xnu_report(0x00000009e07b74a8ULL, 0x00000009e0a2fa00ULL, 4, 0x30d00800, 0x30d00800);
	}
#endif
#if defined(MK_XNU_CKPT) && MK_XNU_CKPT
	if (argc >= 7 && !strcmp(argv[1], "ckpt")) {
		/* ckpt MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON SEQ [full]: what the NAT-031 return stub draws for a
		 * sequence of arrivals "x2:x3,x2:x3,...". The real nat031_decide (ckpt.c, NAT031_HOST) decides, per arrival,
		 * whether the stub resumes (mk_ckpt_pass) or holds (mk_ckpt_hold, which never returns); the register
		 * snapshot is the one the NAT-030 model gives at checkpoint 5 (SCTLR with M cleared). With "full" the
		 * loader's stage markers are drawn first. */
		static struct nat031_state st;
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		if (argc >= 8 && !strcmp(argv[7], "full")) {
			mk_entry_frame(8, 0x30d00800, 0x30d00800);
			mk_stage(MK_ST_LOADER_MAIN); mk_stage(MK_ST_LOADER_FB); mk_stage(MK_ST_LOADER_MEM);
			mk_stage(MK_ST_LOADER_ZERO); mk_stage(MK_ST_LOADER_COPY); mk_stage(MK_ST_LOADER_ADT);
			mk_stage(MK_ST_LOADER_CLEAN); mk_stage(MK_ST_PRE_JUMP);
		}
		st.expect = 1;
		for (char *s = argv[6]; *s;) {
			struct nat031_decision d;
			struct mk_ckpt r = {0};
			char *e;
			r.x2 = strtoull(s, &e, 0); s = *e ? e + 1 : e;
			r.x3 = strtoull(s, &e, 0); s = *e ? e + 1 : e;
			r.sctlr = 0x3454593cULL; r.ttbr1 = 0x9e15af000ULL; r.tcr = 0x22a51a251aULL; r.vbar = 0xfffffff007437000ULL;
			r.esr = r.x3; r.elr = 0xfffffff00743e0b0ULL; r.far = 0x00000000deadbeefULL;
			nat031_decide(&st, r.x2, r.x3, &d);
			r.mask = st.mask; r.arrivals = st.arrivals;
			if (d.action == NAT031_RESUME) mk_ckpt_pass(&r); else mk_ckpt_hold(&r);
		}
		return 6;	/* the sequence ended without a hold */
	}
#endif
	if (argc == 3 && !strcmp(argv[1], "hash16")) { printf("%04x\n", mk_hash16(argv[2])); return 0; }
	if (argc >= 6 && !strcmp(argv[1], "ldexc")) {
		/* ldexc MAXDRAWS OUTFILE GLOBAL_CON TRIG_CON: loader exception loop after four stages. */
		maxdraws = atoi(argv[2]); outfile = argv[3];
		fake_gc = (uint32_t)strtoul(argv[4], 0, 0); fake_tc = (uint32_t)strtoul(argv[5], 0, 0);
		mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
		mk_entry_frame(8, 0x30d00800, 0x30d00800);
		mk_stage(MK_ST_LOADER_MAIN); mk_stage(MK_ST_LOADER_FB); mk_stage(MK_ST_LOADER_MEM);
		mk_exception_loop(4, 0x96000045ULL, 0xffffff8000123456ULL, 0x0000000000dead00ULL);
	}
#endif
	if (argc != 4) return 2;
	maxdraws = atoi(argv[2]); outfile = argv[3];
	mk_host_fb = calloc(1, MK_BANDS * MK_BAND_BYTES);
	memset((void *)mk_host_fb, 0x5a, MK_BANDS * MK_BAND_BYTES);
	if (!strcmp(argv[1], "entry")) { mk_entry_frame(4, 0x30d00800, 0x30d00800); return 3; }
	if (!strcmp(argv[1], "entry_mc")) { mk_entry_frame(8, 0x30c51835ULL, 0x30d00800); return 3; }
	if (!strcmp(argv[1], "gate")) mk_gate_halt(MK_ST_GATE_MC, 8, 0x30c51835ULL, 0x30d01805ULL);
	if (!strcmp(argv[1], "stage")) { mk_stage(MK_ST_PRE_JUMP); return 3; }
	if (!strcmp(argv[1], "exc")) mk_exception_loop(4, 0xf2001234ULL, 0xffffff8000123456ULL, 0x00000000deadbeefULL);
	if (!strcmp(argv[1], "canary")) mk_canary_loop(4, 0x30d00800, 0x30d00800, 1, 0);
	return 4;
}
