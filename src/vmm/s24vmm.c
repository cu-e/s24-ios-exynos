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
 */
#define _GNU_SOURCE
#include <errno.h>
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

static void gic_attr(uint32_t group, uint64_t attr, void *addr, const char *what) {
    struct kvm_device_attr a = {.group = group, .attr = attr, .addr = (uint64_t)(uintptr_t)addr};
    if (ioctl(g.gic, KVM_SET_DEVICE_ATTR, &a) < 0) die(what);
}

int main(int argc, char **argv) {
    const char *image_path = NULL, *initrd_path = NULL, *params = "", *console_path = NULL, *pin = NULL;
    unsigned long mem_mib = 1024, timeout = 60, cpus = 1;
    for (int i = 1; i < argc; i += 2) {
        const char *a = argv[i], *v = i + 1 < argc ? argv[i + 1] : NULL;
        if (!v) { fprintf(stderr, "missing value for %s\n", a); return 2; }
        if (!strcmp(a, "--image")) image_path = v;
        else if (!strcmp(a, "--initrd")) initrd_path = v;
        else if (!strcmp(a, "--mem")) mem_mib = strtoul(v, NULL, 0);
        else if (!strcmp(a, "--cpus")) cpus = strtoul(v, NULL, 0);
        else if (!strcmp(a, "--params")) params = v;
        else if (!strcmp(a, "--timeout")) timeout = strtoul(v, NULL, 0);
        else if (!strcmp(a, "--console")) console_path = v;
        else if (!strcmp(a, "--pin")) pin = v;
        else { fprintf(stderr, "unknown option %s\n", a); return 2; }
    }
    if (!image_path || !timeout || timeout > 3600) { fprintf(stderr, "need --image and 1..3600 s --timeout\n"); return 2; }
    setvbuf(stdout, NULL, _IOLBF, 0);

    size_t image_len = 0, initrd_len = 0;
    uint8_t *image = read_file(image_path, &image_len), *initrd = initrd_path ? read_file(initrd_path, &initrd_len) : NULL;
    g.layout = (struct vmm_layout){.ram_size = (uint64_t)mem_mib << 20, .cpus = (uint32_t)cpus,
                                   .image_size = vmm_image_extent(image, image_len), .initrd_size = initrd_len, .bootargs = params};
    if (!g.layout.image_size) { errno = EINVAL; die("not an arm64 Image"); }
    if (vmm_plan(&g.layout)) { errno = EINVAL; die("layout does not fit"); }
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
    if (console_path && !(g.console = fopen(console_path, "w"))) die("open console log");
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_kick;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGUSR1, &sa, NULL) < 0) die("sigaction");
    fprintf(stderr, "{\"s24vmm\":\"start\",\"ram\":%llu,\"cpus\":%u,\"image\":[%llu,%llu],\"initrd\":[%llu,%llu],\"fdt\":[%llu,%zu],\"gicr\":%llu,\"params\":\"%s\"}\n",
            (unsigned long long)g.layout.ram_size, g.layout.cpus, (unsigned long long)g.layout.image_addr, (unsigned long long)g.layout.image_size,
            (unsigned long long)g.layout.initrd_addr, (unsigned long long)initrd_len, (unsigned long long)g.layout.fdt_addr, fdt_len,
            (unsigned long long)g.layout.gicr_base, params);

    struct timespec t0, t1;
    clock_gettime(CLOCK_MONOTONIC, &t0);
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
    clock_gettime(CLOCK_MONOTONIC, &t1);
    fflush(stdout);
    if (g.console) fclose(g.console);

    fprintf(stderr, "{\"s24vmm\":\"end\",\"cause\":\"%s\",\"system_event\":%d,\"seconds\":%.3f,\"console_bytes\":%llu,\"unknown_mmio_total\":%llu,\"unknown_mmio\":[",
            g.cause, g.system_event, (double)(t1.tv_sec - t0.tv_sec) + (double)(t1.tv_nsec - t0.tv_nsec) / 1e9,
            (unsigned long long)g.console_bytes, (unsigned long long)g.unknown_total);
    for (unsigned i = 0; i < g.unknown_count; i++) fprintf(stderr, "%s%llu", i ? "," : "", (unsigned long long)g.unknown_addr[i]);
    fprintf(stderr, "],\"vcpus\":[");
    for (uint32_t i = 0; i < g.layout.cpus; i++) {
        struct vcpu *v = &g.vcpus[i];
        fprintf(stderr, "%s{\"exits\":%llu,\"mmio\":%llu,\"last_reason\":%d,\"pc\":%llu}", i ? "," : "", (unsigned long long)v->exits,
                (unsigned long long)v->mmio, v->last_reason, (unsigned long long)get_reg(v->fd, CORE_REG(regs.pc)));
    }
    fprintf(stderr, "]}\n");
    return strcmp(g.cause, "psci-system-off") ? 1 : 0;
}
