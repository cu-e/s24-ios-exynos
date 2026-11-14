/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-185 host harness (NAT-176's plus a simulated process table) for the patched e1s_display.c: every ml_io_map() region is fresh read-only memory (a store would fault),
 * each word holds 0xA0000000 | (pa & 0x0fffffff) so printed values name their own address, except the three PMU status words,
 * taken from E1S_DPUB / E1S_DPUF0 / E1S_DPUF1 (default 1). Each map is logged ("map PA SIZE"). The clock is simulated:
 * delay_for_interval advances it; the run stops at 400 s. kernel_thread_start runs the thread at once (after the probe). */
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

uint64_t host_ns;
static void (*pending[4])(void *, int);
static int npending;

/* processes: each uses a fixed share of the time while it lives; HOST_FILLERS more idle ones (overflow test) */
struct host_proc {
	int pid;
	const char *name;
	double share, born_s, died_s;
};
static struct host_proc procs[400] = {
	{ 0, "kernel_task", 0.10, 0, 1e9 },
	{ 1, "launchd", 0.01, 0, 1e9 },
	{ 40, "backboardd", 0.25, 0, 1e9 },
	{ 50, "SpringBoard", 0.40, 0, 1e9 },
	{ 106, "mediaserverd", 0.05, 252.5, 300 },
	{ 200, "a-very-long-process-name-indeed", 0.02, 0, 1e9 },
};
static int nprocs = 6;

static uint64_t
lived_ns(const struct host_proc *p)
{
	double now = host_ns / 1e9, end = now < p->died_s ? now : p->died_s;

	return end > p->born_s ? (uint64_t)((end - p->born_s) * p->share * 1e9) : 0;
}

void
proc_iterate(unsigned int flags, int (*callout)(struct host_proc *, void *), void *arg, void *f, void *fa)
{
	(void)flags; (void)f; (void)fa;
	for (int i = 0; i < nprocs; i++) {
		double now = host_ns / 1e9;

		if (now >= procs[i].born_s && now < procs[i].died_s) {
			callout(&procs[i], arg);
		}
	}
}

int proc_pid(struct host_proc *p) { return p->pid; }
struct host_proc *proc_task(struct host_proc *p) { return p; }
char *proc_best_name(struct host_proc *p) { return (char *)p->name; }
struct recount_times_mach { uint64_t rtm_user, rtm_system; };
struct recount_times_mach
recount_task_times(struct host_proc *t)
{
	uint64_t n = lived_ns(t);
	struct recount_times_mach r = { n * 3 / 4, n - n * 3 / 4 };
	return r;
}

bool
ml_cpu_idle_time(int cpu, uint64_t *idle)
{
	if (cpu != 0 || getenv("HOST_NO_IDLE")) {
		return false;
	}
	*idle = host_ns / 5;
	return true;
}

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
	if (npending < 4) {
		pending[npending++] = f;
	}
	return 0;
}

void e1s_display_probe(void);

int
main(void)
{
	const char *which = getenv("HOST_THREAD"), *fill = getenv("HOST_FILLERS");
	int w;

	for (int i = 0; fill && i < atoi(fill) && nprocs < 400; i++) {
		procs[nprocs++] = (struct host_proc){ 1000 + i, "filler", 0.0, 0, 1e9 };
	}
	host_ns = 123ull * 1000000000ull;
	e1s_display_probe();
	printf("threads %d\n", npending);
	w = which ? atoi(which) : npending - 1;
	if (w >= 0 && w < npending) {
		pending[w](NULL, 0);
	}
	printf("RESULT no thread\n");
	return 0;
}
