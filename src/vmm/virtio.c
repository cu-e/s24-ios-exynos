#include "virtio.h"

#include <string.h>

#define VIRTIO_MMIO_MAGIC 0x74726976u /* "virt" */
#define VIRTIO_VENDOR 0x4d4d5653u     /* "SVMM", s24vmm */
#define VIRTIO_F_VERSION_1 (1ull << 32)
#define VIRTQ_DESC_F_NEXT 1u
#define VIRTQ_DESC_F_WRITE 2u

#define EV_SYN 0x00
#define EV_KEY 0x01
#define EV_ABS 0x03
#define SYN_REPORT 0
#define BTN_TOUCH 0x14a
#define ABS_X 0x00
#define ABS_Y 0x01
#define ABS_MT_SLOT 0x2f
#define ABS_MT_POSITION_X 0x35
#define ABS_MT_POSITION_Y 0x36
#define ABS_MT_TRACKING_ID 0x39
#define INPUT_PROP_DIRECT 0x01

#define CFG_UNSET 0x00
#define CFG_ID_NAME 0x01
#define CFG_ID_SERIAL 0x02
#define CFG_ID_DEVIDS 0x03
#define CFG_PROP_BITS 0x10
#define CFG_EV_BITS 0x11
#define CFG_ABS_INFO 0x12

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t rd64(const uint8_t *p) { return rd32(p) | (uint64_t)rd32(p + 4) << 32; }
static void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void wr32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i)); }

void *vio_gpa(const struct vio_ram *ram, uint64_t gpa, uint64_t len) {
    if (gpa < ram->base || len > ram->size || gpa - ram->base > ram->size - len) return NULL;
    return ram->host + (gpa - ram->base);
}

static void set_line(struct vio_dev *d) {
    int level = d->int_status != 0;
    if (level != d->irq_level) {
        d->irq_level = level;
        if (level) d->interrupts++;
        if (d->set_irq) d->set_irq(d->irq_context, level);
    }
}

static void reset(struct vio_dev *d) {
    d->driver_features = 0;
    d->dev_feat_sel = d->drv_feat_sel = d->queue_sel = d->status = d->int_status = 0;
    memset(d->q, 0, sizeof d->q);
    if (d->ops && d->ops->reset) d->ops->reset(d);
    set_line(d);
}

void vio_init(struct vio_dev *d, uint32_t device_id, const struct vio_ops *ops, const struct vio_ram *ram) {
    memset(d, 0, sizeof *d);
    d->device_id = device_id;
    d->device_features = VIRTIO_F_VERSION_1;
    d->ops = ops;
    d->ram = ram;
}

static struct vio_queue *selected(struct vio_dev *d) {
    return d->queue_sel < VIO_QUEUES ? &d->q[d->queue_sel] : NULL;
}

uint32_t vio_mmio_read(struct vio_dev *d, uint64_t offset, unsigned len) {
    struct vio_queue *q = selected(d);
    if (offset >= 0x100) {
        uint32_t v = 0;
        for (unsigned i = 0; i < len && i < 4; i++) v |= (uint32_t)d->ops->cfg_read(d, (uint32_t)(offset - 0x100 + i)) << (8 * i);
        return v;
    }
    if (len != 4) return 0; /* the register block is 32-bit only */
    switch (offset) {
    case 0x000: return VIRTIO_MMIO_MAGIC;
    case 0x004: return 2;
    case 0x008: return d->device_id;
    case 0x00c: return VIRTIO_VENDOR;
    case 0x010: return d->dev_feat_sel < 2 ? (uint32_t)(d->device_features >> (32 * d->dev_feat_sel)) : 0;
    case 0x034: return q ? VIO_QUEUE_MAX : 0;
    case 0x044: return q ? q->ready : 0;
    case 0x060: return d->int_status;
    case 0x070: return d->status;
    case 0x0b0: case 0x0b4: return 0xffffffffu; /* no shared memory regions */
    case 0x0fc: return d->config_gen;
    default: return 0;
    }
}

