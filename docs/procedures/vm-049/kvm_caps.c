/* VM-049: open /dev/kvm, read KVM_GET_API_VERSION, KVM_GET_VCPU_MMAP_SIZE and a fixed list of
 * KVM_CHECK_EXTENSION answers on the system file descriptor. Creates no VM and no vCPU.
 * Output is one JSON object on stdout. */
#include <errno.h>
#include <fcntl.h>
#include <linux/kvm.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

/* Android common kernels define this vendor capability for protected VMs (pKVM). */
#define S24_KVM_CAP_ARM_PROTECTED_VM 0xffbadab1

struct cap { const char *name; unsigned long id; };

#define CAP(x) { #x, x }
static const struct cap caps[] = {
    CAP(KVM_CAP_IRQCHIP), CAP(KVM_CAP_USER_MEMORY), CAP(KVM_CAP_NR_VCPUS), CAP(KVM_CAP_MAX_VCPUS),
    CAP(KVM_CAP_MAX_VCPU_ID), CAP(KVM_CAP_NR_MEMSLOTS), CAP(KVM_CAP_ONE_REG), CAP(KVM_CAP_DEVICE_CTRL),
    CAP(KVM_CAP_READONLY_MEM), CAP(KVM_CAP_IOEVENTFD), CAP(KVM_CAP_IRQFD), CAP(KVM_CAP_IRQ_ROUTING),
    CAP(KVM_CAP_SIGNAL_MSI), CAP(KVM_CAP_MSI_DEVID), CAP(KVM_CAP_COALESCED_MMIO), CAP(KVM_CAP_IMMEDIATE_EXIT),
    CAP(KVM_CAP_VCPU_EVENTS), CAP(KVM_CAP_ARM_PSCI), CAP(KVM_CAP_ARM_PSCI_0_2), CAP(KVM_CAP_ARM_EL1_32BIT),
    CAP(KVM_CAP_ARM_PMU_V3), CAP(KVM_CAP_ARM_VM_IPA_SIZE), CAP(KVM_CAP_ARM_SVE), CAP(KVM_CAP_ARM_PTRAUTH_ADDRESS),
    CAP(KVM_CAP_ARM_PTRAUTH_GENERIC), CAP(KVM_CAP_ARM_MTE), CAP(KVM_CAP_ARM_USER_IRQ), CAP(KVM_CAP_ARM_NISV_TO_USER),
    CAP(KVM_CAP_ARM_INJECT_SERROR_ESR), CAP(KVM_CAP_ARM_INJECT_EXT_DABT), CAP(KVM_CAP_ARM_SYSTEM_SUSPEND),
    CAP(KVM_CAP_ARM_SET_DEVICE_ADDR), CAP(KVM_CAP_ARM_IRQ_LINE_LAYOUT_2), CAP(KVM_CAP_SYSTEM_EVENT_DATA),
    CAP(KVM_CAP_VCPU_ATTRIBUTES), CAP(KVM_CAP_PMU_CAPABILITY),
    { "KVM_CAP_ARM_PROTECTED_VM(android)", S24_KVM_CAP_ARM_PROTECTED_VM },
};

int main(void) {
    int fd = open("/dev/kvm", O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        int saved = errno;
        printf("{\"opened\":false,\"errno\":%d,\"error\":\"%s\"}\n", saved, strerror(saved));
        return 2;
    }
    int version = ioctl(fd, KVM_GET_API_VERSION, 0);
    int version_errno = version < 0 ? errno : 0;
    int mmap_size = ioctl(fd, KVM_GET_VCPU_MMAP_SIZE, 0);
    int mmap_errno = mmap_size < 0 ? errno : 0;
    printf("{\"opened\":true,\"api_version\":%d,\"api_errno\":%d,\"vcpu_mmap_size\":%d,\"vcpu_mmap_errno\":%d,\"extensions\":{",
           version, version_errno, mmap_size, mmap_errno);
    for (size_t i = 0; i < sizeof caps / sizeof caps[0]; i++) {
        int value = ioctl(fd, KVM_CHECK_EXTENSION, caps[i].id);
        int saved = value < 0 ? errno : 0;
        printf("%s\"%s\":{\"id\":%lu,\"value\":%d,\"errno\":%d}", i ? "," : "", caps[i].name, caps[i].id, value, saved);
    }
    printf("}}\n");
    close(fd);
    return version == KVM_API_VERSION && mmap_size > 0 ? 0 : 3;
}
