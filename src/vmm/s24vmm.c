/* s24vmm: a small root-run KVM VMM for avfboot guests on the Galaxy S24 (Android, arm64).
 *
 * Loads an arm64 Image (avfboot) at the start of guest RAM, the initrd (XNUP payload) 16 MiB-aligned
 * behind it and an FDT at the top of RAM, the way crosvm does, then runs vCPU 0 at the Image with
 * x0 = FDT. Devices: in-kernel vGICv3 and PSCI (KVM), arch timer, an emulated ns16550a at 0x3f8 and a
 * PL031 at 0x2000. Every run is bounded: --timeout seconds, then all vCPUs are kicked out of KVM_RUN
 * and the process exits. A JSON summary goes to stderr as the last line.
 *
 * Usage: s24vmm --image PATH [--initrd PATH] [--mem MiB] [--cpus N] [--params STR]
 *               [--timeout SEC] [--pin CPU,CPU,...] [--console PATH]
 *               [--scfb WxH] [--input] [--display-port PORT]
 *
 * --scfb reserves a Scion shared framebuffer below the FDT and passes scfb.addr/size/w/h to avfboot;
 * --input adds a virtio-mmio virtio-input multi-touch device at 0x0a000000 (SPI 16) and virtio_input=1.
 * With either, a display thread serves frames and accepts touches on 127.0.0.1:PORT (default 5824).
 */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <sys/socket.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <pthread.h>
#include <sched.h>
#include <signal.h>
#include <stdatomic.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "machine.h"
#include "scfb.h"
#include "virtio.h"

#define CORE_REG(x) (KVM_REG_ARM64 | KVM_REG_SIZE_U64 | KVM_REG_ARM_CORE | (offsetof(struct kvm_regs, x) / sizeof(uint32_t)))
#define MAX_UNKNOWN 16

struct vcpu {
    int index, fd, host_cpu;
    pthread_t thread;
    struct kvm_run *run;
    uint64_t exits, mmio;
    int last_reason;
    int running; /* guarded by g.kick_lock: only a running thread may be signalled */
};

static struct {
    int kvm, vm, gic;
    long run_size;
    uint8_t *ram;
    struct vmm_layout layout;
    struct vcpu vcpus[VMM_MAX_CPUS];
    pthread_mutex_t lock, kick_lock;
    struct vmm_uart uart;
    struct vmm_rtc rtc;
    FILE *console;
    uint64_t console_bytes;
    atomic_int stop;
    char cause[96];
    uint64_t unknown_addr[MAX_UNKNOWN];
    unsigned unknown_count;
    uint64_t unknown_total;
    int system_event;
    struct vio_ram vram;
    struct vio_input input;
    int input_on;
    uint16_t display_port;
    pthread_t display_thread;
    int display_on;
    uint64_t frames_sent, frame_bytes, touches, clients, first_frame_ms;
} g = {.kvm = -1, .vm = -1, .gic = -1, .lock = PTHREAD_MUTEX_INITIALIZER, .kick_lock = PTHREAD_MUTEX_INITIALIZER, .system_event = -1};

static void die(const char *what) {
    fprintf(stderr, "{\"s24vmm\":\"error\",\"step\":\"%s\",\"errno\":%d,\"error\":\"%s\"}\n", what, errno, strerror(errno));
    exit(2);
}

static void set_cause(const char *cause) {
    pthread_mutex_lock(&g.lock);
    if (!g.cause[0]) snprintf(g.cause, sizeof g.cause, "%s", cause);
    pthread_mutex_unlock(&g.lock);
    atomic_store(&g.stop, 1);
}

static void on_kick(int sig) {
    (void)sig;
}

/* Called only by the main thread. Bionic aborts on pthread_kill of an exited thread, so a vCPU thread
 * clears `running` under kick_lock before it returns and is never signalled afterwards. */
static void kick_all(void) {
    pthread_mutex_lock(&g.kick_lock);
    for (uint32_t i = 0; i < g.layout.cpus; i++) {
        struct vcpu *v = &g.vcpus[i];
        if (!v->running) continue;
        v->run->immediate_exit = 1;
        pthread_kill(v->thread, SIGUSR1);
    }
    pthread_mutex_unlock(&g.kick_lock);
}

