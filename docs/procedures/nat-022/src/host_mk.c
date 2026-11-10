/* SPDX-License-Identifier: GPL-2.0-only */
/* Host-only harness: runs the real markerlib.c against a RAM buffer.
 * usage: host_mk SCENARIO MAXDRAWS OUTFILE
 * It prints one "DRAW %08x" per completed draw and dumps the buffer at exit. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "marker.h"
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
