// SPDX-License-Identifier: GPL-2.0-only
// NAT-156: host-only timing of MiniIOMobileFramebuffer's per-frame scaling (references/s24-port c8860dec,
// xnu/hackios/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp: blend(), sample_at(), the column tables of drawLayer() and the
// loops of drawRows()), copied without change of arithmetic, for one full-screen layer 1125x2436 -> panel 1080x2340.
// Not a phone measurement: it ranks the paths (filter=1 bilinear, filter=0 nearest, unscaled memcpy) by work per frame.
//   cc -O2 -o bench bench_scale.c && ./bench INPUT.bgra   (INPUT: 1125*2436*4 bytes; or "flat" / "noise")
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define SW 1125
#define SH 2436
#define PW 1080
#define PH 2340

static inline uint32_t blend(uint32_t a, uint32_t b, uint32_t w)
{
	uint32_t rb = ((a & 0xff00ff) * (256 - w) + (b & 0xff00ff) * w) >> 8 & 0xff00ff;
	uint32_t ga = ((a >> 8 & 0xff00ff) * (256 - w) + (b >> 8 & 0xff00ff) * w) & 0xff00ff00;
	return rb | ga;
}

static inline int64_t sample_at(int64_t i, int64_t in, int64_t out)
{
	int64_t at = ((2 * i + 1) * in - out) * 128 / out;
	return at < 0 ? 0 : at > (in - 1) * 256 ? (in - 1) * 256 : at;
}

static uint32_t column[PW];
static uint16_t weight[PW];
static uint32_t blendrow[SW + 1];

static void draw(const uint32_t *pixels, uint32_t *panel, int filter, int unscaled)
{
	for (int32_t y = 0; y < PH; y++) {
		const uint32_t *from;
		uint32_t *to = panel + (size_t)y * PW;
		if (unscaled) {              /* the unscaled path: one memcpy per row (a surface of the panel's size) */
			memcpy(to, pixels + (size_t)y * SW, (size_t)PW * 4);
			continue;
		}
		if (filter) {
			int64_t at = sample_at(y, SH, PH);
			uint32_t row = (uint32_t)(at >> 8), w = (uint32_t)(at & 255);
			const uint32_t *upper = pixels + (size_t)row * SW;
			if (w == 0 || row + 1 >= SH) {
				from = upper;
			} else {
				const uint32_t *lower = pixels + (size_t)(row + 1) * SW;
				uint32_t first = column[0], last = column[PW - 1] + 1 < SW ? column[PW - 1] + 1 : column[PW - 1];
				for (uint32_t c = first; c <= last; c++) {
					uint32_t a = upper[c], b = lower[c];
					blendrow[c] = a == b ? a : blend(a, b, w);
				}
				from = blendrow;
			}
			for (uint32_t i = 0; i < PW; i++) {
				uint32_t c = column[i], ww = weight[i], a = from[c];
				to[i] = ww == 0 || a == from[c + 1] ? a : blend(a, from[c + 1], ww);
			}
		} else {
			from = pixels + (size_t)((int64_t)y * SH / PH) * SW;
			for (int32_t x = 0; x < PW; x++)
				to[x] = from[column[x]];
		}
	}
}

static double now(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec + t.tv_nsec * 1e-9;
}

int main(int argc, char **argv)
{
	uint32_t *pixels = malloc((size_t)SW * SH * 4 + 64), *panel = malloc((size_t)PW * PH * 4);
	if (!pixels || !panel || argc < 2)
		return 2;
	if (!strcmp(argv[1], "flat")) {
		for (size_t i = 0; i < (size_t)SW * SH; i++) pixels[i] = 0xff202020;
	} else if (!strcmp(argv[1], "noise")) {
		uint32_t s = 1;
		for (size_t i = 0; i < (size_t)SW * SH; i++) { s = s * 1103515245 + 12345; pixels[i] = s; }
	} else if (!strcmp(argv[1], "ui")) {
		/* synthetic, home-screen-like: a vertical gradient (rows differ, neighbours in a row alike) and a 4 x 6 grid of 180 px
		 * "icons" of noise (about 20% of the screen); not a captured frame */
		uint32_t s = 1;
		for (int y = 0; y < SH; y++)
			for (int x = 0; x < SW; x++) {
				uint32_t g = 0x30 + y * 0x60 / SH;
				int ix = (x - 90) % 255, iy = (y - 300) % 340;
				int icon = x >= 90 && y >= 300 && y < 300 + 6 * 340 && ix < 180 && iy < 180 && (x - 90) / 255 < 4;
				s = s * 1103515245 + 12345;
				pixels[(size_t)y * SW + x] = icon ? (s | 0xff000000) : (0xff000000 | g << 16 | g << 8 | (g + 0x20));
			}
	} else {
		FILE *f = fopen(argv[1], "rb");
		if (!f || fread(pixels, 4, (size_t)SW * SH, f) != (size_t)SW * SH)
			return 3;
		fclose(f);
	}
	const char *name[3] = { "filter1-bilinear", "filter0-nearest", "unscaled-memcpy" };
	for (int mode = 0; mode < 3; mode++) {
		int filter = mode == 0, unscaled = mode == 2;
		for (int x = 0; x < PW; x++) {
			if (filter) {
				int64_t at = sample_at(x, SW, PW);
				column[x] = (uint32_t)(at >> 8);
				weight[x] = (uint16_t)(column[x] + 1 < SW ? at & 255 : 0);
			} else {
				column[x] = (uint32_t)((int64_t)x * SW / PW);
				weight[x] = 0;
			}
		}
		double best = 1e9;
		for (int r = 0; r < 15; r++) {
			double t0 = now();
			draw(pixels, panel, filter, unscaled);
			double t = now() - t0;
			best = t < best ? t : best;
		}
		uint64_t sum = 0;
		for (size_t i = 0; i < (size_t)PW * PH; i += 97) sum += panel[i];
		printf("%s %.3f ms (best of 15) check %llu\n", name[mode], best * 1e3, (unsigned long long)sum);
	}
	return 0;
}
