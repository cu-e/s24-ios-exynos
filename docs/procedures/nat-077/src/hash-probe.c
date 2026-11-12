/* NAT-077: the hashing probe. PID 1 of the payload kernel (the project's test /sbin/launchd, not Apple's launchd) that reads the root
 * device end to end through the kernel's own memory-disk driver and prints how many bytes it got, their SHA-256 and how long it took.
 *
 * Question it answers for NAT-078: are the bytes that the host pushed over USB into the reserved RAM region the bytes the kernel
 * reads back through /dev/rmd1 (MMU on, kernel-side read, user buffer)? The host knows the image's SHA-256; the probe prints one.
 *
 * Console text (all of it reaches the host through the image's console ring, as in NAT-068):
 *     \n*** SWEET hash probe: init running as PID 1 ***\n
 *     SWEET hash: reading /dev/rmd1 in chunks of 131072\n
 *     SWEET hash: at=<decimal> sha256=<64 hex digits> sec=<s>.<mmm>\n       (progress: SHA-256 of the first <at> bytes, about every 128 MiB)
 *     SWEET hash: bytes=<decimal> sha256=<64 hex digits> sec=<s>.<mmm>\n    (the end)
 *     SWEET probe: done, exiting\n
 * The progress lines let the host check every prefix of the image against hashlib: a run that the kernel cuts short (loader_return_after,
 * the watchdog) still shows the hash rate, and a corrupted byte is localised to a 128 MiB range.
 * Exit status: 0x50 + PID on success (81 for PID 1, the same class as the NAT-065 probe), 0x60 no console, 0x61 the device cannot be
 * opened, 0x62 a read failed (the kernel panics with that status and the analyser reads it), 0x63 the device had no bytes at all.
 *
 * Two builds of this one file: for arm64 iOS (no libc, the system calls are issued directly) and, with -DHOST_TEST, for the host
 * (libc stand-ins for the same six calls, plus a hook that limits how many bytes one read() returns, to exercise short reads).
 */
#include "sha256.h"

#ifndef ROOT_DEV
#define ROOT_DEV "/dev/rmd1"
#endif
#ifndef CHUNK
#define CHUNK 131072
#endif
#ifndef CKPT_BYTES
#define CKPT_BYTES (128ull << 20)
#endif
#ifndef CONSOLE_DEV
#define CONSOLE_DEV "/dev/console"
#endif

#define STR_(x) #x
#define STR(x) STR_(x)

#define EXIT_NO_CONSOLE 0x60
#define EXIT_NO_DEVICE 0x61
#define EXIT_READ_FAILED 0x62
#define EXIT_EMPTY 0x63
#define EINTR_ 4

struct tv {
	long long sec;
	int usec;
	int pad;
};

#ifdef HOST_TEST
#include <fcntl.h>
#include <sys/time.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>

/* test hooks, set by src/host-main.c */
unsigned long g_read_limit = 0;		/* at most this many bytes per read(), 0 = no limit */
unsigned long g_eintr_budget = 0;	/* the next this-many read() calls fail with EINTR */
unsigned long long g_fail_after = ~0ull;	/* once this many bytes were read, every read() fails with EIO */
unsigned long long g_total_read = 0;
unsigned long g_fake_step_us = 0;	/* nonzero: gettimeofday() is a fake clock that advances by this many microseconds per call */
unsigned long long g_fake_now_us = 1700000000ull * 1000000u;
int g_clock_backwards = 0;		/* the fake clock runs backwards instead */
unsigned long g_write_limit = 0;	/* at most this many bytes per write(), 0 = no limit */
/* what the hooks did, printed on stderr by src/host-main.c when the process ends, so that a test can tell a hook that took effect from one that did not */
unsigned long g_stat_reads, g_stat_eintr, g_stat_limited, g_stat_cut, g_stat_failed;
unsigned long g_stat_writes, g_stat_short_writes, g_stat_fake_clock, g_stat_real_clock;

