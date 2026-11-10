/* Host tests for the s24vmm virtio-mmio transport, split virtqueues, virtio-input events and the SCFB
 * reader. The guest side is played by this file following the virtio 1.2 and scion-avf patch 1200
 * protocols, written independently of the code under test. */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "scfb.h"
#include "virtio.h"

static int failures, checks;
#define CHECK(c) do { checks++; if (!(c)) { failures++; fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); } } while (0)

#define BASE 0x80000000ull
#define RAM_BYTES (1u << 20)
static uint8_t ram_bytes[RAM_BYTES];
static struct vio_ram ram = {ram_bytes, BASE, RAM_BYTES};
static int irq_level, irq_raises;
static void on_irq(void *c, int level) { (void)c; irq_level = level; irq_raises += level; }

static uint16_t g16(uint64_t gpa) { uint8_t *p = ram_bytes + (gpa - BASE); return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t g32(uint64_t gpa) { uint8_t *p = ram_bytes + (gpa - BASE); return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static void s16(uint64_t gpa, uint16_t v) { uint8_t *p = ram_bytes + (gpa - BASE); p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void s32(uint64_t gpa, uint32_t v) { uint8_t *p = ram_bytes + (gpa - BASE); for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i)); }
static void s64(uint64_t gpa, uint64_t v) { s32(gpa, (uint32_t)v); s32(gpa + 4, (uint32_t)(v >> 32)); }

/* Guest-side queue layout for queue qi: desc, avail, used and 8-byte buffers. */
struct gq { uint64_t desc, avail, used, bufs; uint32_t num; uint16_t avail_idx; };

static void guest_queue(struct vio_dev *d, uint32_t qi, struct gq *q, uint64_t at, uint32_t num) {
    q->num = num;
    q->desc = at;
    q->avail = at + 0x1000;
    q->used = at + 0x2000;
    q->bufs = at + 0x3000;
    q->avail_idx = 0;
    vio_mmio_write(d, 0x030, qi, 4);
    vio_mmio_write(d, 0x038, num, 4);
    vio_mmio_write(d, 0x080, (uint32_t)q->desc, 4);
    vio_mmio_write(d, 0x084, (uint32_t)(q->desc >> 32), 4);
    vio_mmio_write(d, 0x090, (uint32_t)q->avail, 4);
    vio_mmio_write(d, 0x094, (uint32_t)(q->avail >> 32), 4);
    vio_mmio_write(d, 0x0a0, (uint32_t)q->used, 4);
    vio_mmio_write(d, 0x0a4, (uint32_t)(q->used >> 32), 4);
    vio_mmio_write(d, 0x044, 1, 4);
}

static void guest_post(struct gq *q, uint16_t id, uint64_t addr, uint32_t len, uint16_t flags) {
    s64(q->desc + 16u * id, addr);
    s32(q->desc + 16u * id + 8, len);
    s16(q->desc + 16u * id + 12, flags);
    s16(q->desc + 16u * id + 14, 0);
    s16(q->avail + 4 + 2u * (q->avail_idx % q->num), id);
    q->avail_idx++;
    s16(q->avail + 2, q->avail_idx);
}

static void test_gpa(void) {
    CHECK(vio_gpa(&ram, BASE, RAM_BYTES) == ram_bytes);
    CHECK(vio_gpa(&ram, BASE + RAM_BYTES - 8, 8) != NULL);
    CHECK(vio_gpa(&ram, BASE + RAM_BYTES - 8, 9) == NULL);
    CHECK(vio_gpa(&ram, BASE - 1, 2) == NULL);
    CHECK(vio_gpa(&ram, BASE + 16, ~0ull) == NULL);
    CHECK(vio_gpa(&ram, ~0ull - 4, 8) == NULL);
}

static uint8_t cfg_byte(struct vio_dev *d, uint32_t off) { return (uint8_t)vio_mmio_read(d, 0x100 + off, 1); }

static void test_mmio_and_config(void) {
    static struct vio_input in;
    vin_init(&in, &ram, 1125, 2436);
    struct vio_dev *d = &in.dev;
    d->set_irq = on_irq;
    CHECK(vio_mmio_read(d, 0x000, 4) == 0x74726976u);
    CHECK(vio_mmio_read(d, 0x004, 4) == 2);
    CHECK(vio_mmio_read(d, 0x008, 4) == 18);
    CHECK(vio_mmio_read(d, 0x000, 2) == 0); /* registers are 32-bit only */
    vio_mmio_write(d, 0x014, 0, 4);
    CHECK(vio_mmio_read(d, 0x010, 4) == 0);
    vio_mmio_write(d, 0x014, 1, 4);
    CHECK(vio_mmio_read(d, 0x010, 4) == 1); /* VIRTIO_F_VERSION_1 is bit 32 */
    vio_mmio_write(d, 0x024, 1, 4);
    vio_mmio_write(d, 0x020, 0xffffffffu, 4);
    CHECK(d->driver_features == (1ull << 32)); /* only offered bits stick */
    vio_mmio_write(d, 0x030, 0, 4);
    CHECK(vio_mmio_read(d, 0x034, 4) == VIO_QUEUE_MAX);
    vio_mmio_write(d, 0x038, 12, 4); /* not a power of two: ignored */
    CHECK(d->q[0].num == 0);
    vio_mmio_write(d, 0x038, 16, 4);
    CHECK(d->q[0].num == 16);
    vio_mmio_write(d, 0x038, 128, 4); /* above the maximum: ignored */
    CHECK(d->q[0].num == 16);
    vio_mmio_write(d, 0x030, 5, 4);
    CHECK(vio_mmio_read(d, 0x034, 4) == 0); /* no such queue */

    /* configuration space */
    vio_mmio_write(d, 0x100, 0x01, 1); /* ID_NAME */
    vio_mmio_write(d, 0x101, 0, 1);
    uint8_t size = cfg_byte(d, 2);
    char name[64] = {0};
    for (unsigned i = 0; i < size && i < 63; i++) name[i] = (char)cfg_byte(d, 8 + i);
    CHECK(size == 18 && !strcmp(name, "s24vmm multi-touch"));
    vio_mmio_write(d, 0x100, 0x12, 1); /* ABS_INFO */
    vio_mmio_write(d, 0x101, 0x35, 1); /* ABS_MT_POSITION_X */
    CHECK(cfg_byte(d, 2) == 20 && vio_mmio_read(d, 0x108, 4) == 0 && vio_mmio_read(d, 0x10c, 4) == 1124);
    vio_mmio_write(d, 0x101, 0x36, 1);
    CHECK(vio_mmio_read(d, 0x10c, 4) == 2435);
    vio_mmio_write(d, 0x101, 0x01, 1);
    CHECK(vio_mmio_read(d, 0x10c, 4) == 2435);
    vio_mmio_write(d, 0x101, 0x2f, 1);
    CHECK(vio_mmio_read(d, 0x10c, 4) == VIN_SLOTS - 1);
    vio_mmio_write(d, 0x101, 0x07, 1); /* an axis the device does not have */
    CHECK(cfg_byte(d, 2) == 0);
    vio_mmio_write(d, 0x100, 0x11, 1); /* EV_BITS */
    vio_mmio_write(d, 0x101, 0x03, 1); /* EV_ABS */
    CHECK(cfg_byte(d, 2) == 8 && (cfg_byte(d, 8 + 0x35 / 8) & (1u << (0x35 % 8))) && (cfg_byte(d, 8 + 0x39 / 8) & (1u << (0x39 % 8))));
    vio_mmio_write(d, 0x101, 0x01, 1); /* EV_KEY */
    CHECK(cfg_byte(d, 2) == 0x14a / 8 + 1 && (cfg_byte(d, 8 + 0x14a / 8) & (1u << (0x14a % 8))));
    vio_mmio_write(d, 0x101, 0x02, 1); /* EV_REL: none */
    CHECK(cfg_byte(d, 2) == 0);
    vio_mmio_write(d, 0x100, 0x10, 1); /* PROP_BITS */
    vio_mmio_write(d, 0x101, 0, 1);
    CHECK(cfg_byte(d, 2) == 1 && cfg_byte(d, 8) == 2); /* INPUT_PROP_DIRECT */
    vio_mmio_write(d, 0x100, 0x7f, 1);
    CHECK(cfg_byte(d, 2) == 0);

    /* status and reset */
    vio_mmio_write(d, 0x070, 0x0f, 4);
    CHECK(vio_mmio_read(d, 0x070, 4) == 0x0f);
    d->int_status = 1;
    d->irq_level = 1;
    vio_mmio_write(d, 0x070, 0, 4);
    CHECK(vio_mmio_read(d, 0x070, 4) == 0 && d->q[0].num == 0 && d->int_status == 0 && irq_level == 0);
}

static void test_input_events(void) {
    static struct vio_input in;
    vin_init(&in, &ram, 100, 200);
    struct vio_dev *d = &in.dev;
    d->set_irq = on_irq;
    irq_level = irq_raises = 0;
    memset(ram_bytes, 0, RAM_BYTES);
    struct gq ev, st;
    guest_queue(d, 0, &ev, BASE + 0x10000, 8);
    guest_queue(d, 1, &st, BASE + 0x20000, 8);
    CHECK(vio_mmio_read(d, 0x044, 4) == 1);
    vio_mmio_write(d, 0x030, 0, 4);
    vio_mmio_write(d, 0x038, 4, 4); /* queue is live: size cannot change */
    CHECK(d->q[0].num == 8);
    for (uint16_t i = 0; i < 8; i++) guest_post(&ev, i, ev.bufs + 8u * i, 8, 2);
    vio_mmio_write(d, 0x050, 0, 4); /* notify, nothing pending */
    CHECK(irq_raises == 0);

    /* finger 0 down at (10, 20): slot, tracking id, x, y, BTN_TOUCH, SYN_REPORT */
    CHECK(vin_touch(&in, 0, 7, 10, 20, 1) == 0);
    CHECK(g16(ev.used + 2) == 6 && in.delivered == 6 && irq_level == 1 && irq_raises == 1);
    static const uint32_t want[6][3] = {{3, 0x2f, 0}, {3, 0x39, 7}, {3, 0x35, 10}, {3, 0x36, 20}, {1, 0x14a, 1}, {0, 0, 0}};
    for (int i = 0; i < 6; i++) {
        uint32_t id = g32(ev.used + 4 + 8u * i), len = g32(ev.used + 8 + 8u * i);
        uint64_t b = ev.bufs + 8u * id;
        CHECK(id == (uint32_t)i && len == 8);
        CHECK(g16(b) == want[i][0] && g16(b + 2) == want[i][1] && g32(b + 4) == want[i][2]);
    }
    CHECK(vio_mmio_read(d, 0x060, 4) == 1);
    vio_mmio_write(d, 0x064, 1, 4);
    CHECK(irq_level == 0 && vio_mmio_read(d, 0x060, 4) == 0);

    /* finger lifted: tracking id -1, no position; only two buffers left, so four events wait */
    CHECK(vin_touch(&in, 0, -1, 0, 0, 0) == 0);
    CHECK(in.delivered == 8 && in.pending_count == 2);
    CHECK(g32(ev.bufs + 8u * 7 + 4) == 0xffffffffu);
    for (uint16_t i = 0; i < 8; i++) guest_post(&ev, i, ev.bufs + 8u * i, 8, 2);
    vio_mmio_write(d, 0x050, 0, 4);
    CHECK(in.delivered == 10 && in.pending_count == 0);
    CHECK(g16(ev.bufs + 8u * 0) == 1 && g16(ev.bufs + 8u * 0 + 2) == 0x14a && g32(ev.bufs + 4) == 0); /* BTN_TOUCH up */
    CHECK(g16(ev.bufs + 8u * 1) == 0); /* SYN_REPORT */

    /* coordinates are clamped to the axis range; out-of-range slots are ignored */
    vin_touch(&in, 1, 3, 1000, 5000, 1);
    CHECK(g32(ev.bufs + 8u * 4 + 4) == 99 && g32(ev.bufs + 8u * 5 + 4) == 199);
    unsigned before = (unsigned)in.delivered;
    CHECK(vin_touch(&in, VIN_SLOTS, 1, 0, 0, 1) == 0 && in.delivered == before && in.pending_count == 0);

    /* a buffer the device may not write, or outside RAM, is returned empty and counted */
    guest_post(&ev, 0, ev.bufs, 8, 0);
    guest_post(&ev, 1, BASE + RAM_BYTES - 4, 8, 2);
    guest_post(&ev, 2, ev.bufs + 16, 8, 2);
    uint64_t bad = d->bad_descriptors;
    vin_touch(&in, 0, 9, 1, 1, 1);
    CHECK(d->bad_descriptors == bad + 2);

    /* overflow drops whole reports only */
    static struct vio_input full;
    vin_init(&full, &ram, 10, 10);
    unsigned dropped = 0;
    for (int i = 0; i < 100; i++) dropped += vin_touch(&full, 0, 1, 1, 1, 1);
    CHECK(full.pending_count == VIN_PENDING - VIN_PENDING % 6 && full.pending_count % 6 == 0 && dropped == full.dropped && dropped > 0);

    /* statusq buffers come back unused */
    guest_post(&st, 0, st.bufs, 8, 0);
    guest_post(&st, 1, st.bufs + 8, 8, 0);
    vio_mmio_write(d, 0x050, 1, 4);
    CHECK(g16(st.used + 2) == 2 && g32(st.used + 8) == 0);
    /* notify of an unready or unknown queue does nothing */
    uint64_t n = d->notifications;
    vio_mmio_write(d, 0x050, 7, 4);
    CHECK(d->notifications == n + 1);
}

/* ---- SCFB ---- */
#define W 64
#define H 48
static uint8_t region[0x10000 + W * H * 4];
static void hput32(unsigned off, uint32_t v) { memcpy(region + off, &v, 4); }
static void hput64(unsigned off, uint64_t v) { memcpy(region + off, &v, 8); }
static uint64_t hget64(unsigned off) { uint64_t v; memcpy(&v, region + off, 8); return v; }
static void header(uint32_t flags, uint64_t seq) {
    hput32(0, SCFB_MAGIC); hput32(4, 1); hput32(8, W); hput32(12, H); hput32(16, W * 4); hput32(20, SCFB_FORMAT_XR24);
    hput32(24, SCFB_FB_OFFSET); hput32(28, SCFB_FB_OFFSET); hput32(32, 1); hput32(36, flags); hput32(40, 0); hput32(44, 0);
    hput64(48, seq);
}
static void fill(uint32_t v) { for (int i = 0; i < W * H; i++) memcpy(region + 0x10000 + 4 * i, &v, 4); }
static void pixel(int x, int y, uint32_t v) { memcpy(region + 0x10000 + 4 * (y * W + x), &v, 4); }

static void test_scfb(void) {
    static uint8_t px[W * H * 4];
    struct scfb_reader r = {0};
    struct scfb_frame f = {.pixels = px};
    memset(region, 0, sizeof region);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_NOTHING); /* no magic yet */
    header(SCFB_F_READY | SCFB_F_POLL, 1);
    CHECK(scfb_read(&r, region, sizeof region, W + 1, H, 0, &f) == SCFB_INVALID);
    CHECK(scfb_read(&r, region, 0x8000, W, H, 0, &f) == SCFB_NOTHING);
    hput32(36, SCFB_F_POLL);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_INVALID); /* not READY */
    header(SCFB_F_READY | SCFB_F_POLL, 1);
    fill(0x11223344);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_FRAME && f.w == W && f.h == H && f.seq == 1);
    CHECK(!memcmp(px, region + 0x10000, sizeof px) && hget64(96) == 0 && hget64(88) == 1);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_FRAME); /* POLL copies again */
    header(SCFB_F_READY | SCFB_F_DAMAGE, 1);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_NOTHING); /* published, unchanged */
    /* one published frame with exact damage: only that rectangle */
    pixel(5, 6, 0xaabbccdd);
    pixel(7, 9, 0x01020304);
    hput32(72, 5); hput32(76, 6); hput32(80, 3); hput32(84, 4);
    hput64(48, 2);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_FRAME && f.x == 5 && f.y == 6 && f.w == 3 && f.h == 4);
    uint32_t a, b;
    memcpy(&a, px, 4);
    memcpy(&b, px + 4 * (3 * 3 + 2), 4);
    CHECK(a == 0xaabbccdd && b == 0x01020304);
    /* empty exact damage: nothing to send, but the frame is consumed */
    hput32(80, 0); hput32(84, 0);
    hput64(48, 3);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_NOTHING && r.last_seq == 3);
    /* two frames since the last copy: damage of the first is lost, so the whole frame */
    hput32(72, 1); hput32(76, 1); hput32(80, 1); hput32(84, 1);
    hput64(48, 5);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_FRAME && f.w == W && f.h == H);
    /* damage outside the frame: whole frame */
    hput32(72, 60); hput32(80, 10);
    hput64(48, 6);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_FRAME && f.w == W);
    /* a new viewer forces a whole frame */
    CHECK(scfb_read(&r, region, sizeof region, W, H, 1, &f) == SCFB_FRAME && f.w == W && f.h == H);
    /* the guest is drawing: back off and leave host_reading clear */
    hput32(44, 1);
    hput64(48, 7);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_BUSY && hget64(96) == 0 && r.busy == 1);
    hput32(44, 0);
    CHECK(scfb_read(&r, region, sizeof region, W, H, 0, &f) == SCFB_FRAME && f.seq == 7);
}

