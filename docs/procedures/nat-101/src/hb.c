// SPDX-License-Identifier: GPL-2.0-only
/*
 * NAT-101 hb: a launchd-independent heartbeat for the Stage A observability image.
 *
 * Started by /redwood/etc/rc as `/redwood/bin/hb &` (the donor init forks it and does not wait), before process 1 becomes Apple's launchd. It
 * writes to /dev/console itself and starts Apple's /bin/ps by itself, so what it prints does not pass through launchd, logd or any job
 * plist. NAT-098 showed that after Apple's logd ran, neither launchd's console lines nor the com.nat085.ps job's lists reached the returned
 * kernel log; this program separates "the console path is lost" (no hb line either) from "launchd's own routing is lost" (hb lines, no job
 * lines) and, when it works, lists the processes that exist (blocker B7).
 *
 * Each round (HB_PERIOD_S apart, HB_ROUNDS rounds):
 *   SWEET hb: n=<round> pid=<pid> ppid=<ppid> up=<seconds since start>
 *   then /bin/ps with its output on the console: odd rounds `ps -A` (the format NAT-088 returned), even rounds `ps -Ao pid,ppid,stat,comm`
 *   (parent and state: a crash-looping job shows as a zombie or a pid that keeps growing); a ps that does not finish in HB_PS_TIMEOUT_S is
 *   killed and the line says so;
 *   SWEET hb: n=<round> ps pid=<pid> status=<raw wait status> ms=<elapsed> [timeout-killed]
 *
 * Freestanding: no libc, raw Darwin arm64 system calls (number in x16, `svc #0x80`, carry set = error with errno in x0). Nothing is
 * written except to /dev/console; the only other process it starts is /bin/ps; it kills only that child.
 */
#ifndef HB_PERIOD_S
#define HB_PERIOD_S 10
#endif
#ifndef HB_ROUNDS
#define HB_ROUNDS 60
#endif
#ifndef HB_PS_TIMEOUT_S
#define HB_PS_TIMEOUT_S 8
#endif
#ifndef CONSOLE_DEV
#define CONSOLE_DEV "/dev/console"
#endif
#ifndef PS_PATH
#define PS_PATH "/bin/ps"
#endif
#define XSTR(x) #x
#define STR(x) XSTR(x)

typedef unsigned long u64;

struct tv {
	long sec;
	int usec;
	int pad;
};

#define SYS_exit 1
#define SYS_fork 2
#define SYS_write 4
#define SYS_open 5
#define SYS_wait4 7
#define SYS_getpid 20
#define SYS_kill 37
#define SYS_getppid 39
#define SYS_execve 59
#define SYS_dup2 90
#define SYS_select 93
#define SYS_gettimeofday 116

#define WNOHANG 1
#define SIGKILL 9

#ifdef HOST_TEST
/* Host model (tests only): the same control flow over libc, so the loop, the timeout kill and the output format can be exercised on Linux.
 * It does NOT test the raw Darwin system-call layer below (numbers, x1 child flag, carry convention). */
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/resource.h>
#include <sys/select.h>
#include <sys/time.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

static long sys_fork(long *is_child)
{
	pid_t p = fork();

	*is_child = (p == 0);
	return p < 0 ? -errno : (long)p;
}
static long sys_write(long fd, const void *p, u64 n) { return write((int)fd, p, n); }
static long sys_open(const char *path, long flags) { long r = open(path, (int)flags); return r < 0 ? -errno : r; }
static long sys_getpid(void) { return getpid(); }
static long sys_getppid(void) { return getppid(); }
static long sys_gettimeofday(struct tv *t)
{
	struct timeval v;

	gettimeofday(&v, 0);
	t->sec = v.tv_sec;
	t->usec = (int)v.tv_usec;
	return 0;
}
static long sys_wait4(long pid, int *status, long options) { long r = wait4((pid_t)pid, status, (int)options, 0); return r < 0 ? -errno : r; }
static long sys_kill(long pid, long sig) { return kill((pid_t)pid, (int)sig); }
static long sys_dup2(long from, long to) { return dup2((int)from, (int)to); }
static long sys_execve(const char *path, char *const argv[], char *const envp[]) { (void)path; return execve(PS_PATH, argv, envp); }
static long sys_select_sleep(long sec, int usec)
{
	struct timeval v;

	v.tv_sec = sec;
	v.tv_usec = usec;
	return select(0, 0, 0, 0, &v);
}
static void sys_exit(long code) { _exit((int)code); }
#else
/* number in x16, `svc #0x80`, result in x0, carry set = failure with errno in x0 (returned negated) */
static inline long sc5(long n, long a, long b, long c, long d, long e)
{
	register long r0 __asm__("x0") = a;
	register long r1 __asm__("x1") = b;
	register long r2 __asm__("x2") = c;
	register long r3 __asm__("x3") = d;
	register long r4 __asm__("x4") = e;
	register long r16 __asm__("x16") = n;
	long err;

	__asm__ volatile("svc #0x80\n\tcset %1, cs" : "+r"(r0), "=&r"(err), "+r"(r1) : "r"(r2), "r"(r3), "r"(r4), "r"(r16) : "memory", "cc");
	return err ? -r0 : r0;
}

