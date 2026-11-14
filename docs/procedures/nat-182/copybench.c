// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-182: copy-bandwidth reference on one core for the framebuffer scaling of MiniIOMobileFramebuffer (fb_filter=0).
 * Source: a cached 1125x2436 ARGB picture (malloc). Destinations: a 1080x2340 buffer from /dev/dma_heap/system-uncached (Linux maps
 * it write-combined, Normal non-cacheable, the memory type XNU uses for the panel, VM_WIMG_WCOMB) and a cached one (malloc).
 * Every test is one full frame, repeated; the caches are flushed of the source between repeats by streaming a 48 MiB scratch buffer.
 *   copybench CPU REPEATS
 * Prints one line per test: name, median and minimum ms, MB/s of the bytes the test moves, cpu clock before/after (kHz).
 */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/dma-heap.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

#define SW 1125
#define SH 2436
#define PW 1080
#define PH 2340

static uint32_t *src, *wc, *cached, *scratch;
static uint32_t col[PW], rowmap[PH];
static int cpu;
static volatile uint64_t sink;

static double now_ms(void)
{
	struct timespec t;
	clock_gettime(CLOCK_MONOTONIC, &t);
	return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}

static long khz(void)
{
	char p[96], b[32] = "";
	snprintf(p, sizeof p, "/sys/devices/system/cpu/cpu%d/cpufreq/scaling_cur_freq", cpu);
	FILE *f = fopen(p, "r");
	if (!f)
		return -1;
	if (!fgets(b, sizeof b, f))
		b[0] = 0;
	fclose(f);
	return atol(b);
}

static void evict(void)
{
	uint64_t s = 0;
	for (size_t i = 0; i < (48u << 20) / 4; i += 16)
		s += scratch[i]++;
	sink += s;
}

/* the loop NAT-180 replaced */
static void scale_pixel(uint32_t *dst)
{
	for (int y = 0; y < PH; y++) {
		const uint32_t *from = src + (size_t)rowmap[y] * SW;
		uint32_t *to = dst + (size_t)y * PW;
		for (int x = 0; x < PW; x++)
			to[x] = from[col[x]];
	}
}

/* NAT-180's copyColumnRuns, row by row */
static void scale_runs(uint32_t *dst)
{
	for (int y = 0; y < PH; y++) {
		const uint32_t *from = src + (size_t)rowmap[y] * SW;
		uint32_t *to = dst + (size_t)y * PW;
		int x = 0;
		while (x < PW) {
			int start = x;
			uint32_t first = col[x];
			while (x + 1 < PW && col[x + 1] == col[x] + 1)
				x++;
			x++;
			memcpy(to + start, from + first, (size_t)(x - start) * 4);
		}
	}
}

/* the runs found once (when the column map is made), then per row only the copies */
struct run { uint32_t to, from, n; };
static struct run runs[PW];
static int nruns;

static void make_runs(void)
{
	int x = 0;
	nruns = 0;
	while (x < PW) {
		int start = x;
		while (x + 1 < PW && col[x + 1] == col[x] + 1)
			x++;
		x++;
		runs[nruns++] = (struct run){ (uint32_t)start, col[start], (uint32_t)(x - start) };
	}
}

static void scale_table(uint32_t *dst)
{
	for (int y = 0; y < PH; y++) {
		const uint32_t *from = src + (size_t)rowmap[y] * SW;
		uint32_t *to = dst + (size_t)y * PW;
		for (int r = 0; r < nruns; r++)
			memcpy(to + runs[r].to, from + runs[r].from, (size_t)runs[r].n * 4);
	}
}

static void clean(uint32_t *dst)
{
	for (size_t o = 0; o < (size_t)PW * PH * 4; o += 64)
		__asm__ volatile("dc cvac, %0" ::"r"((char *)dst + o) : "memory");
	__asm__ volatile("dsb sy" ::: "memory");
}

static void t_pixel_wc(void) { scale_pixel(wc); }
static void t_runs_wc(void) { scale_runs(wc); }
static void t_pixel_cached(void) { scale_pixel(cached); }
static void t_runs_cached(void) { scale_runs(cached); }
static void t_runs_cached_clean(void) { scale_runs(cached); clean(cached); }
static void t_table_wc(void) { scale_table(wc); }
static void t_table_cached(void) { scale_table(cached); }
static void t_memset_wc(void) { memset(wc, 0x5a, (size_t)PW * PH * 4); }
static void t_memset_cached(void) { memset(cached, 0x5a, (size_t)PW * PH * 4); }
static void t_read_src(void)
{
	const uint64_t *p = (const uint64_t *)src;
	uint64_t a = 0, b = 0;
	for (size_t i = 0; i < (size_t)SW * SH / 2; i += 2) {
		a += p[i];
		b += p[i + 1];
	}
	sink += a + b;
}
static void t_read_wc(void)
{
	const uint64_t *p = (const uint64_t *)wc;
	uint64_t a = 0;
	for (size_t i = 0; i < (size_t)PW * PH / 2; i += 8)    /* one word per 64 B: a line-rate probe, not every byte */
		a += p[i];
	sink += a;
}
static void t_memcpy_cached(void) { memcpy(cached, src, (size_t)PW * PH * 4); }
static void t_memcpy_wc(void) { memcpy(wc, src, (size_t)PW * PH * 4); }