static int64_t host_seconds(void) {
    return (int64_t)time(NULL);
}

static void mmio(struct vcpu *v) {
    struct kvm_run *run = v->run;
    uint64_t addr = run->mmio.phys_addr, value = 0;
    uint32_t len = run->mmio.len <= 8 ? run->mmio.len : 8;
    v->mmio++;
    if (run->mmio.is_write) memcpy(&value, run->mmio.data, len);
    pthread_mutex_lock(&g.lock);
    if (addr >= VMM_UART_BASE && addr < VMM_UART_BASE + VMM_UART_SIZE) {
        uint64_t off = addr - VMM_UART_BASE;
        if (run->mmio.is_write) {
            uint8_t tx;
            if (vmm_uart_write(&g.uart, off, (uint8_t)value, &tx)) {
                fputc(tx, stdout);
                if (tx == '\n') fflush(stdout);
                if (g.console) fputc(tx, g.console);
                g.console_bytes++;
            }
        } else {
            value = vmm_uart_read(&g.uart, off);
        }
    } else if (addr >= VMM_RTC_BASE && addr < VMM_RTC_BASE + VMM_RTC_SIZE) {
        uint64_t off = addr - VMM_RTC_BASE;
        if (run->mmio.is_write) vmm_rtc_write(&g.rtc, off, (uint32_t)value, host_seconds());
        else value = vmm_rtc_read(&g.rtc, off, host_seconds());
    } else if (g.input_on && addr >= VIO_MMIO_BASE && addr < VIO_MMIO_BASE + 32 * VIO_MMIO_SLOT) {
        uint64_t off = addr - VIO_MMIO_BASE;
        if (off < VIO_MMIO_SLOT) {
            if (run->mmio.is_write) vio_mmio_write(&g.input.dev, off, (uint32_t)value, len);
            else value = vio_mmio_read(&g.input.dev, off, len);
        } else {
            value = 0; /* empty slots: magic 0, the guest skips them */
        }
    } else {
        g.unknown_total++;
        int seen = 0;
        for (unsigned i = 0; i < g.unknown_count; i++) seen |= g.unknown_addr[i] == addr;
        if (!seen && g.unknown_count < MAX_UNKNOWN) g.unknown_addr[g.unknown_count++] = addr;
        value = 0;
    }
    pthread_mutex_unlock(&g.lock);
    if (!run->mmio.is_write) memcpy(run->mmio.data, &value, len);
}

static void *vcpu_main(void *arg) {
    struct vcpu *v = arg;
    if (v->host_cpu >= 0) {
        cpu_set_t set;
        CPU_ZERO(&set);
        CPU_SET(v->host_cpu, &set);
        sched_setaffinity(0, sizeof set, &set);
    }
    while (!atomic_load(&g.stop)) {
        if (ioctl(v->fd, KVM_RUN, 0) < 0) {
            if (errno == EINTR || errno == EAGAIN) {
                v->run->immediate_exit = 0;
                continue;
            }
            char cause[64];
            snprintf(cause, sizeof cause, "vcpu%d KVM_RUN errno %d", v->index, errno);
            set_cause(cause);
            break;
        }
        v->exits++;
        v->last_reason = (int)v->run->exit_reason;
        switch (v->run->exit_reason) {
        case KVM_EXIT_MMIO:
            mmio(v);
            break;
        case KVM_EXIT_SYSTEM_EVENT:
            pthread_mutex_lock(&g.lock);
            g.system_event = (int)v->run->system_event.type;
            pthread_mutex_unlock(&g.lock);
            set_cause(v->run->system_event.type == KVM_SYSTEM_EVENT_SHUTDOWN ? "psci-system-off"
                      : v->run->system_event.type == KVM_SYSTEM_EVENT_RESET  ? "psci-system-reset"
                                                                             : "system-event");
            break;
        default: {
            char cause[64];
            snprintf(cause, sizeof cause, "vcpu%d exit reason %u", v->index, v->run->exit_reason);
            set_cause(cause);
            break;
        }
        }
    }
    pthread_mutex_lock(&g.kick_lock);
    v->running = 0;
    pthread_mutex_unlock(&g.kick_lock);
    return NULL;
}