/* A guest thread follows patch 1200: wait for host_reading to clear, set drawing, re-check, draw a
 * uniform frame, publish. The host must never copy a frame that mixes two values. */
static int stop_guest; /* accessed only through __atomic builtins */
static void *guest(void *arg) {
    (void)arg;
    uint8_t *h = region;
    for (uint32_t v = 1; !__atomic_load_n(&stop_guest, __ATOMIC_ACQUIRE) && v < 4000; v++) {
        for (;;) {
            while (__atomic_load_n((uint64_t *)(void *)(h + 96), __ATOMIC_ACQUIRE)) { }
            __atomic_store_n((uint32_t *)(void *)(h + 44), 1, __ATOMIC_SEQ_CST);
            if (!__atomic_load_n((uint64_t *)(void *)(h + 96), __ATOMIC_SEQ_CST)) break;
            __atomic_store_n((uint32_t *)(void *)(h + 44), 0, __ATOMIC_SEQ_CST); /* both at once: the host goes first */
        }
        for (int i = 0; i < W * H; i++) __atomic_store_n((uint32_t *)(void *)(h + 0x10000 + 4 * i), v, __ATOMIC_RELAXED);
        __atomic_store_n((uint32_t *)(void *)(h + 72), 0, __ATOMIC_RELAXED);
        __atomic_store_n((uint32_t *)(void *)(h + 76), 0, __ATOMIC_RELAXED);
        __atomic_store_n((uint32_t *)(void *)(h + 80), W, __ATOMIC_RELAXED);
        __atomic_store_n((uint32_t *)(void *)(h + 84), H, __ATOMIC_RELAXED);
        __atomic_store_n((uint32_t *)(void *)(h + 44), 0, __ATOMIC_RELEASE);
        __atomic_fetch_add((uint64_t *)(void *)(h + 48), 1, __ATOMIC_RELEASE);
    }
    return NULL;
}

