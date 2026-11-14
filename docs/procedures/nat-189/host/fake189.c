/* SPDX-License-Identifier: GPL-2.0-only */
/* NAT-189 host harness (NAT-185's plus backboardd threads, saved user state and the shared region) for the patched e1s_display.c: every ml_io_map() region is fresh read-only memory (a store would fault),
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

/* processes: each uses a fixed share of the time while it lives. backboardd (pid 40; with HOST_RESTART_S it dies then and comes back
 * as pid 41 half a second later) has threads whose run time grows by a fixed pattern of the tick number n (= calls of
 * task_act_iterate_wth_args): A (tid 100) when n % 10 < 6, B (101) when n % 10 is 6..8, D (102, outside the cache) when n % 50 == 9,
 * C (103) never; HOST_CHURN adds a new short-lived thread every tick, HOST_BBD_THREADS more always-idle ones. */
struct recount_times_mach { uint64_t rtm_user, rtm_system; };
struct arm_saved_state { uint64_t pc, lr; };
struct host_proc {
	int pid;
	const char *name;
	double share, born_s, died_s;
};
static struct host_proc procs[8] = {
	{ 0, "kernel_task", 0.10, 0, 1e9 },
	{ 1, "launchd", 0.01, 0, 1e9 },
	{ 40, "backboardd", 0.25, 0, 1e9 },
	{ 50, "SpringBoard", 0.40, 0, 1e9 },
	{ 41, "backboardd", 0.25, 1e9, 1e9 },
};
static int nprocs = 5;
static int refs;

#define START 0x1a0000000ull
struct host_thread {
	uint64_t tid, time;
	struct arm_saved_state ss;
};
static struct host_thread threads[200];
static int nthreads;
static uint64_t iterations, self_ns;
struct host_sr { int dummy; } host_sr;

void *
host_kalloc(size_t size, int flags)
{
	if (getenv("HOST_NO_ALLOC")) {
		return NULL;
	}
	if (flags != 3) {
		printf("BAD kalloc flags %d\n", flags);
	}
	return calloc(1, size);
}

static bool
alive(const struct host_proc *p)
{
	double now = host_ns / 1e9;

	return now >= p->born_s && now < p->died_s;
}

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
		if (alive(&procs[i])) {
			callout(&procs[i], arg);
		}
	}
}

struct host_proc *
proc_find(int pid)
{
	for (int i = 0; i < nprocs; i++) {
		if (procs[i].pid == pid && alive(&procs[i])) {
			refs++;
			return &procs[i];
		}
	}
	return NULL;
}

int proc_rele(struct host_proc *p) { (void)p; refs--; return 0; }
int proc_pid(struct host_proc *p) { return p->pid; }
struct host_proc *proc_task(struct host_proc *p) { return p; }
char *proc_best_name(struct host_proc *p) { return (char *)p->name; }
struct recount_times_mach
recount_task_times(struct host_proc *t)
{
	uint64_t n = lived_ns(t);
	struct recount_times_mach r = { n * 3 / 4, n - n * 3 / 4 };
	return r;
}

uint64_t recount_thread_time_mach(struct host_thread *th) { return th->time; }
uint64_t recount_current_thread_time_mach(void) { return self_ns; }
uint64_t thread_tid(struct host_thread *th) { return th->tid; }
struct arm_saved_state *get_user_regs(struct host_thread *th) { return &th->ss; }

struct host_sr *
vm_shared_region_get(struct host_proc *t)
{
	(void)t;
	if (getenv("HOST_NO_SR")) {
		return NULL;
	}
	refs++;
	return &host_sr;
}

int
vm_shared_region_start_address(struct host_sr *sr, uint64_t *start, struct host_proc *t)
{
	(void)sr;
	if (t != NULL) {
		printf("BAD start_address with a task\n");
	}
	*start = START;
	return 0;
}

void vm_shared_region_deallocate(struct host_sr *sr) { (void)sr; refs--; }

void
task_act_iterate_wth_args(struct host_proc *task, void (*func)(struct host_thread *, void *), void *arg)
{
	uint64_t n = ++iterations;

	if (strcmp(task->name, "backboardd") != 0) {
		printf("BAD iterate %s\n", task->name);
		return;
	}
	self_ns += 5000;
	if (getenv("HOST_CHURN")) {
		threads[nthreads - 1].tid = 100000 + n;        /* the last slot is a new thread every tick */
		threads[nthreads - 1].time = 1;
	}
	threads[0].time += (n % 10 < 6) ? 1000 : 0;
	threads[1].time += (n % 10 >= 6 && n % 10 <= 8) ? 1000 : 0;
	threads[2].time += (n % 50 == 9) ? 1000 : 0;
	for (int i = 0; i < nthreads; i++) {
		func(&threads[i], arg);
	}
}

static void
threads_init(void)
{
	const char *more = getenv("HOST_BBD_THREADS");

	threads[0] = (struct host_thread){ 100, 0, { START + 0x1000047, START + 0x2000013 } };
	threads[1] = (struct host_thread){ 101, 0, { START + 0x3000088, START + 0x2000013 } };
	threads[2] = (struct host_thread){ 102, 0, { 0x100004010ull, 0x100004100ull } };
	threads[3] = (struct host_thread){ 103, 0, { START + 0x5000000, START + 0x5000004 } };
	nthreads = 4;
	for (int i = 0; more && i < atoi(more) && nthreads < 199; i++) {
		threads[nthreads] = (struct host_thread){ 500 + (uint64_t)i, 0, { START + 0x6000000, 0 } };
		nthreads++;
	}
	if (getenv("HOST_CHURN")) {
		threads[nthreads++] = (struct host_thread){ 100000, 0, { START + 0x7000000, 0 } };
	}
	if (getenv("HOST_RESTART_S")) {
		procs[2].died_s = atof(getenv("HOST_RESTART_S"));
		procs[4].born_s = procs[2].died_s + 0.5;
	}
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
		printf("RESULT end at %llu s refs %d iterations %llu\n", (unsigned long long)(host_ns / 1000000000ull), refs, (unsigned long long)iterations);
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

	(void)fill;
	threads_init();
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
