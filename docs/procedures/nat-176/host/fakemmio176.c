/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-176 host harness for the patched e1s_display.c: every ml_io_map() region is fresh read-only memory (a store would fault),
 * each word holds 0xA0000000 | (pa & 0x0fffffff) so printed values name their own address, except the three PMU status words,
 * taken from E1S_DPUB / E1S_DPUF0 / E1S_DPUF1 (default 1). Each map is logged ("map PA SIZE"). The clock is simulated:
 * delay_for_interval advances it; the run stops at 400 s. kernel_thread_start runs the thread at once (after the probe). */
#include <setjmp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

uint64_t host_ns;
static void (*pending)(void *, int);

uintptr_t
ml_io_map(uintptr_t pa, uintptr_t size)
{
	size_t len = (size + 4095) & ~(size_t)4095;
	uint32_t *m = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	size_t i;

	if (m == MAP_FAILED) {
		return 0;
	}
	for (i = 0; i < len / 4; i++) {
		m[i] = 0xA0000000u | (uint32_t)((pa + i * 4) & 0x0fffffffu);
	}
	if (pa == 0x12860000u) {
		const char *names[3] = { "E1S_DPUB", "E1S_DPUF0", "E1S_DPUF1" };
		const unsigned offs[3] = { 0x1d44, 0x1d84, 0x26c4 };
		for (i = 0; i < 3; i++) {
			const char *v = getenv(names[i]);
			m[offs[i] / 4] = v ? (uint32_t)strtoul(v, NULL, 0) : 1u;
		}
	}
	mprotect(m, len, PROT_READ);
	printf("map %#lx %#lx\n", (unsigned long)pa, (unsigned long)size);
	return (uintptr_t)m;
}

int
PE_parse_boot_argn(const char *n, void *v, int s)
{
	char key[64];
	const char *e;
	uint32_t x;

	snprintf(key, sizeof(key), "BOOTARG_%s", n);
	e = getenv(key);
	if (e == NULL || s < 4) {
		return 0;
	}
	x = (uint32_t)strtoul(e, NULL, 0);
	memcpy(v, &x, 4);
	return 1;
}

void
host_delay(uint64_t n, uint64_t scale)
{
	uint64_t before = host_ns / (50ull * 1000000000ull);

	host_ns += n * scale;
	if (host_ns / (50ull * 1000000000ull) != before) {
		printf("clock %llu s\n", (unsigned long long)(host_ns / (50ull * 1000000000ull) * 50));
	}
	if (host_ns > 400ull * 1000000000ull) {
		printf("RESULT end at %llu s\n", (unsigned long long)(host_ns / 1000000000ull));
		fflush(stdout);
		exit(0);
	}
}

int
host_thread_start(void (*f)(void *, int), void *a, void **t)
{
	(void)a;
	*t = 0;
	pending = f;
	return 0;
}

void e1s_display_probe(void);

int
main(void)
{
	host_ns = 123ull * 1000000000ull;
	e1s_display_probe();
	if (pending != NULL) {
		pending(NULL, 0);
	}
	printf("RESULT no thread\n");
	return 0;
}
