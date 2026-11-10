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
