#include "machine.h"

#include <string.h>

#include "fdt.h"

#define GIC_PHANDLE 1u
#define IRQ_TYPE_SPI 0u
#define IRQ_TYPE_PPI 1u
#define IRQ_LEVEL_HIGH 4u
#define PPI_FLAGS 0xf08u /* all CPUs, level low, as crosvm and QEMU describe the timer */

static uint64_t align_up(uint64_t v, uint64_t a) {
    return (v + a - 1) & ~(a - 1);
}

uint64_t vmm_image_extent(const uint8_t *image, size_t len) {
    if (len < 64 || memcmp(image + 56, "ARM\x64", 4)) return 0;
    uint64_t image_size = 0;
    for (int i = 7; i >= 0; i--) image_size = image_size << 8 | image[16 + i];
    return image_size > len ? image_size : (uint64_t)len;
}

int vmm_plan(struct vmm_layout *l) {
    if (!l->cpus || l->cpus > VMM_MAX_CPUS || !l->image_size || l->ram_size < (64ull << 20) ||
        l->ram_size % (2ull << 20) || l->ram_size > (64ull << 30))
        return -1;
    l->image_addr = VMM_RAM_BASE;
    l->initrd_addr = align_up(l->image_addr + l->image_size, VMM_INITRD_ALIGN);
    l->fdt_addr = VMM_RAM_BASE + l->ram_size - VMM_FDT_MAX;
    l->gicr_size = VMM_GICR_STRIDE * l->cpus;
    l->gicr_base = VMM_GICD_BASE - l->gicr_size;
    if (l->initrd_addr + l->initrd_size > l->fdt_addr || l->initrd_addr + l->initrd_size < l->initrd_addr) return -1;
    return 0;
}

static void reg2(struct fdt_w *w, uint64_t base, uint64_t size) {
    uint32_t cells[4] = {(uint32_t)(base >> 32), (uint32_t)base, (uint32_t)(size >> 32), (uint32_t)size};
    fdt_prop_cells(w, "reg", cells, 4);
}

size_t vmm_build_fdt(const struct vmm_layout *l, uint8_t *out, size_t out_len) {
    static struct fdt_w w; /* 18 KiB: keep it off the vCPU thread stacks */
    char name[32];
    fdt_w_init(&w);
    fdt_begin_node(&w, "");
    fdt_prop_str(&w, "compatible", "linux,dummy-virt");
    fdt_prop_u32(&w, "#address-cells", 2);
    fdt_prop_u32(&w, "#size-cells", 2);
    fdt_prop_u32(&w, "interrupt-parent", GIC_PHANDLE);

    fdt_begin_node(&w, "chosen");
    if (l->bootargs) fdt_prop_str(&w, "bootargs", l->bootargs);
    if (l->initrd_size) {
        fdt_prop_u64(&w, "linux,initrd-start", l->initrd_addr);
        fdt_prop_u64(&w, "linux,initrd-end", l->initrd_addr + l->initrd_size);
    }
    fdt_prop_str(&w, "stdout-path", "/uart@3f8");
    fdt_end_node(&w);

    memcpy(name, "memory@80000000", 16);
    fdt_begin_node(&w, name);
    fdt_prop_str(&w, "device_type", "memory");
    reg2(&w, VMM_RAM_BASE, l->ram_size);
    fdt_end_node(&w);

    fdt_begin_node(&w, "cpus");
    fdt_prop_u32(&w, "#address-cells", 1);
    fdt_prop_u32(&w, "#size-cells", 0);
    for (uint32_t i = 0; i < l->cpus; i++) {
        memcpy(name, "cpu@", 4);
        name[4] = (char)('0' + i % 10);
        name[5] = 0;
        fdt_begin_node(&w, name);
        fdt_prop_str(&w, "device_type", "cpu");
        fdt_prop_str(&w, "compatible", "arm,arm-v8");
        fdt_prop_str(&w, "enable-method", "psci");
        fdt_prop_u32(&w, "reg", i); /* KVM's default MPIDR for vCPU i < 16 */
        fdt_end_node(&w);
    }
    fdt_end_node(&w);

    fdt_begin_node(&w, "psci");
    static const char psci_compat[] = "arm,psci-1.0\0arm,psci-0.2";
    fdt_prop(&w, "compatible", psci_compat, sizeof psci_compat);
    fdt_prop_str(&w, "method", "hvc");
    fdt_end_node(&w);

    fdt_begin_node(&w, "intc@3fff0000");
    fdt_prop_str(&w, "compatible", "arm,gic-v3");
    fdt_prop_u32(&w, "#interrupt-cells", 3);
    fdt_prop_empty(&w, "interrupt-controller");
    uint32_t gic_reg[8] = {(uint32_t)(VMM_GICD_BASE >> 32), (uint32_t)VMM_GICD_BASE, 0, (uint32_t)VMM_GICD_SIZE,
                           (uint32_t)(l->gicr_base >> 32), (uint32_t)l->gicr_base, 0, (uint32_t)l->gicr_size};
    fdt_prop_cells(&w, "reg", gic_reg, 8);
    fdt_prop_u32(&w, "phandle", GIC_PHANDLE);
    fdt_end_node(&w);

    fdt_begin_node(&w, "timer");
    fdt_prop_str(&w, "compatible", "arm,armv8-timer");
    uint32_t timer[12] = {IRQ_TYPE_PPI, 13, PPI_FLAGS, IRQ_TYPE_PPI, 14, PPI_FLAGS,
                          IRQ_TYPE_PPI, 11, PPI_FLAGS, IRQ_TYPE_PPI, 10, PPI_FLAGS};
    fdt_prop_cells(&w, "interrupts", timer, 12);
    fdt_prop_empty(&w, "always-on");
    fdt_end_node(&w);

    fdt_begin_node(&w, "uart@3f8");
    fdt_prop_str(&w, "compatible", "ns16550a");
    reg2(&w, VMM_UART_BASE, VMM_UART_SIZE);
    fdt_prop_u32(&w, "clock-frequency", 1843200);
    uint32_t uart_irq[3] = {IRQ_TYPE_SPI, VMM_UART_SPI, IRQ_LEVEL_HIGH};
    fdt_prop_cells(&w, "interrupts", uart_irq, 3);
    fdt_end_node(&w);

    fdt_begin_node(&w, "rtc@2000");
    static const char rtc_compat[] = "arm,pl031\0arm,primecell";
    fdt_prop(&w, "compatible", rtc_compat, sizeof rtc_compat);
    reg2(&w, VMM_RTC_BASE, VMM_RTC_SIZE);
    uint32_t rtc_irq[3] = {IRQ_TYPE_SPI, VMM_RTC_SPI, IRQ_LEVEL_HIGH};
    fdt_prop_cells(&w, "interrupts", rtc_irq, 3);
    fdt_end_node(&w);

    fdt_end_node(&w);
    return fdt_finish(&w, out, out_len);
}