struct test {
	const char *name;
	void (*fn)(void);
	double mb;          /* MB moved (read + written) */
};

static int cmp(const void *a, const void *b)
{
	double x = *(const double *)a, y = *(const double *)b;
	return x < y ? -1 : x > y;
}

int main(int argc, char **argv)
{
	cpu = argc > 1 ? atoi(argv[1]) : 0;
	int reps = argc > 2 ? atoi(argv[2]) : 15;
	cpu_set_t set;
	CPU_ZERO(&set);
	CPU_SET(cpu, &set);
	if (sched_setaffinity(0, sizeof set, &set)) {
		perror("sched_setaffinity");
		return 2;
	}
	size_t pbytes = (size_t)PW * PH * 4, sbytes = (size_t)SW * SH * 4;
	if (posix_memalign((void **)&src, 4096, sbytes) || posix_memalign((void **)&cached, 4096, pbytes) ||
	    posix_memalign((void **)&scratch, 4096, 48u << 20))
		return 3;
	for (size_t i = 0; i < (size_t)SW * SH; i++)
		src[i] = (uint32_t)(i * 2654435761u) | 0xff000000u;
	memset(cached, 0, pbytes);
	memset(scratch, 1, 48u << 20);
	int hfd = open("/dev/dma_heap/system-uncached", O_RDONLY | O_CLOEXEC);
	if (hfd < 0) {
		printf("ERROR open system-uncached: %s\n", strerror(errno));
		return 4;
	}
	struct dma_heap_allocation_data a = { .len = pbytes, .fd_flags = O_RDWR | O_CLOEXEC };
	if (ioctl(hfd, DMA_HEAP_IOCTL_ALLOC, &a)) {
		printf("ERROR alloc: %s\n", strerror(errno));
		return 5;
	}
	wc = mmap(NULL, pbytes, PROT_READ | PROT_WRITE, MAP_SHARED, (int)a.fd, 0);
	if (wc == MAP_FAILED) {
		printf("ERROR mmap: %s\n", strerror(errno));
		return 6;
	}
	for (int x = 0; x < PW; x++)
		col[x] = (uint32_t)((int64_t)x * SW / PW);
	for (int y = 0; y < PH; y++)
		rowmap[y] = (uint32_t)((int64_t)y * SH / PH);
	make_runs();
	printf("runs per row %d\n", nruns);
	double scaled_mb = ((double)PH * PW * 4 * 2) / 1e6;        /* read about as much as written */
	struct test tests[] = {
		{ "pixel_wc", t_pixel_wc, scaled_mb },
		{ "runs_wc", t_runs_wc, scaled_mb },
		{ "pixel_cached", t_pixel_cached, scaled_mb },
		{ "runs_cached", t_runs_cached, scaled_mb },
		{ "runs_cached_clean", t_runs_cached_clean, scaled_mb },
		{ "table_wc", t_table_wc, scaled_mb },
		{ "table_cached", t_table_cached, scaled_mb },
		{ "memset_wc", t_memset_wc, pbytes / 1e6 },
		{ "memset_cached", t_memset_cached, pbytes / 1e6 },
		{ "read_src", t_read_src, sbytes / 1e6 },
		{ "read_wc_lines", t_read_wc, pbytes / 1e6 },
		{ "memcpy_cached", t_memcpy_cached, 2 * pbytes / 1e6 },
		{ "memcpy_wc", t_memcpy_wc, 2 * pbytes / 1e6 },
	};
	printf("copybench cpu %d reps %d src %dx%d panel %dx%d wc_heap system-uncached\n", cpu, reps, SW, SH, PW, PH);
	for (unsigned t = 0; t < sizeof tests / sizeof tests[0]; t++) {
		double ms[64];
		long k0 = khz();
		tests[t].fn();          /* warm the code and the page tables */
		for (int r = 0; r < reps && r < 64; r++) {
			evict();
			double t0 = now_ms();
			tests[t].fn();
			ms[r] = now_ms() - t0;
		}
		long k1 = khz();
		int n = reps < 64 ? reps : 64;
		qsort(ms, n, sizeof ms[0], cmp);
		printf("%-18s median %7.3f ms  min %7.3f ms  %6.0f MB/s(median)  khz %ld %ld\n", tests[t].name, ms[n / 2], ms[0],
		       tests[t].mb / (ms[n / 2] / 1e3), k0, k1);
		fflush(stdout);
	}
	/* the pixels of the two scalings agree (the host test's claim, once more on the phone) */
	scale_pixel(cached);
	scale_runs(wc);
	printf("check runs_wc == pixel_cached: %s\n", memcmp(cached, wc, pbytes) ? "DIFFER" : "same");
	memset(wc, 0, pbytes);
	scale_table(wc);
	printf("check table_wc == pixel_cached: %s\n", memcmp(cached, wc, pbytes) ? "DIFFER" : "same");
	return 0;
}