/* Level-triggered SPI for the virtio-mmio slot; called with g.lock held. */
static void input_irq(void *context, int level) {
    (void)context;
    struct kvm_irq_level irq = {.irq = (KVM_ARM_IRQ_TYPE_SPI << KVM_ARM_IRQ_TYPE_SHIFT) | (32u + VIO_MMIO_SPI_BASE), .level = (uint32_t)level};
    ioctl(g.vm, KVM_IRQ_LINE, &irq);
}

static uint64_t mono_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000u + (uint64_t)ts.tv_nsec / 1000000u;
}

static int send_all(int fd, const uint8_t *p, size_t n) {
    while (n) {
        ssize_t k = send(fd, p, n, MSG_NOSIGNAL);
        if (k <= 0) {
            if (k < 0 && errno == EINTR) continue;
            return -1;
        }
        p += k;
        n -= (size_t)k;
    }
    return 0;
}

/* One viewer at a time on 127.0.0.1:port. Frames go out when the guest publishes one (or at 10 Hz
 * while the header says POLL); touch messages come back and become virtio-input reports. */
static void *display_main(void *arg) {
    (void)arg;
    uint64_t start = mono_ms();
    int ls = socket(AF_INET, SOCK_STREAM | SOCK_CLOEXEC, 0), one = 1, client = -1;
    struct sockaddr_in addr = {.sin_family = AF_INET, .sin_port = htons(g.display_port), .sin_addr.s_addr = htonl(INADDR_LOOPBACK)};
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if (ls < 0 || bind(ls, (struct sockaddr *)&addr, sizeof addr) < 0 || listen(ls, 1) < 0) {
        fprintf(stderr, "{\"s24vmm\":\"display\",\"error\":\"listen %u: %s\"}\n", g.display_port, strerror(errno));
        if (ls >= 0) close(ls);
        return NULL;
    }
    size_t cap = (size_t)g.layout.scfb_w * g.layout.scfb_h * 4;
    uint8_t *pixels = cap ? malloc(cap) : NULL, rx[S24T_BYTES];
    size_t rx_len = 0;
    struct scfb_reader reader = {0};
    uint64_t last_poll_copy = 0;
    int force = 0;
    while (!atomic_load(&g.stop)) {
        struct pollfd fds[2] = {{.fd = client >= 0 ? client : ls, .events = POLLIN}};
        int n = poll(fds, 1, 8);
        if (n > 0 && client < 0 && (fds[0].revents & POLLIN)) {
            client = accept4(ls, NULL, NULL, SOCK_CLOEXEC);
            if (client >= 0) {
                setsockopt(client, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
                g.clients++;
                force = 1;
                rx_len = 0;
            }
            continue;
        }
        if (n > 0 && client >= 0 && (fds[0].revents & (POLLIN | POLLHUP | POLLERR))) {
            ssize_t k = recv(client, rx + rx_len, sizeof rx - rx_len, MSG_DONTWAIT);
            if (k <= 0) {
                close(client);
                client = -1;
                continue;
            }
            rx_len += (size_t)k;
            if (rx_len == sizeof rx) {
                struct s24t_touch t;
                if (!s24t_decode(rx, &t) && g.input_on) {
                    pthread_mutex_lock(&g.lock);
                    static int down[VIN_SLOTS];
                    down[t.slot] = t.tracking_id >= 0;
                    int any = 0;
                    for (int i = 0; i < VIN_SLOTS; i++) any |= down[i];
                    vin_touch(&g.input, t.slot, t.tracking_id, t.x, t.y, any);
                    pthread_mutex_unlock(&g.lock);
                    g.touches++;
                }
                rx_len = 0;
            }
        }
        if (client < 0 || !pixels) continue;
        uint8_t *region = g.ram + (g.layout.scfb_addr - VMM_RAM_BASE);
        uint64_t now = mono_ms();
        struct scfb_frame f = {.pixels = pixels};
        /* POLL frames (boot console, nothing published yet) at 10 Hz; published frames at once */
        int poll_due = now - last_poll_copy >= 100;
        enum scfb_result r = scfb_read(&reader, region, g.layout.scfb_size, g.layout.scfb_w, g.layout.scfb_h, force || poll_due, &f);
        if (poll_due) last_poll_copy = now;
        if (r != SCFB_FRAME) continue;
        force = 0;
        uint8_t header[S24F_HEADER_BYTES];
        s24f_encode_header(header, &f);
        if (send_all(client, header, sizeof header) || send_all(client, pixels, (size_t)f.w * f.h * 4)) {
            close(client);
            client = -1;
            continue;
        }
        if (!g.frames_sent) g.first_frame_ms = now - start;
        g.frames_sent++;
        g.frame_bytes += sizeof header + (uint64_t)f.w * f.h * 4;
    }
    if (client >= 0) close(client);
    close(ls);
    free(pixels);
    return NULL;
}

static uint8_t *read_file(const char *path, size_t *len) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) die("open input");
    struct stat st;
    if (fstat(fd, &st) < 0) die("stat input");
    uint8_t *buf = malloc((size_t)st.st_size ? (size_t)st.st_size : 1);
    if (!buf) die("malloc input");
    size_t got = 0;
    while (got < (size_t)st.st_size) {
        ssize_t n = read(fd, buf + got, (size_t)st.st_size - got);
        if (n <= 0) die("read input");
        got += (size_t)n;
    }
    close(fd);
    *len = got;
    return buf;
}