void vmm_uart_reset(struct vmm_uart *u) {
    memset(u, 0, sizeof *u);
    u->lcr = 0x03;
}

uint8_t vmm_uart_read(struct vmm_uart *u, uint64_t offset) {
    int dlab = (u->lcr & 0x80) != 0;
    switch (offset) {
    case 0:
        if (dlab) return u->dll;
        if (!u->rx_count) return 0;
        {
            uint8_t b = u->rx[u->rx_head];
            u->rx_head = (u->rx_head + 1) % sizeof u->rx;
            u->rx_count--;
            return b;
        }
    case 1: return dlab ? u->dlm : u->ier;
    case 2: return (u->rx_count && (u->ier & 1)) ? 0xc4 : 0xc1; /* FIFOs on; RX data or none pending */
    case 3: return u->lcr;
    case 4: return u->mcr;
    case 5: return (uint8_t)(0x60 | (u->rx_count ? 1 : 0)); /* THR empty, transmitter empty, DR */
    case 6: return 0xb0;                                     /* DCD, DSR, CTS */
    case 7: return u->scr;
    default: return 0;
    }
}

int vmm_uart_write(struct vmm_uart *u, uint64_t offset, uint8_t value, uint8_t *tx) {
    int dlab = (u->lcr & 0x80) != 0;
    switch (offset) {
    case 0:
        if (dlab) { u->dll = value; return 0; }
        *tx = value;
        return 1;
    case 1:
        if (dlab) u->dlm = value;
        else u->ier = value & 0x0f;
        return 0;
    case 3: u->lcr = value; return 0;
    case 4: u->mcr = value & 0x1f; return 0;
    case 7: u->scr = value; return 0;
    default: return 0; /* FCR and read-only registers */
    }
}

int vmm_uart_push_rx(struct vmm_uart *u, uint8_t byte) {
    if (u->rx_count == sizeof u->rx) return -1;
    u->rx[(u->rx_head + u->rx_count) % sizeof u->rx] = byte;
    u->rx_count++;
    return 0;
}

void vmm_rtc_reset(struct vmm_rtc *r) {
    memset(r, 0, sizeof *r);
    r->control = 1;
}

uint32_t vmm_rtc_read(const struct vmm_rtc *r, uint64_t offset, int64_t host_seconds) {
    static const uint8_t id[8] = {0x31, 0x10, 0x04, 0x00, 0x0d, 0xf0, 0x05, 0xb1};
    if (offset >= 0xfe0 && offset <= 0xffc && !(offset & 3)) return id[(offset - 0xfe0) / 4];
    switch (offset) {
    case 0x000: return (uint32_t)(host_seconds + r->offset);
    case 0x004: return r->match;
    case 0x008: return (uint32_t)(host_seconds + r->offset);
    case 0x00c: return r->control;
    case 0x010: return r->mask;
    default: return 0; /* RIS, MIS: the match interrupt is never raised */
    }
}

void vmm_rtc_write(struct vmm_rtc *r, uint64_t offset, uint32_t value, int64_t host_seconds) {
    switch (offset) {
    case 0x004: r->match = value; break;
    case 0x008: r->offset = (int64_t)value - host_seconds; break;
    case 0x00c: r->control = 1; break; /* writing 0 cannot stop a PL031 */
    case 0x010: r->mask = value & 1; break;
    default: break;
    }
}
