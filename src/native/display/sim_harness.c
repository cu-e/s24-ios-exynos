/* SPDX-License-Identifier: GPL-2.0-only
 *
 * Host-only harness for e1s_boot_window.c (UI-007). It knows nothing about
 * DECON/DPP semantics: the test driver sends register images built from the
 * cited Samsung definitions and compares the JSON printed here.
 *
 * Every simulated MMIO block is an mmap between two PROT_NONE guard pages
 * and is PROT_READ while the reader runs, so any write or out-of-range read
 * by the module faults (SIGSEGV) instead of passing silently.
 *
 * stdin commands, one per line (numbers in C notation):
 *   region NAME SIZE        NAME: main win wincon dma0..dma15 sysmmu
 *   w NAME OFFSET VALUE     32-bit store into the image before protection
 *   vmid MASK               sysmmu_vmid_mask
 *   expect BASE SIZE W H OPTIONS
 *   run LABEL               protect, read, validate, print JSON, release all
 *   poke NAME OFFSET        self-test: protect, then write (must fault)
 *   peek-past NAME          self-test: protect, then read one word past end
 *   layout                  print e1s_dpu_mmio_default() as JSON
 */
#define _DEFAULT_SOURCE
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include "e1s_boot_window.h"

#define NREG ((int)(3 + E1S_BW_CHANNELS + 1))

struct region {
	char *map;
	size_t size, total;
};

static struct region regs[NREG];
static size_t page;
static uint32_t vmid;
static uint64_t ex_base, ex_size;
static uint32_t ex_w, ex_h, ex_opt;
static int have_expect;

static int index_of(const char *name)
{
	char buf[16];
	if (!strcmp(name, "main")) return 0;
	if (!strcmp(name, "win")) return 1;
	if (!strcmp(name, "wincon")) return 2;
	if (!strcmp(name, "sysmmu")) return NREG - 1;
	for (unsigned i = 0; i < E1S_BW_CHANNELS; i++) {
		snprintf(buf, sizeof buf, "dma%u", i);
		if (!strcmp(name, buf)) return 3 + (int)i;
	}
	return -1;
}

static void die(const char *what)
{
	fprintf(stderr, "harness: %s\n", what);
	exit(2);
}

static char *body(int i)
{
	return regs[i].map + page;
}