static void test_scfb_no_tearing(void) {
    static uint8_t px[W * H * 4];
    memset(region, 0, sizeof region);
    header(SCFB_F_READY | SCFB_F_DAMAGE, 1);
    struct scfb_reader r = {0};
    struct scfb_frame f = {.pixels = px};
    pthread_t t;
    __atomic_store_n(&stop_guest, 0, __ATOMIC_RELEASE);
    pthread_create(&t, NULL, guest, NULL);
    unsigned torn = 0, copies = 0;
    for (int i = 0; i < 200000 && copies < 3000; i++) {
        if (scfb_read(&r, region, sizeof region, W, H, 1, &f) != SCFB_FRAME) continue;
        copies++;
        uint32_t first, v;
        memcpy(&first, px, 4);
        for (uint32_t k = 1; k < f.w * f.h; k++) {
            memcpy(&v, px + 4 * k, 4);
            if (v != first) { torn++; break; }
        }
    }
    __atomic_store_n(&stop_guest, 1, __ATOMIC_RELEASE);
    pthread_join(t, NULL);
    CHECK(copies > 100);
    CHECK(torn == 0);
    printf("{\"seqlock_copies\":%u,\"torn\":%u,\"busy\":%llu}\n", copies, torn, (unsigned long long)r.busy);
}