static void set_reg(int fd, uint64_t id, uint64_t value, const char *what) {
    struct kvm_one_reg reg = {.id = id, .addr = (uint64_t)(uintptr_t)&value};
    if (ioctl(fd, KVM_SET_ONE_REG, &reg) < 0) die(what);
}

static uint64_t get_reg(int fd, uint64_t id) {
    uint64_t value = 0;
    struct kvm_one_reg reg = {.id = id, .addr = (uint64_t)(uintptr_t)&value};
    if (ioctl(fd, KVM_GET_ONE_REG, &reg) < 0) return ~0ull;
    return value;
}

/* End-of-run guest state for diagnosing a stuck guest: exception syndrome, translation and vector
 * registers, and the general registers, as hex strings (all ~0 when a register cannot be read). */
#define SYS_REG(op0, op1, crn, crm, op2) ARM64_SYS_REG(op0, op1, crn, crm, op2)
static void dump_regs(int fd) {
    static const struct { const char *name; uint64_t id; } named[] = {
        {"pc", CORE_REG(regs.pc)}, {"pstate", CORE_REG(regs.pstate)}, {"sp_el0", CORE_REG(regs.sp)},
        {"sp_el1", CORE_REG(sp_el1)}, {"elr_el1", CORE_REG(elr_el1)}, {"spsr_el1", CORE_REG(spsr[KVM_SPSR_EL1])},
        {"esr_el1", SYS_REG(3, 0, 5, 2, 0)}, {"far_el1", SYS_REG(3, 0, 6, 0, 0)}, {"vbar_el1", SYS_REG(3, 0, 12, 0, 0)},
        {"sctlr_el1", SYS_REG(3, 0, 1, 0, 0)}, {"tcr_el1", SYS_REG(3, 0, 2, 0, 2)}, {"ttbr0_el1", SYS_REG(3, 0, 2, 0, 0)},
        {"ttbr1_el1", SYS_REG(3, 0, 2, 0, 1)}, {"mair_el1", SYS_REG(3, 0, 10, 2, 0)}, {"cpacr_el1", SYS_REG(3, 0, 1, 0, 2)},
        {"tpidr_el1", SYS_REG(3, 0, 13, 0, 4)}, {"cntv_ctl", SYS_REG(3, 3, 14, 3, 1)}, {"midr_el1", SYS_REG(3, 0, 0, 0, 0)},
    };
    for (size_t k = 0; k < sizeof named / sizeof named[0]; k++)
        fprintf(stderr, "%s\"%s\":\"0x%llx\"", k ? "," : "", named[k].name, (unsigned long long)get_reg(fd, named[k].id));
    for (int r = 0; r < 31; r++)
        fprintf(stderr, ",\"x%d\":\"0x%llx\"", r, (unsigned long long)get_reg(fd, CORE_REG(regs.regs[r])));
}