/* fork: the parent gets the child's pid, the child gets x1 != 0 (and x0 = the parent's pid); libsyscall's ___fork tests x1 the same way */
static long sys_fork(long *is_child)
{
	register long r0 __asm__("x0") = 0;
	register long r1 __asm__("x1") = 0;
	register long r16 __asm__("x16") = SYS_fork;
	long err;

	__asm__ volatile("svc #0x80\n\tcset %2, cs" : "+r"(r0), "+r"(r1), "=&r"(err) : "r"(r16) : "memory", "cc");
	*is_child = (!err && r1 != 0);
	return err ? -r0 : r0;
}

static long sys_write(long fd, const void *p, u64 n) { return sc5(SYS_write, fd, (long)p, (long)n, 0, 0); }
static long sys_open(const char *path, long flags) { return sc5(SYS_open, (long)path, flags, 0, 0, 0); }
static long sys_getpid(void) { return sc5(SYS_getpid, 0, 0, 0, 0, 0); }
static long sys_getppid(void) { return sc5(SYS_getppid, 0, 0, 0, 0, 0); }
static long sys_gettimeofday(struct tv *t) { return sc5(SYS_gettimeofday, (long)t, 0, 0, 0, 0); }
static long sys_wait4(long pid, int *status, long options) { return sc5(SYS_wait4, pid, (long)status, options, 0, 0); }
static long sys_kill(long pid, long sig) { return sc5(SYS_kill, pid, sig, 0, 0, 0); }
static long sys_dup2(long from, long to) { return sc5(SYS_dup2, from, to, 0, 0, 0); }
static long sys_execve(const char *path, char *const argv[], char *const envp[]) { return sc5(SYS_execve, (long)path, (long)argv, (long)envp, 0, 0); }
static long sys_select_sleep(long sec, int usec)
{
	struct tv t;

	t.sec = sec;
	t.usec = usec;
	t.pad = 0;
	return sc5(SYS_select, 0, 0, 0, 0, (long)&t);
}
static void sys_exit(long code)
{
	sc5(SYS_exit, code, 0, 0, 0, 0);
	for (;;)
		;
}
#endif /* HOST_TEST */

/* ---- one line = one write, so a line is not split by another process's output ---- */
struct line {
	char b[160];
	unsigned n;
};

static void ls(struct line *l, const char *s)
{
	while (*s && l->n < sizeof(l->b) - 1)
		l->b[l->n++] = *s++;
}

static void ld(struct line *l, long v)
{
	char t[24];
	unsigned n = 0;
	u64 u = v < 0 ? (u64)-v : (u64)v;

	if (v < 0 && l->n < sizeof(l->b) - 1)
		l->b[l->n++] = '-';
	do {
		t[n++] = (char)('0' + u % 10);
		u /= 10;
	} while (u && n < sizeof(t));
	while (n && l->n < sizeof(l->b) - 1)
		l->b[l->n++] = t[--n];
}

static void lflush(struct line *l, long fd)
{
	sys_write(fd, l->b, l->n);
	l->n = 0;
}

static long ms_since(const struct tv *t0)
{
	struct tv t;

	sys_gettimeofday(&t);
	return (t.sec - t0->sec) * 1000 + (t.usec - t0->usec) / 1000;
}