static long sys_open(const char *path, long flags)
{
	int fd = open(path, (int)flags);

	return fd < 0 ? -errno : fd;
}
static long sys_read(long fd, void *buf, unsigned long n)
{
	long r;

	g_stat_reads++;
	if (g_eintr_budget) {
		g_eintr_budget--;
		g_stat_eintr++;
		return -EINTR;
	}
	if (g_total_read >= g_fail_after) {
		g_stat_failed++;
		return -EIO;
	}
	if (g_read_limit && n > g_read_limit) {
		n = g_read_limit;
		g_stat_limited++;
	}
	if (g_total_read + n > g_fail_after) {
		n = (unsigned long)(g_fail_after - g_total_read);
		g_stat_cut++;
	}
	r = read((int)fd, buf, n);
	if (r > 0)
		g_total_read += (unsigned long long)r;
	return r < 0 ? -errno : r;
}
static long sys_write(long fd, const void *buf, unsigned long n)
{
	long r;

	g_stat_writes++;
	if (g_write_limit && n > g_write_limit) {
		n = g_write_limit;
		g_stat_short_writes++;
	}
	r = write((int)fd, buf, n);
	return r < 0 ? -errno : r;
}
static long sys_getpid(void) { return getpid(); }
static long sys_gettimeofday(struct tv *t)
{
	struct timeval v;

	if (g_fake_step_us) {
		g_stat_fake_clock++;
		g_fake_now_us = g_clock_backwards ? g_fake_now_us - g_fake_step_us : g_fake_now_us + g_fake_step_us;
		t->sec = (long long)(g_fake_now_us / 1000000u);
		t->usec = (int)(g_fake_now_us % 1000000u);
		return 0;
	}
	g_stat_real_clock++;
	gettimeofday(&v, 0);
	t->sec = v.tv_sec;
	t->usec = (int)v.tv_usec;
	return 0;
}
static void sys_exit(long code) { exit((int)code); }
#else
/* Darwin arm64: number in x16, `svc #0x80`, result in x0, carry set = failure with errno in x0 */
static inline long sc(long n, long a, long b, long c)
{
	register long r0 __asm__("x0") = a;
	register long r1 __asm__("x1") = b;
	register long r2 __asm__("x2") = c;
	register long r16 __asm__("x16") = n;
	long err;

	__asm__ volatile("svc #0x80\n\tcset %1, cs" : "+r"(r0), "=&r"(err), "+r"(r1) : "r"(r2), "r"(r16) : "memory", "cc");
	return err ? -r0 : r0;
}
static long sys_open(const char *path, long flags) { return sc(5, (long)path, flags, 0); }
static long sys_read(long fd, void *buf, unsigned long n) { return sc(3, fd, (long)buf, (long)n); }
static long sys_write(long fd, const void *buf, unsigned long n) { return sc(4, fd, (long)buf, (long)n); }
static long sys_getpid(void) { return sc(20, 0, 0, 0); }
static long sys_gettimeofday(struct tv *t) { return sc(116, (long)t, 0, 0); }
static void sys_exit(long code)
{
	sc(1, code, 0, 0);
	for (;;)
		;
}
#endif

/* no global state at all: the wrapper carries code and read-only data only (a writable global lands in __DATA and is refused) */
static void put(long con, const char *s)
{
	unsigned long n = 0;

	while (s[n])
		n++;
	while (n) {
		long r = sys_write(con, s, n);

		if (r <= 0)
			return;
		s += r;
		n -= (unsigned long)r;
	}
}

/* unsigned decimal, at least `width` digits (zero padded) */
static void put_dec(long con, sha_u64 v, unsigned width)
{
	char b[24];
	unsigned i = sizeof(b) - 1;

	b[i] = 0;
	do {
		b[--i] = (char)('0' + v % 10);
		v /= 10;
	} while (v);
	while (sizeof(b) - 1 - i < width)
		b[--i] = '0';
	put(con, b + i);
}

static void put_hex(long con, const sha_u8 *p, unsigned n)
{
	char b[3];
	unsigned i;

	b[2] = 0;
	for (i = 0; i < n; i++) {
		b[0] = "0123456789abcdef"[p[i] >> 4];
		b[1] = "0123456789abcdef"[p[i] & 15];
		put(con, b);
	}
}