static void alloc_region(int i, size_t size)
{
	if (regs[i].map || !size || size % 4 || size > (1u << 20)) die("bad region");
	size_t rounded = (size + page - 1) / page * page;
	regs[i].total = rounded + 2 * page;
	regs[i].map = mmap(NULL, regs[i].total, PROT_READ | PROT_WRITE,
	    MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (regs[i].map == MAP_FAILED) die("mmap");
	regs[i].size = size;
	if (mprotect(regs[i].map, page, PROT_NONE) ||
	    mprotect(regs[i].map + page + rounded, page, PROT_NONE)) die("mprotect guard");
}

/* Start of the simulated block: aligned so that its last byte is followed by
 * the trailing guard page. */
static char *block(int i)
{
	size_t rounded = (regs[i].size + page - 1) / page * page;
	return body(i) + (rounded - regs[i].size);
}

static void protect_all(int prot)
{
	for (int i = 0; i < NREG; i++) {
		if (!regs[i].map) continue;
		size_t rounded = (regs[i].size + page - 1) / page * page;
		if (mprotect(body(i), rounded, prot)) die("mprotect body");
	}
}

static void release_all(void)
{
	for (int i = 0; i < NREG; i++) {
		if (regs[i].map) munmap(regs[i].map, regs[i].total);
		regs[i].map = NULL;
		regs[i].size = regs[i].total = 0;
	}
	vmid = 0;
	have_expect = 0;
}

static uintptr_t base_of(int i)
{
	return regs[i].map ? (uintptr_t)block(i) : 0;
}

static void run(const char *label)
{
	struct e1s_dpu_mmio m;
	struct e1s_boot_window w;
	uint32_t st, val = 0xFFFFFFFFu;

	m.decon_main = base_of(0);
	m.decon_win = base_of(1);
	m.decon_wincon = base_of(2);
	for (unsigned c = 0; c < E1S_BW_CHANNELS; c++) m.dpp_dma[c] = base_of(3 + (int)c);
	m.sysmmu = base_of(NREG - 1);
	m.sysmmu_vmid_mask = vmid;

	protect_all(PROT_READ);
	st = e1s_boot_window_read(&m, &w);
	if (have_expect) val = e1s_boot_window_validate(&w, ex_base, ex_size, ex_w, ex_h, ex_opt);
	protect_all(PROT_READ | PROT_WRITE);

	printf("{\"label\":\"%s\",\"ret\":%" PRIu32 ",\"status\":%" PRIu32 ",\"enabled\":%" PRIu32
	    ",\"window\":%" PRIu32 ",\"channel\":%" PRIu32 ",\"base\":%" PRIu64 ",\"stride\":%" PRIu32
	    ",\"format\":%" PRIu32 ",\"bpp\":%" PRIu32 ",\"width\":%" PRIu32 ",\"height\":%" PRIu32
	    ",\"src_width\":%" PRIu32 ",\"src_height\":%" PRIu32 ",\"src_x\":%" PRIu32 ",\"src_y\":%" PRIu32
	    ",\"win\":[%" PRIu32 ",%" PRIu32 ",%" PRIu32 ",%" PRIu32 "],\"enabled_mask\":%" PRIu32
	    ",\"colormap_mask\":%" PRIu32 ",\"flags\":%" PRIu32 ",\"global_con\":%" PRIu32
	    ",\"in_ctrl\":%" PRIu32 ",\"validate\":%" PRId64 "}\n",
	    label, st, w.status, w.enabled, w.window, w.channel, w.base, w.stride, w.format,
	    w.bytes_per_pixel, w.width, w.height, w.src_width, w.src_height, w.src_x, w.src_y,
	    w.win_x0, w.win_y0, w.win_x1, w.win_y1, w.enabled_mask, w.colormap_mask, w.flags,
	    w.global_con, w.in_ctrl, have_expect ? (int64_t)val : (int64_t)-1);
	fflush(stdout);
	release_all();
}

int main(void)
{
	char line[512], a[64], b[64];
	unsigned long long x, y, z, p, q;

	page = (size_t)sysconf(_SC_PAGESIZE);
	setvbuf(stdout, NULL, _IOLBF, 0);
	/* Null arguments are rejected without touching memory. */
	if (e1s_boot_window_read(NULL, NULL) != E1S_BW_ERR_ARGS) die("null args");

	while (fgets(line, sizeof line, stdin)) {
		if (sscanf(line, "region %63s %llx", a, &x) == 2) {
			int i = index_of(a);
			if (i < 0) die("unknown region");
			alloc_region(i, (size_t)x);
		} else if (sscanf(line, "w %63s %llx %llx", a, &x, &y) == 3) {
			int i = index_of(a);
			if (i < 0 || !regs[i].map || x % 4 || x + 4 > regs[i].size || y > 0xFFFFFFFFull)
				die("bad store");
			uint32_t v = (uint32_t)y;
			memcpy(block(i) + x, &v, 4);
		} else if (sscanf(line, "vmid %llx", &x) == 1) {
			vmid = (uint32_t)x;
		} else if (sscanf(line, "expect %llx %llx %llu %llu %llx", &x, &y, &z, &p, &q) == 5) {
			ex_base = x; ex_size = y; ex_w = (uint32_t)z; ex_h = (uint32_t)p; ex_opt = (uint32_t)q;
			have_expect = 1;
		} else if (sscanf(line, "run %63s", a) == 1) {
			run(a);
		} else if (sscanf(line, "poke %63s %llx", a, &x) == 2) {
			int i = index_of(a);
			if (i < 0 || !regs[i].map) die("bad poke");
			protect_all(PROT_READ);
			*(volatile uint32_t *)(block(i) + x) = 1;	/* must fault */
			printf("{\"poke\":\"not-faulted\"}\n");
			return 3;
		} else if (sscanf(line, "peek-past %63s", a) == 1) {
			int i = index_of(a);
			if (i < 0 || !regs[i].map) die("bad peek");
			protect_all(PROT_READ);
			volatile uint32_t sink = *(volatile uint32_t *)(block(i) + regs[i].size);	/* must fault */
			(void)sink;
			printf("{\"peek\":\"not-faulted\"}\n");
			return 3;
		} else if (sscanf(line, "%63s", b) == 1 && !strcmp(b, "layout")) {
			struct e1s_dpu_mmio m;
			e1s_dpu_mmio_default(&m);
			printf("{\"decon_main\":%" PRIuPTR ",\"decon_win\":%" PRIuPTR ",\"decon_wincon\":%" PRIuPTR
			    ",\"sysmmu\":%" PRIuPTR ",\"sysmmu_vmid_mask\":%" PRIu32 ",\"dpp_dma\":[",
			    m.decon_main, m.decon_win, m.decon_wincon, m.sysmmu, m.sysmmu_vmid_mask);
			for (unsigned c = 0; c < E1S_BW_CHANNELS; c++)
				printf("%s%" PRIuPTR, c ? "," : "", m.dpp_dma[c]);
			printf("]}\n");
		} else if (line[0] != '\n' && line[0] != '#') {
			die("unknown command");
		}
	}
	release_all();
	return 0;
}
