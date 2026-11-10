/* virtio-mmio v2 transport (virtio 1.2 section 4.2), split virtqueues (2.7) and a virtio-input
 * multi-touch device (5.8) for s24vmm. Pure code over a guest-RAM window; the caller supplies the
 * interrupt line and serializes calls with its own lock. All guest memory is little endian. */
#ifndef S24VMM_VIRTIO_H
#define S24VMM_VIRTIO_H

#include <stddef.h>
#include <stdint.h>

#define VIO_MMIO_BASE 0x0a000000ull
#define VIO_MMIO_SLOT 0x200ull
#define VIO_MMIO_SPI_BASE 16u /* slot n raises SPI 16 + n (INTID 48 + n), as QEMU virt */
#define VIO_QUEUES 2
#define VIO_QUEUE_MAX 64
#define VIO_DEVICE_INPUT 18u

struct vio_ram {
    uint8_t *host;
    uint64_t base, size;
};
/* Host pointer for [gpa, gpa+len) inside guest RAM, or NULL. */
void *vio_gpa(const struct vio_ram *ram, uint64_t gpa, uint64_t len);

struct vio_queue {
    uint32_t num, ready;
    uint64_t desc, avail, used;
    uint16_t last_avail;
};

struct vio_dev;
struct vio_ops {
    uint8_t (*cfg_read)(struct vio_dev *d, uint32_t offset);
    void (*cfg_write)(struct vio_dev *d, uint32_t offset, uint8_t value);
    void (*notify)(struct vio_dev *d, uint32_t queue);
    void (*reset)(struct vio_dev *d);
};

struct vio_dev {
    uint32_t device_id;
    uint64_t device_features, driver_features;
    uint32_t dev_feat_sel, drv_feat_sel, queue_sel, status, int_status, config_gen;
    struct vio_queue q[VIO_QUEUES];
    const struct vio_ops *ops;
    const struct vio_ram *ram;
    void (*set_irq)(void *context, int level);
    void *irq_context;
    int irq_level;
    uint64_t notifications, interrupts, bad_descriptors;
};

void vio_init(struct vio_dev *d, uint32_t device_id, const struct vio_ops *ops, const struct vio_ram *ram);
uint32_t vio_mmio_read(struct vio_dev *d, uint64_t offset, unsigned len);
void vio_mmio_write(struct vio_dev *d, uint64_t offset, uint32_t value, unsigned len);
/* Raise the used-buffer interrupt (status bit 0) and the line. */
void vio_signal_used(struct vio_dev *d);

/* Takes the next available chain of queue q; returns its head or -1. buf, len and flags describe the first
 * descriptor only (the devices here use single-descriptor buffers). */
int vio_pop(struct vio_dev *d, uint32_t q, uint64_t *buf, uint32_t *len, uint16_t *flags);
void vio_push_used(struct vio_dev *d, uint32_t q, uint16_t head, uint32_t written);

/* virtio-input multi-touch. */
#define VIN_SLOTS 10
#define VIN_PENDING 256
struct vin_event {
    uint16_t type, code;
    uint32_t value;
};
struct vio_input {
    struct vio_dev dev;
    uint8_t select, subsel;
    uint32_t width, height;
    struct vin_event pending[VIN_PENDING];
    unsigned pending_head, pending_count;
    uint64_t delivered, dropped;
};
void vin_init(struct vio_input *in, const struct vio_ram *ram, uint32_t width, uint32_t height);
/* Queues one contact change as an MT-B report (slot, tracking id, x, y, BTN_TOUCH, SYN_REPORT) and
 * delivers what fits into posted eventq buffers. tracking_id < 0 lifts the finger. Returns events dropped. */
unsigned vin_touch(struct vio_input *in, uint32_t slot, int32_t tracking_id, uint32_t x, uint32_t y, int any_down);
/* Moves pending events into eventq buffers; signals the guest when any were written. */
void vin_flush(struct vio_input *in);

#endif