/* <seconds>.<milliseconds>, e.g. 3600.000 */
static void put_secs(long con, sha_u64 us)
{
	put_dec(con, us / 1000000u, 1);
	put(con, ".");
	put_dec(con, us / 1000u % 1000u, 3);
}

/* a field-by-field copy: with -ffreestanding there is no memcpy to call */
static void sha256_copy(struct sha256 *d, const struct sha256 *s)
{
	unsigned i;

	for (i = 0; i < 8; i++)
		d->h[i] = s->h[i];
	for (i = 0; i < 64; i++)
		d->buf[i] = s->buf[i];
	d->total = s->total;
	d->fill = s->fill;
}

static sha_u64 now_us(void)
{
	struct tv t = {0, 0, 0};

	sys_gettimeofday(&t);
	return (sha_u64)t.sec * 1000000u + (sha_u64)t.usec;
}

static sha_u64 since_us(sha_u64 t0)
{
	sha_u64 t = now_us();

	return t >= t0 ? t - t0 : 0;		/* a clock that went backwards reads as zero, not as 584,000 years */
}

#ifdef HOST_TEST
int probe_main(void)
#else
__attribute__((used)) void probe_main(void)
#endif
{
	static const char dev[] = ROOT_DEV;
	sha_u8 buf[CHUNK];
	sha_u8 digest[32];
	struct sha256 s;
	sha_u64 bytes = 0, next_ckpt = CKPT_BYTES, t0, us;
	long con, fd, pid, r;

	con = sys_open(CONSOLE_DEV, 2);
	if (con < 0)
		sys_exit(EXIT_NO_CONSOLE);
	pid = sys_getpid();
	put(con, "\n*** SWEET hash probe: init running as PID ");
	put_dec(con, (sha_u64)pid, 1);
	put(con, " ***\n");
	fd = sys_open(dev, 0);
	if (fd < 0) {
		put(con, "SWEET hash: cannot open " ROOT_DEV ", errno ");
		put_dec(con, (sha_u64)-fd, 1);
		put(con, "\n");
		sys_exit(EXIT_NO_DEVICE);
	}
	put(con, "SWEET hash: reading " ROOT_DEV " in chunks of " STR(CHUNK) "\n");
	sha256_init(&s);
	t0 = now_us();
	for (;;) {
		r = sys_read(fd, buf, sizeof(buf));
		if (r == -EINTR_)
			continue;
		if (r < 0) {
			put(con, "SWEET hash: read failed after ");
			put_dec(con, bytes, 1);
			put(con, " bytes, errno ");
			put_dec(con, (sha_u64)-r, 1);
			put(con, "\n");
			sys_exit(EXIT_READ_FAILED);
		}
		if (r == 0)
			break;
		sha256_update(&s, buf, (sha_u64)r);
		bytes += (sha_u64)r;
		if (bytes >= next_ckpt) {
			struct sha256 c;
			sha_u8 d[32];

			sha256_copy(&c, &s);
			sha256_final(&c, d);
			put(con, "SWEET hash: at=");
			put_dec(con, bytes, 1);
			put(con, " sha256=");
			put_hex(con, d, 32);
			put(con, " sec=");
			put_secs(con, since_us(t0));
			put(con, "\n");
			next_ckpt = bytes - bytes % CKPT_BYTES + CKPT_BYTES;
		}
	}
	sha256_final(&s, digest);
	us = since_us(t0);
	put(con, "SWEET hash: bytes=");
	put_dec(con, bytes, 1);
	put(con, " sha256=");
	put_hex(con, digest, 32);
	put(con, " sec=");
	put_secs(con, us);
	put(con, "\n");
	if (!bytes)
		sys_exit(EXIT_EMPTY);
	put(con, "SWEET probe: done, exiting\n");
	sys_exit(0x50 + pid);
#ifdef HOST_TEST
	return 0;
#endif
}

#ifndef HOST_TEST
/* the kernel starts the thread with sp = 0 replaced by its default user stack; align it and call the C function */
__asm__(".text\n.globl _start\n.p2align 2\n_start:\n\tmov x9, sp\n\tand x9, x9, #~15\n\tmov sp, x9\n\tbl _probe_main\n1:\tb 1b\n");
#endif
