/* VM-051: one bounded KVM guest on the S24. Creates a VM with a vGICv3, one vCPU and a 2 MiB
 * memslot, runs the few instructions of guest.S to a PSCI SYSTEM_OFF exit and prints one JSON
 * object. Bounds: an in-process 5 s alarm (immediate_exit) and an exit budget; the caller adds an
 * outer timeout. Usage: kvm_guest CPU   (the vCPU thread is pinned to that host CPU). */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <sched.h>
#include <signal.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

extern const unsigned char vm051_guest_start[], vm051_guest_end[];

#define RAM_BASE 0x80000000ull
#define RAM_SIZE (2u << 20)
#define REPORT 0x09000000ull
#define GICD 0x08000000ull
#define GICR 0x080a0000ull
#define EXIT_LOOP 10000u
#define LOOP_ITERATIONS 100000000ull
#define CORE_REG(x) (KVM_REG_ARM64 | KVM_REG_SIZE_U64 | KVM_REG_ARM_CORE | (offsetof(struct kvm_regs, x) / sizeof(uint32_t)))

static struct kvm_run *volatile g_run;
static volatile sig_atomic_t g_alarm;

static void on_alarm(int sig) {
    (void)sig;
    g_alarm = 1;
    if (g_run) g_run->immediate_exit = 1;
}

static uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static const char *g_step = "start";
static int g_errno;

#define CHECK(expr, name) do { g_step = name; if ((expr) < 0) { g_errno = errno; goto out; } } while (0)

static uint64_t native_loop(void) {
    uint64_t n = LOOP_ITERATIONS, start = now_ns();
    __asm__ volatile("1: subs %0, %0, #1\n b.ne 1b" : "+r"(n) :: "cc");
    return now_ns() - start;
}