/* Guest memory around addresses taken from the registers, translated through the guest's own stage-1
 * tables (identity when SCTLR_EL1.M is clear). Code addresses show 32 bytes before and after; data
 * addresses (stack, saved-state candidates) show 0x140 bytes from the address. */
static void dump_mem(int fd) {
    static const struct { const char *name; uint64_t id; int code; } where[] = {
        {"pc", CORE_REG(regs.pc), 1}, {"elr_el1", CORE_REG(elr_el1), 1}, {"x30", CORE_REG(regs.regs[30]), 1},
        {"sp_el1", CORE_REG(sp_el1), 0}, {"sp_el0", CORE_REG(regs.sp), 0}, {"far_el1", SYS_REG(3, 0, 6, 0, 0), 0},
        {"x0", CORE_REG(regs.regs[0]), 0}, {"x19", CORE_REG(regs.regs[19]), 0}, {"x21", CORE_REG(regs.regs[21]), 0},
        {"x29", CORE_REG(regs.regs[29]), 0},
    };
    uint64_t sctlr = get_reg(fd, SYS_REG(3, 0, 1, 0, 0)), tcr = get_reg(fd, SYS_REG(3, 0, 2, 0, 2));
    uint64_t ttbr0 = get_reg(fd, SYS_REG(3, 0, 2, 0, 0)), ttbr1 = get_reg(fd, SYS_REG(3, 0, 2, 0, 1));
    for (size_t k = 0; k < sizeof where / sizeof where[0]; k++) {
        uint64_t va = get_reg(fd, where[k].id);
        uint64_t start = where[k].code ? (va & ~0xfull) - 32 : va & ~0xfull;
        unsigned len = where[k].code ? 80 : 0x140;
        fprintf(stderr, "%s\"%s\":{\"va\":\"0x%llx\",\"from\":\"0x%llx\"", k ? "," : "", where[k].name, (unsigned long long)va,
                (unsigned long long)start);
        uint64_t pa = 0;
        int fault = (sctlr & 1) ? vmm_walk(g.ram, VMM_RAM_BASE, g.layout.ram_size, tcr, ttbr0, ttbr1, start, &pa) : (pa = start, 0);
        fprintf(stderr, ",\"walk\":%d,\"pa\":\"0x%llx\",\"bytes\":\"", fault, (unsigned long long)pa);
        for (unsigned i = 0; !fault && i < len; i++) {
            uint64_t a = start + i, p = 0;
            int f = (sctlr & 1) ? vmm_walk(g.ram, VMM_RAM_BASE, g.layout.ram_size, tcr, ttbr0, ttbr1, a, &p) : (p = a, 0);
            if (f || p < VMM_RAM_BASE || p >= VMM_RAM_BASE + g.layout.ram_size) break;
            fprintf(stderr, "%02x", g.ram[p - VMM_RAM_BASE]);
        }
        fprintf(stderr, "\"}");
    }
}

static void gic_attr(uint32_t group, uint64_t attr, void *addr, const char *what) {
    struct kvm_device_attr a = {.group = group, .attr = attr, .addr = (uint64_t)(uintptr_t)addr};
    if (ioctl(g.gic, KVM_SET_DEVICE_ATTR, &a) < 0) die(what);
}

