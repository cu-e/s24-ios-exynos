/* s24vmm machine description: memory map, FDT and the two emulated devices (8250, PL031).
 * Pure functions with no KVM dependency so they can be tested on the host.
 * The map follows crosvm on arm64, which avfboot (scion-avf avf/shim) was written for. */
#ifndef S24VMM_MACHINE_H
#define S24VMM_MACHINE_H

#include <stddef.h>
#include <stdint.h>

#define VMM_RAM_BASE 0x80000000ull
#define VMM_UART_BASE 0x3f8ull
#define VMM_UART_SIZE 0x8ull
#define VMM_RTC_BASE 0x2000ull
#define VMM_RTC_SIZE 0x1000ull
#define VMM_GICD_BASE 0x3fff0000ull
#define VMM_GICD_SIZE 0x10000ull
#define VMM_GICR_STRIDE 0x20000ull
#define VMM_FDT_MAX 0x200000ull
#define VMM_INITRD_ALIGN 0x1000000ull
#define VMM_MAX_CPUS 10
#define VMM_UART_SPI 0u
#define VMM_RTC_SPI 1u

struct vmm_layout {
    uint64_t ram_size;
    uint32_t cpus;
    uint64_t image_size;   /* bytes the Image occupies in RAM, including its .bss */
    uint64_t initrd_size;
    const char *bootargs;
    /* Outputs of vmm_plan(). */
    uint64_t image_addr, initrd_addr, fdt_addr, gicr_base, gicr_size;
};

/* Places Image, initrd and FDT. Returns 0, or -1 if they do not fit or arguments are invalid. */
int vmm_plan(struct vmm_layout *l);
/* Writes the FDT for a planned layout. Returns the blob size, or 0 on error. */
size_t vmm_build_fdt(const struct vmm_layout *l, uint8_t *out, size_t out_len);
/* Reads the arm64 Image header: returns the size to reserve (max of file and image_size), 0 if invalid. */
uint64_t vmm_image_extent(const uint8_t *image, size_t len);

/* 8250/16550 subset: polled transmit, a small receive queue, LSR/IIR/MSR answers a driver expects. */
struct vmm_uart {
    uint8_t ier, lcr, mcr, scr, dll, dlm;
    uint8_t rx[64];
    unsigned rx_head, rx_count;
};
void vmm_uart_reset(struct vmm_uart *u);
/* Returns the register value for a read at offset. */
uint8_t vmm_uart_read(struct vmm_uart *u, uint64_t offset);
/* Returns 1 and stores the byte in *tx when the write is a transmitted character. */
int vmm_uart_write(struct vmm_uart *u, uint64_t offset, uint8_t value, uint8_t *tx);
int vmm_uart_push_rx(struct vmm_uart *u, uint8_t byte);

/* PL031 real-time clock: the counter is host time plus an offset the guest can load. */
struct vmm_rtc {
    int64_t offset;
    uint32_t match, control, mask;
};
void vmm_rtc_reset(struct vmm_rtc *r);
uint32_t vmm_rtc_read(const struct vmm_rtc *r, uint64_t offset, int64_t host_seconds);
void vmm_rtc_write(struct vmm_rtc *r, uint64_t offset, uint32_t value, int64_t host_seconds);

#endif