void vio_mmio_write(struct vio_dev *d, uint64_t offset, uint32_t value, unsigned len) {
    struct vio_queue *q = selected(d);
    if (offset >= 0x100) {
        for (unsigned i = 0; i < len && i < 4; i++) d->ops->cfg_write(d, (uint32_t)(offset - 0x100 + i), (uint8_t)(value >> (8 * i)));
        return;
    }
    if (len != 4) return;
    switch (offset) {
    case 0x014: d->dev_feat_sel = value; break;
    case 0x020:
        if (d->drv_feat_sel < 2) {
            uint64_t mask = 0xffffffffull << (32 * d->drv_feat_sel);
            d->driver_features = (d->driver_features & ~mask) | ((uint64_t)value << (32 * d->drv_feat_sel) & d->device_features);
        }
        break;
    case 0x024: d->drv_feat_sel = value; break;
    case 0x030: d->queue_sel = value; break;
    case 0x038: if (q && !q->ready && value && value <= VIO_QUEUE_MAX && !(value & (value - 1))) q->num = value; break;
    case 0x044:
        if (q) {
            q->ready = value & 1;
            if (q->ready && !q->num) q->num = VIO_QUEUE_MAX;
        }
        break;
    case 0x050:
        d->notifications++;
        if (value < VIO_QUEUES && d->q[value].ready && d->ops->notify) d->ops->notify(d, value);
        break;
    case 0x064:
        d->int_status &= ~value;
        set_line(d);
        break;
    case 0x070:
        if (!value) reset(d);
        else d->status = value & 0xff;
        break;
    case 0x080: if (q && !q->ready) q->desc = (q->desc & ~0xffffffffull) | value; break;
    case 0x084: if (q && !q->ready) q->desc = (q->desc & 0xffffffffull) | (uint64_t)value << 32; break;
    case 0x090: if (q && !q->ready) q->avail = (q->avail & ~0xffffffffull) | value; break;
    case 0x094: if (q && !q->ready) q->avail = (q->avail & 0xffffffffull) | (uint64_t)value << 32; break;
    case 0x0a0: if (q && !q->ready) q->used = (q->used & ~0xffffffffull) | value; break;
    case 0x0a4: if (q && !q->ready) q->used = (q->used & 0xffffffffull) | (uint64_t)value << 32; break;
    default: break;
    }
}

void vio_signal_used(struct vio_dev *d) {
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    d->int_status |= 1;
    set_line(d);
}

int vio_pop(struct vio_dev *d, uint32_t qi, uint64_t *buf, uint32_t *len, uint16_t *flags) {
    if (qi >= VIO_QUEUES) return -1;
    struct vio_queue *q = &d->q[qi];
    if (!q->ready || !q->num) return -1;
    uint8_t *avail = vio_gpa(d->ram, q->avail, 4 + 2ull * q->num);
    if (!avail) { d->bad_descriptors++; return -1; }
    uint16_t idx = __atomic_load_n((uint16_t *)(void *)(avail + 2), __ATOMIC_ACQUIRE);
    if (q->last_avail == idx) return -1;
    uint16_t head = rd16(avail + 4 + 2 * (q->last_avail % q->num));
    q->last_avail++;
    uint8_t *desc = head < q->num ? vio_gpa(d->ram, q->desc + 16ull * head, 16) : NULL;
    if (!desc) { d->bad_descriptors++; return -1; }
    *buf = rd64(desc);
    *len = rd32(desc + 8);
    *flags = rd16(desc + 12);
    return head;
}

void vio_push_used(struct vio_dev *d, uint32_t qi, uint16_t head, uint32_t written) {
    struct vio_queue *q = &d->q[qi];
    uint8_t *used = vio_gpa(d->ram, q->used, 4 + 8ull * q->num);
    if (!used) { d->bad_descriptors++; return; }
    uint16_t idx = rd16(used + 2);
    uint8_t *entry = used + 4 + 8 * (idx % q->num);
    wr32(entry, head);
    wr32(entry + 4, written);
    __atomic_thread_fence(__ATOMIC_RELEASE);
    __atomic_store_n((uint16_t *)(void *)(used + 2), (uint16_t)(idx + 1), __ATOMIC_RELEASE);
}

/* ---- virtio-input multi-touch ---- */

static struct vio_input *input_of(struct vio_dev *d) {
    return (struct vio_input *)(void *)d;
}

/* Fills the 128-byte union for the current select/subsel; returns its size. */
static uint8_t input_union(const struct vio_input *in, uint8_t *u) {
    static const char name[] = "s24vmm multi-touch";
    memset(u, 0, 128);
    switch (in->select) {
    case CFG_ID_NAME:
        if (in->subsel) return 0;
        memcpy(u, name, sizeof name - 1);
        return sizeof name - 1;
    case CFG_ID_DEVIDS:
        if (in->subsel) return 0;
        wr16(u, 0x06); wr16(u + 2, 0x0001); wr16(u + 4, 0x0001); wr16(u + 6, 1); /* BUS_VIRTUAL */
        return 8;
    case CFG_PROP_BITS:
        if (in->subsel) return 0;
        u[0] = 1u << INPUT_PROP_DIRECT;
        return 1;
    case CFG_EV_BITS:
        if (in->subsel == EV_KEY) { u[BTN_TOUCH / 8] |= (uint8_t)(1u << (BTN_TOUCH % 8)); return BTN_TOUCH / 8 + 1; }
        if (in->subsel == EV_ABS) {
            static const uint8_t axes[] = {ABS_X, ABS_Y, ABS_MT_SLOT, ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_TRACKING_ID};
            for (size_t i = 0; i < sizeof axes; i++) u[axes[i] / 8] |= (uint8_t)(1u << (axes[i] % 8));
            return ABS_MT_TRACKING_ID / 8 + 1;
        }
        return 0;
    case CFG_ABS_INFO: {
        uint32_t max;
        switch (in->subsel) {
        case ABS_X: case ABS_MT_POSITION_X: max = in->width - 1; break;
        case ABS_Y: case ABS_MT_POSITION_Y: max = in->height - 1; break;
        case ABS_MT_SLOT: max = VIN_SLOTS - 1; break;
        case ABS_MT_TRACKING_ID: max = 0xffff; break;
        default: return 0;
        }
        wr32(u, 0);
        wr32(u + 4, max);
        return 20;
    }
    default:
        return 0;
    }
}

