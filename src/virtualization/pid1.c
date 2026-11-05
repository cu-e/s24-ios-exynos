/* Owned VM-002 guest program: no libc, dyld, SDK or Apple userland.
 * Raw arm64 Darwin syscall ABI reviewed against pinned scion-avf
 * a6f4bc38aa244359cd365c976244a88c9d6b3304:userland/src/hello.c (MIT).
 * This file is independently authored, not the donor's hello program.
 */
typedef unsigned long usize;
struct result { long value; long error; };

static struct result call(long number, long a, long b, long c,
                          long d, long e, long f)
{
    register long x16 __asm__("x16") = number;
    register long x0 __asm__("x0") = a;
    register long x1 __asm__("x1") = b;
    register long x2 __asm__("x2") = c;
    register long x3 __asm__("x3") = d;
    register long x4 __asm__("x4") = e;
    register long x5 __asm__("x5") = f;
    long error;
    __asm__ volatile("svc #0x80\n\tcset %1, cs"
                     : "+r"(x0), "=&r"(error)
                     : "r"(x16), "r"(x1), "r"(x2), "r"(x3), "r"(x4), "r"(x5)
                     : "memory", "cc");
    return (struct result){ x0, error };
}

static void write_all(long fd, const char *text, usize size)
{
    while (size) {
        struct result r = call(4, fd, (long)text, (long)size, 0, 0, 0);
        if (r.error || r.value <= 0 || (usize)r.value > size)
            return;
        text += r.value;
        size -= (usize)r.value;
    }
}

__attribute__((noreturn)) void start(void)
{
    char ostype[32] = {0};
    usize size = sizeof(ostype);
    struct result console = call(5, (long)"/dev/console", 2, 0, 0, 0, 0);
    struct result pid = call(20, 0, 0, 0, 0, 0, 0);
    struct result os = call(274, (long)"kern.ostype", 11,
                           (long)ostype, (long)&size, 0, 0);
    int darwin = size == 7 && ostype[0] == 'D' && ostype[1] == 'a' &&
        ostype[2] == 'r' && ostype[3] == 'w' && ostype[4] == 'i' &&
        ostype[5] == 'n' && ostype[6] == 0;
    if (!console.error && !pid.error && pid.value == 1 && !os.error && darwin) {
        static const char verified[] = "\nVM002: pid=1 ostype=Darwin owned-entry=v1\n";
        write_all(console.value, verified, sizeof(verified) - 1);
    } else if (!console.error) {
        static const char failed[] = "\nVM002: guest identity checks failed\n";
        write_all(console.value, failed, sizeof(failed) - 1);
    }
    /* Exiting PID 1 intentionally panics XNU. Donor patch 1001 powers off
     * through PSCI; the host deadline must also work when that path fails. */
    (void)call(1, 0, 0, 0, 0, 0, 0);
    for (;;)
        __asm__ volatile("wfe");
}