static void test_protocol(void) {
    uint8_t hdr[S24F_HEADER_BYTES];
    struct scfb_frame f = {.width = 1125, .height = 2436, .x = 3, .y = 4, .w = 5, .h = 6, .seq = 0x123456789ull};
    s24f_encode_header(hdr, &f);
    uint32_t v;
    memcpy(&v, hdr, 4); CHECK(v == S24F_MAGIC);
    memcpy(&v, hdr + 8, 4); CHECK(v == 1125);
    memcpy(&v, hdr + 12, 4); CHECK(v == 2436);
    uint64_t seq; memcpy(&seq, hdr + 16, 8); CHECK(seq == 0x123456789ull);
    memcpy(&v, hdr + 32, 4); CHECK(v == 5);
    memcpy(&v, hdr + 44, 4); CHECK(v == 5 * 6 * 4);
    uint8_t m[S24T_BYTES];
    uint32_t fields[5] = {S24T_MAGIC, 2, 0xffffffffu, 100, 200};
    memcpy(m, fields, sizeof m);
    struct s24t_touch t;
    CHECK(s24t_decode(m, &t) == 0 && t.slot == 2 && t.tracking_id == -1 && t.x == 100 && t.y == 200);
    fields[1] = 10;
    memcpy(m, fields, sizeof m);
    CHECK(s24t_decode(m, &t) == -1);
    fields[1] = 0; fields[2] = (uint32_t)-2;
    memcpy(m, fields, sizeof m);
    CHECK(s24t_decode(m, &t) == -1);
    fields[0] = 0;
    memcpy(m, fields, sizeof m);
    CHECK(s24t_decode(m, &t) == -1);
    CHECK(scfb_region_size(1125, 2436) == 12ull << 20);
    CHECK(scfb_region_size(1, 1) == 2ull << 20);
}

int main(void) {
    test_gpa();
    test_mmio_and_config();
    test_input_events();
    test_scfb();
    test_scfb_no_tearing();
    test_protocol();
    printf("{\"checks\":%d,\"failures\":%d}\n", checks, failures);
    return failures ? 1 : 0;
}