int main(int argc, char **argv) {
    const char *image_path = NULL, *initrd_path = NULL, *params = "", *console_path = NULL, *pin = NULL;
    unsigned long mem_mib = 1024, timeout = 60, cpus = 1, scfb_w = 0, scfb_h = 0, port = 5824;
    int input = 0;
    for (int i = 1; i < argc; i += 2) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!strcmp(a, "--input")) { input = 1; i--; continue; }
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        if (!strcmp(a, "--image")) image_path = v;
        else if (!strcmp(a, "--initrd")) initrd_path = v;
        else if (!strcmp(a, "--mem")) mem_mib = strtoul(v, NULL, 0);
        else if (!strcmp(a, "--cpus")) cpus = strtoul(v, NULL, 0);
        else if (!strcmp(a, "--params")) params = v;
        else if (!strcmp(a, "--timeout")) timeout = strtoul(v, NULL, 0);
        else if (!strcmp(a, "--console")) console_path = v;
        else if (!strcmp(a, "--pin")) pin = v;
        else if (!strcmp(a, "--scfb")) { char *x; scfb_w = strtoul(v, &x, 10); scfb_h = *x == 'x' ? strtoul(x + 1, NULL, 10) : 0; }
        else if (!strcmp(a, "--display-port")) port = strtoul(v, NULL, 0);
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!image_path || !timeout || timeout > 3600) { fprintf(stderr, "need --image and 1..3600 s --timeout\n"); return 2; }
    setvbuf(stdout, NULL, _IOLBF, 0);

    size_t image_len = 0, initrd_len = 0;
    uint8_t *image = read_file(image_path, &image_len), *initrd = initrd_path ? read_file(initrd_path, &initrd_len) : NULL;
    g.layout = (struct vmm_layout){.ram_size = (uint64_t)mem_mib << 20, .cpus = (uint32_t)cpus,
                                   .image_size = vmm_image_extent(image, image_len), .initrd_size = initrd_len, .bootargs = params,
                                   .scfb_w = (uint32_t)scfb_w, .scfb_h = (uint32_t)scfb_h, .virtio_input = input};
    if (!g.layout.image_size) { errno = EINVAL; die("not an arm64 Image"); }
    if ((scfb_w || scfb_h) && (!scfb_w || !scfb_h)) { errno = EINVAL; die("--scfb needs WxH"); }
    if (!port || port > 65535) { errno = EINVAL; die("--display-port"); }
    if (vmm_plan(&g.layout)) { errno = EINVAL; die("layout does not fit"); }
    static char bootargs[1024];
    int blen = snprintf(bootargs, sizeof bootargs, "%s", params);
    if (g.layout.scfb_size)
        blen += snprintf(bootargs + blen, sizeof bootargs - (size_t)blen, "%sscfb.addr=0x%llx scfb.size=0x%llx scfb.w=%u scfb.h=%u", blen ? " " : "",
                         (unsigned long long)g.layout.scfb_addr, (unsigned long long)g.layout.scfb_size, g.layout.scfb_w, g.layout.scfb_h);
    if (input) blen += snprintf(bootargs + blen, sizeof bootargs - (size_t)blen, "%svirtio_input=1", blen ? " " : "");
    if (blen < 0 || (size_t)blen >= sizeof bootargs) { errno = E2BIG; die("bootargs"); }
    g.layout.bootargs = bootargs;
    g.display_port = (uint16_t)port;
    static uint8_t fdt[64 << 10];
    size_t fdt_len = vmm_build_fdt(&g.layout, fdt, sizeof fdt);
    if (!fdt_len) { errno = EINVAL; die("fdt"); }

    if ((g.kvm = open("/dev/kvm", O_RDWR | O_CLOEXEC)) < 0) die("open /dev/kvm");
    if ((g.vm = ioctl(g.kvm, KVM_CREATE_VM, 0)) < 0) die("KVM_CREATE_VM");
    g.ram = mmap(NULL, g.layout.ram_size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (g.ram == MAP_FAILED) die("mmap ram");
    struct kvm_userspace_memory_region region = {.slot = 0, .guest_phys_addr = VMM_RAM_BASE, .memory_size = g.layout.ram_size,
                                                 .userspace_addr = (uint64_t)(uintptr_t)g.ram};
    if (ioctl(g.vm, KVM_SET_USER_MEMORY_REGION, &region) < 0) die("KVM_SET_USER_MEMORY_REGION");
    memcpy(g.ram + (g.layout.image_addr - VMM_RAM_BASE), image, image_len);
    if (initrd_len) memcpy(g.ram + (g.layout.initrd_addr - VMM_RAM_BASE), initrd, initrd_len);
    memcpy(g.ram + (g.layout.fdt_addr - VMM_RAM_BASE), fdt, fdt_len);

    struct kvm_create_device dev = {.type = KVM_DEV_TYPE_ARM_VGIC_V3};
    if (ioctl(g.vm, KVM_CREATE_DEVICE, &dev) < 0) die("KVM_CREATE_DEVICE vgic-v3");
    g.gic = (int)dev.fd;
    uint64_t gicd = VMM_GICD_BASE, gicr = g.layout.gicr_base;
    gic_attr(KVM_DEV_ARM_VGIC_GRP_ADDR, KVM_VGIC_V3_ADDR_TYPE_DIST, &gicd, "vgic dist");
    gic_attr(KVM_DEV_ARM_VGIC_GRP_ADDR, KVM_VGIC_V3_ADDR_TYPE_REDIST, &gicr, "vgic redist");

    if ((g.run_size = ioctl(g.kvm, KVM_GET_VCPU_MMAP_SIZE, 0)) <= 0) die("KVM_GET_VCPU_MMAP_SIZE");
    struct kvm_vcpu_init init;
    memset(&init, 0, sizeof init);
    if (ioctl(g.vm, KVM_ARM_PREFERRED_TARGET, &init) < 0) die("KVM_ARM_PREFERRED_TARGET");
    for (uint32_t i = 0; i < g.layout.cpus; i++) {
        struct vcpu *v = &g.vcpus[i];
        v->index = (int)i;
        v->host_cpu = -1;
        if ((v->fd = ioctl(g.vm, KVM_CREATE_VCPU, i)) < 0) die("KVM_CREATE_VCPU");
        v->run = mmap(NULL, (size_t)g.run_size, PROT_READ | PROT_WRITE, MAP_SHARED, v->fd, 0);
        if (v->run == MAP_FAILED) die("mmap kvm_run");
        struct kvm_vcpu_init vi = init;
        vi.features[0] |= 1u << KVM_ARM_VCPU_PSCI_0_2;
        if (i) vi.features[0] |= 1u << KVM_ARM_VCPU_POWER_OFF;
        if (ioctl(v->fd, KVM_ARM_VCPU_INIT, &vi) < 0) die("KVM_ARM_VCPU_INIT");
    }
    gic_attr(KVM_DEV_ARM_VGIC_GRP_CTRL, KVM_DEV_ARM_VGIC_CTRL_INIT, NULL, "vgic init");
    set_reg(g.vcpus[0].fd, CORE_REG(regs.pc), g.layout.image_addr, "set pc");
    set_reg(g.vcpus[0].fd, CORE_REG(regs.regs[0]), g.layout.fdt_addr, "set x0");
    if (pin) {
        const char *p = pin;
        for (uint32_t i = 0; i < g.layout.cpus && *p; i++) {
            g.vcpus[i].host_cpu = atoi(p);
            while (*p && *p != ',') p++;
            if (*p == ',') p++;
        }
    }

    vmm_uart_reset(&g.uart);
    vmm_rtc_reset(&g.rtc);
    g.vram = (struct vio_ram){.host = g.ram, .base = VMM_RAM_BASE, .size = g.layout.ram_size};
    if (input) {
        vin_init(&g.input, &g.vram, g.layout.scfb_w ? g.layout.scfb_w : 1125, g.layout.scfb_h ? g.layout.scfb_h : 2436);
        g.input.dev.set_irq = input_irq;
        g.input_on = 1;
    }
    if (console_path && !(g.console = fopen(console_path, "w"))) die("open console log");
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_kick;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGUSR1, &sa, NULL) < 0) die("sigaction");
    fprintf(stderr, "{\"s24vmm\":\"start\",\"ram\":%llu,\"cpus\":%u,\"image\":[%llu,%llu],\"initrd\":[%llu,%llu],\"fdt\":[%llu,%zu],\"gicr\":%llu,\"params\":\"%s\"}\n",
            (unsigned long long)g.layout.ram_size, g.layout.cpus, (unsigned long long)g.layout.image_addr, (unsigned long long)g.layout.image_size,
            (unsigned long long)g.layout.initrd_addr, (unsigned long long)initrd_len, (unsigned long long)g.layout.fdt_addr, fdt_len,
            (unsigned long long)g.layout.gicr_base, g.layout.bootargs);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
    if (g.layout.scfb_size || input) {
        if (pthread_create(&g.display_thread, NULL, display_main, NULL)) die("pthread_create display");
        g.display_on = 1;
    }
    for (uint32_t i = 0; i < g.layout.cpus; i++) {
        pthread_mutex_lock(&g.kick_lock);
        g.vcpus[i].running = 1;
        int failed = pthread_create(&g.vcpus[i].thread, NULL, vcpu_main, &g.vcpus[i]);
        if (failed) g.vcpus[i].running = 0;
        pthread_mutex_unlock(&g.kick_lock);
        if (failed) die("pthread_create");
    }
    for (unsigned long waited = 0; !atomic_load(&g.stop); waited++) {
        if (waited >= timeout * 100) {
            set_cause("timeout");
            break;
        }
        usleep(10000);
    }
    /* Kick until every vCPU thread has left KVM_RUN; a signal can land just before a thread re-enters. */
    for (int round = 0; round < 500; round++) {
        int left = 0;
        kick_all();
        pthread_mutex_lock(&g.kick_lock);
        for (uint32_t i = 0; i < g.layout.cpus; i++) left += g.vcpus[i].running;
        pthread_mutex_unlock(&g.kick_lock);
        if (!left) break;
        usleep(10000);
    }
    for (uint32_t i = 0; i < g.layout.cpus; i++) pthread_join(g.vcpus[i].thread, NULL);
    if (g.display_on) pthread_join(g.display_thread, NULL);
    clock_gettime(CLOCK_MONOTONIC, &t1);
    fflush(stdout);
    if (g.console) fclose(g.console);

    fprintf(stderr, "{\"s24vmm\":\"end\",\"cause\":\"%s\",\"system_event\":%d,\"seconds\":%.3f,\"console_bytes\":%llu,\"unknown_mmio_total\":%llu,\"unknown_mmio\":[",
            g.cause, g.system_event, (double)(t1.tv_sec - t0.tv_sec) + (double)(t1.tv_nsec - t0.tv_nsec) / 1e9,
            (unsigned long long)g.console_bytes, (unsigned long long)g.unknown_total);
    for (unsigned i = 0; i < g.unknown_count; i++) fprintf(stderr, "%s%llu", i ? "," : "", (unsigned long long)g.unknown_addr[i]);
    fprintf(stderr, "],\"display\":{\"scfb\":[%llu,%llu,%u,%u],\"clients\":%llu,\"frames\":%llu,\"bytes\":%llu,\"first_frame_ms\":%llu,\"touches\":%llu},"
            "\"input\":{\"on\":%d,\"status\":%u,\"notifications\":%llu,\"interrupts\":%llu,\"delivered\":%llu,\"dropped\":%llu,\"bad_descriptors\":%llu}",
            (unsigned long long)g.layout.scfb_addr, (unsigned long long)g.layout.scfb_size, g.layout.scfb_w, g.layout.scfb_h,
            (unsigned long long)g.clients, (unsigned long long)g.frames_sent, (unsigned long long)g.frame_bytes, (unsigned long long)g.first_frame_ms,
            (unsigned long long)g.touches, g.input_on, g.input.dev.status, (unsigned long long)g.input.dev.notifications,
            (unsigned long long)g.input.dev.interrupts, (unsigned long long)g.input.delivered, (unsigned long long)g.input.dropped,
            (unsigned long long)g.input.dev.bad_descriptors);
    fprintf(stderr, ",\"vcpus\":[");
    for (uint32_t i = 0; i < g.layout.cpus; i++) {
        struct vcpu *v = &g.vcpus[i];
        fprintf(stderr, "%s{\"exits\":%llu,\"mmio\":%llu,\"last_reason\":%d,\"pc\":%llu,\"regs\":{", i ? "," : "", (unsigned long long)v->exits,
                (unsigned long long)v->mmio, v->last_reason, (unsigned long long)get_reg(v->fd, CORE_REG(regs.pc)));
        dump_regs(v->fd);
        fprintf(stderr, "},\"memory\":{");
        dump_mem(v->fd);
        fprintf(stderr, "}}");
    }
    fprintf(stderr, "]}\n");
    return strcmp(g.cause, "psci-system-off") ? 1 : 0;
}