/* start /bin/ps with the given argv and its stdout/stderr on the console; wait up to HB_PS_TIMEOUT_S; -> pid, *status, *timed_out */
static long run_ps(long con, char *argv[], int *status, int *timed_out, long *ms)
{
	/* local arrays: a static table of pointers would need rebase fixups, which the static wrapper (mkstatic.py) refuses */
	char *envp[2];
	struct tv t0;
	long child, pid, r, polls;

	envp[0] = (char *)"PATH=/bin:/sbin:/usr/bin:/usr/sbin";
	envp[1] = 0;
	*status = 0;
	*timed_out = 0;
	sys_gettimeofday(&t0);
	pid = sys_fork(&child);
	if (pid < 0) {
		*ms = ms_since(&t0);
		return pid;
	}
	if (child) {
		sys_dup2(con, 1);
		sys_dup2(con, 2);
		sys_execve(PS_PATH, argv, envp);
		sys_exit(127);
	}
	for (polls = 0; polls < HB_PS_TIMEOUT_S * 10; polls++) {
		r = sys_wait4(pid, status, WNOHANG);
		if (r == pid)
			goto done;
		if (r < 0)
			goto done;
		sys_select_sleep(0, 100000);
	}
	*timed_out = 1;
	sys_kill(pid, SIGKILL);
	sys_wait4(pid, status, 0);
done:
	*ms = ms_since(&t0);
	return pid;
}

#ifdef HOST_TEST
int main(void)
#else
__attribute__((used)) void hb_main(void)
#endif
{
	char *argv_a[3], *argv_o[4];
	struct line l;
	struct tv start;
	long con, pid, ppid, n, psp, ms;
	int status, timed_out;

	argv_a[0] = (char *)"ps";
	argv_a[1] = (char *)"-A";
	argv_a[2] = 0;
	argv_o[0] = (char *)"ps";
	argv_o[1] = (char *)"-Ao";
	argv_o[2] = (char *)"pid,ppid,stat,comm";
	argv_o[3] = 0;
	l.n = 0;
	con = sys_open(CONSOLE_DEV, 2);
	if (con < 0)
		sys_exit(2);
	pid = sys_getpid();
	ppid = sys_getppid();
	sys_gettimeofday(&start);
	ls(&l, "\nSWEET hb: start pid=");
	ld(&l, pid);
	ls(&l, " ppid=");
	ld(&l, ppid);
	ls(&l, " period=" STR(HB_PERIOD_S) "s rounds=" STR(HB_ROUNDS) " ps_timeout=" STR(HB_PS_TIMEOUT_S) "s\n");
	lflush(&l, con);
	for (n = 1; n <= HB_ROUNDS; n++) {
		ls(&l, "SWEET hb: n=");
		ld(&l, n);
		ls(&l, " pid=");
		ld(&l, sys_getpid());
		ls(&l, " ppid=");
		ld(&l, sys_getppid());
		ls(&l, " up=");
		ld(&l, ms_since(&start) / 1000);
		ls(&l, "\n");
		lflush(&l, con);
		psp = run_ps(con, (n & 1) ? argv_a : argv_o, &status, &timed_out, &ms);
		ls(&l, "SWEET hb: n=");
		ld(&l, n);
		ls(&l, " ps pid=");
		ld(&l, psp);
		ls(&l, " status=");
		ld(&l, status);
		ls(&l, " ms=");
		ld(&l, ms);
		if (timed_out)
			ls(&l, " timeout-killed");
		ls(&l, "\n");
		lflush(&l, con);
		sys_select_sleep(HB_PERIOD_S, 0);
	}
	ls(&l, "SWEET hb: done rounds=");
	ld(&l, HB_ROUNDS);
	ls(&l, "\n");
	lflush(&l, con);
	sys_exit(0);
#ifdef HOST_TEST
	return 0;
#endif
}

#ifndef HOST_TEST
/* the kernel starts the thread with sp = 0 replaced by its default user stack; align it and call the C function */
__asm__(".text\n.globl _start\n.p2align 2\n_start:\n\tmov x9, sp\n\tand x9, x9, #~15\n\tmov sp, x9\n\tbl _hb_main\n1:\tb 1b\n");
#endif