int main(int argc, char **argv) {
    int cpu = argc > 1 ? atoi(argv[1]) : 0;
    int kvm = -1, vm = -1, gic = -1, vcpu = -1, ok = 0, exits = 0, ipa = -1;
    uint8_t *mem = MAP_FAILED;
    struct kvm_run *run = MAP_FAILED;
    long mmap_size = 0;
    char console[64] = {0};
    size_t console_len = 0;
    uint64_t psci = 0, el = 0, midr = 0, cntfrq = 0, mpidr = 0, ticks = 0;
    uint64_t t_first = 0, t_last = 0, t_compute = 0, t_end = 0, counter_exits = 0, native_ns[4] = {0}, other_mmio = 0, other_addr = 0;
    int cpu_before = -1, cpu_after = -1, event_type = -1, last_reason = -1;
    unsigned long long event_flags = 0;

    cpu_set_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    CHECK(sched_setaffinity(0, sizeof set, &set), "sched_setaffinity");
    cpu_before = sched_getcpu();
    for (int i = 0; i < 3; i++) native_ns[i] = native_loop();

    CHECK(kvm = open("/dev/kvm", O_RDWR | O_CLOEXEC), "open");
    CHECK(vm = ioctl(kvm, KVM_CREATE_VM, 0), "KVM_CREATE_VM");
    ipa = ioctl(vm, KVM_CHECK_EXTENSION, KVM_CAP_ARM_VM_IPA_SIZE);
    g_step = "mmap_ram";
    mem = mmap(NULL, RAM_SIZE, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
    if (mem == MAP_FAILED) { g_errno = errno; goto out; }
    memcpy(mem, vm051_guest_start, (size_t)(vm051_guest_end - vm051_guest_start));
    struct kvm_userspace_memory_region region = {.slot = 0, .guest_phys_addr = RAM_BASE, .memory_size = RAM_SIZE,
                                                 .userspace_addr = (uint64_t)(uintptr_t)mem};
    CHECK(ioctl(vm, KVM_SET_USER_MEMORY_REGION, &region), "KVM_SET_USER_MEMORY_REGION");

    struct kvm_create_device device = {.type = KVM_DEV_TYPE_ARM_VGIC_V3};
    CHECK(ioctl(vm, KVM_CREATE_DEVICE, &device), "KVM_CREATE_DEVICE(vgic-v3)");
    gic = (int)device.fd;
    uint64_t gicd = GICD, gicr = GICR;
    struct kvm_device_attr attr = {.group = KVM_DEV_ARM_VGIC_GRP_ADDR, .attr = KVM_VGIC_V3_ADDR_TYPE_DIST, .addr = (uint64_t)(uintptr_t)&gicd};
    CHECK(ioctl(gic, KVM_SET_DEVICE_ATTR, &attr), "vgic dist address");
    attr.attr = KVM_VGIC_V3_ADDR_TYPE_REDIST;
    attr.addr = (uint64_t)(uintptr_t)&gicr;
    CHECK(ioctl(gic, KVM_SET_DEVICE_ATTR, &attr), "vgic redist address");

    CHECK(vcpu = ioctl(vm, KVM_CREATE_VCPU, 0), "KVM_CREATE_VCPU");
    CHECK(mmap_size = ioctl(kvm, KVM_GET_VCPU_MMAP_SIZE, 0), "KVM_GET_VCPU_MMAP_SIZE");
    g_step = "mmap_run";
    run = mmap(NULL, (size_t)mmap_size, PROT_READ | PROT_WRITE, MAP_SHARED, vcpu, 0);
    if (run == MAP_FAILED) { g_errno = errno; goto out; }
    struct kvm_vcpu_init init;
    memset(&init, 0, sizeof init);
    CHECK(ioctl(vm, KVM_ARM_PREFERRED_TARGET, &init), "KVM_ARM_PREFERRED_TARGET");
    init.features[0] |= 1u << KVM_ARM_VCPU_PSCI_0_2;
    CHECK(ioctl(vcpu, KVM_ARM_VCPU_INIT, &init), "KVM_ARM_VCPU_INIT");
    struct kvm_device_attr ctrl = {.group = KVM_DEV_ARM_VGIC_GRP_CTRL, .attr = KVM_DEV_ARM_VGIC_CTRL_INIT};
    CHECK(ioctl(gic, KVM_SET_DEVICE_ATTR, &ctrl), "vgic init");
    uint64_t pc = RAM_BASE;
    struct kvm_one_reg reg = {.id = CORE_REG(regs.pc), .addr = (uint64_t)(uintptr_t)&pc};
    CHECK(ioctl(vcpu, KVM_SET_ONE_REG, &reg), "set pc");

    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = on_alarm;
    sigemptyset(&action.sa_mask);
    CHECK(sigaction(SIGALRM, &action, NULL), "sigaction");
    g_run = run;
    alarm(5);
    g_step = "KVM_RUN";
    for (exits = 0; exits < (int)EXIT_LOOP + 64; exits++) {
        if (ioctl(vcpu, KVM_RUN, 0) < 0) {
            g_errno = errno;
            g_step = g_alarm ? "alarm" : "KVM_RUN";
            goto out;
        }
        last_reason = (int)run->exit_reason;
        if (run->exit_reason == KVM_EXIT_MMIO && run->mmio.is_write) {
            uint64_t off = run->mmio.phys_addr - REPORT, value = 0;
            memcpy(&value, run->mmio.data, run->mmio.len <= 8 ? run->mmio.len : 8);
            if (off == 0 && console_len + 1 < sizeof console) console[console_len++] = (char)value;
            else if (off == 8) psci = value;
            else if (off == 16) el = value;
            else if (off == 24) midr = value;
            else if (off == 32) cntfrq = value;
            else if (off == 40) mpidr = value;
            else if (off == 0x40) { if (!counter_exits++) t_first = now_ns(); t_last = now_ns(); }
            else if (off == 0x48) t_compute = now_ns();
            else if (off == 48) { ticks = value; t_end = now_ns(); }
            else { other_mmio++; other_addr = run->mmio.phys_addr; }
            continue;
        }
        if (run->exit_reason == KVM_EXIT_SYSTEM_EVENT) {
            event_type = (int)run->system_event.type;
            event_flags = (unsigned long long)run->system_event.flags;
            ok = event_type == KVM_SYSTEM_EVENT_SHUTDOWN;
            g_step = "system_event";
            break;
        }
        g_step = "unexpected_exit";
        break;
    }
    if (!ok && !strcmp(g_step, "KVM_RUN")) g_step = "exit_budget";
out:
    alarm(0);
    native_ns[3] = native_loop();
    cpu_after = sched_getcpu();
    printf("{\"ok\":%s,\"step\":\"%s\",\"errno\":%d,\"error\":\"%s\",\"cpu_requested\":%d,\"cpu_before\":%d,\"cpu_after\":%d,"
           "\"vm_ipa_size\":%d,\"exits\":%d,\"last_exit_reason\":%d,\"system_event_type\":%d,\"system_event_flags\":%llu,"
           "\"console\":\"%s\",\"psci_version\":%llu,\"current_el\":%llu,\"midr\":%llu,\"cntfrq\":%llu,\"mpidr\":%llu,"
           "\"mmio_counter_exits\":%llu,\"mmio_exit_span_ns\":%llu,\"guest_loop_ticks\":%llu,\"guest_loop_wall_ns\":%llu,"
           "\"native_loop_ns\":[%llu,%llu,%llu,%llu],\"loop_iterations\":%llu,\"alarm_fired\":%d,\"other_mmio\":%llu,\"other_mmio_addr\":%llu}\n",
           ok ? "true" : "false", g_step, g_errno, g_errno ? strerror(g_errno) : "", cpu, cpu_before, cpu_after, ipa, exits, last_reason,
           event_type, event_flags, console, (unsigned long long)psci, (unsigned long long)el, (unsigned long long)midr,
           (unsigned long long)cntfrq, (unsigned long long)mpidr, (unsigned long long)counter_exits,
           (unsigned long long)(t_last - t_first), (unsigned long long)ticks, (unsigned long long)(t_end - t_compute),
           (unsigned long long)native_ns[0], (unsigned long long)native_ns[1], (unsigned long long)native_ns[2], (unsigned long long)native_ns[3],
           LOOP_ITERATIONS, (int)g_alarm, (unsigned long long)other_mmio, (unsigned long long)other_addr);
    g_run = NULL;
    if (run != MAP_FAILED) munmap(run, (size_t)mmap_size);
    if (vcpu >= 0) close(vcpu);
    if (gic >= 0) close(gic);
    if (vm >= 0) close(vm);
    if (kvm >= 0) close(kvm);
    if (mem != MAP_FAILED) munmap(mem, RAM_SIZE);
    return ok ? 0 : 3;
}