static uint8_t input_cfg_read(struct vio_dev *d, uint32_t offset) {
    struct vio_input *in = input_of(d);
    uint8_t u[128];
    uint8_t size = input_union(in, u);
    if (offset == 0) return in->select;
    if (offset == 1) return in->subsel;
    if (offset == 2) return size;
    if (offset >= 8 && offset < 8 + 128) return u[offset - 8];
    return 0;
}

static void input_cfg_write(struct vio_dev *d, uint32_t offset, uint8_t value) {
    struct vio_input *in = input_of(d);
    if (offset == 0) in->select = value;
    else if (offset == 1) in->subsel = value;
}

static void input_notify(struct vio_dev *d, uint32_t queue) {
    struct vio_input *in = input_of(d);
    if (queue == 0) {
        vin_flush(in);
        return;
    }
    /* statusq: LED and similar feedback the guest sends; accepted and discarded */
    uint64_t buf;
    uint32_t len;
    uint16_t flags;
    int head, any = 0;
    while ((head = vio_pop(d, 1, &buf, &len, &flags)) >= 0) {
        vio_push_used(d, 1, (uint16_t)head, 0);
        any = 1;
    }
    if (any) vio_signal_used(d);
}

static void input_reset(struct vio_dev *d) {
    struct vio_input *in = input_of(d);
    in->select = in->subsel = 0;
    in->pending_head = in->pending_count = 0;
}

static const struct vio_ops input_ops = {input_cfg_read, input_cfg_write, input_notify, input_reset};

void vin_init(struct vio_input *in, const struct vio_ram *ram, uint32_t width, uint32_t height) {
    memset(in, 0, sizeof *in);
    vio_init(&in->dev, VIO_DEVICE_INPUT, &input_ops, ram);
    in->width = width ? width : 1;
    in->height = height ? height : 1;
}

void vin_flush(struct vio_input *in) {
    uint64_t buf;
    uint32_t len;
    uint16_t flags;
    int head, wrote = 0;
    while (in->pending_count && (head = vio_pop(&in->dev, 0, &buf, &len, &flags)) >= 0) {
        uint8_t *dst = len >= 8 && (flags & VIRTQ_DESC_F_WRITE) ? vio_gpa(in->dev.ram, buf, 8) : NULL;
        if (!dst) {
            in->dev.bad_descriptors++;
            vio_push_used(&in->dev, 0, (uint16_t)head, 0);
            wrote = 1;
            continue;
        }
        const struct vin_event *e = &in->pending[in->pending_head];
        wr16(dst, e->type);
        wr16(dst + 2, e->code);
        wr32(dst + 4, e->value);
        vio_push_used(&in->dev, 0, (uint16_t)head, 8);
        in->pending_head = (in->pending_head + 1) % VIN_PENDING;
        in->pending_count--;
        in->delivered++;
        wrote = 1;
    }
    if (wrote) vio_signal_used(&in->dev);
}

unsigned vin_touch(struct vio_input *in, uint32_t slot, int32_t tracking_id, uint32_t x, uint32_t y, int any_down) {
    struct vin_event report[6];
    unsigned n = 0;
    if (slot >= VIN_SLOTS) return 0;
    if (x >= in->width) x = in->width - 1;
    if (y >= in->height) y = in->height - 1;
    report[n++] = (struct vin_event){EV_ABS, ABS_MT_SLOT, slot};
    report[n++] = (struct vin_event){EV_ABS, ABS_MT_TRACKING_ID, tracking_id < 0 ? 0xffffffffu : (uint32_t)tracking_id & 0xffff};
    if (tracking_id >= 0) {
        report[n++] = (struct vin_event){EV_ABS, ABS_MT_POSITION_X, x};
        report[n++] = (struct vin_event){EV_ABS, ABS_MT_POSITION_Y, y};
    }
    report[n++] = (struct vin_event){EV_KEY, BTN_TOUCH, any_down ? 1u : 0u};
    report[n++] = (struct vin_event){EV_SYN, SYN_REPORT, 0};
    if (VIN_PENDING - in->pending_count < n) {
        in->dropped += n; /* a whole report or nothing: never a half report */
        return n;
    }
    for (unsigned i = 0; i < n; i++) in->pending[(in->pending_head + in->pending_count + i) % VIN_PENDING] = report[i];
    in->pending_count += n;
    vin_flush(in);
    return 0;
}
