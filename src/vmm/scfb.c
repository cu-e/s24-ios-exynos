#include "scfb.h"

#include <string.h>

static uint32_t ld32(const uint8_t *p) {
    return __atomic_load_n((const uint32_t *)(const void *)p, __ATOMIC_ACQUIRE);
}
static uint64_t ld64(const uint8_t *p) {
    return __atomic_load_n((const uint64_t *)(const void *)p, __ATOMIC_ACQUIRE);
}
static void st64(uint8_t *p, uint64_t v) {
    __atomic_store_n((uint64_t *)(void *)p, v, __ATOMIC_RELEASE);
}
static void put32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static void put64(uint8_t *p, uint64_t v) {
    put32(p, (uint32_t)v);
    put32(p + 4, (uint32_t)(v >> 32));
}
static uint32_t get32(const uint8_t *p) {
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

uint64_t scfb_region_size(uint32_t width, uint32_t height) {
    uint64_t bytes = SCFB_FB_OFFSET + (uint64_t)width * height * 4;
    return (bytes + (2ull << 20) - 1) & ~((2ull << 20) - 1);
}

enum scfb_result scfb_read(struct scfb_reader *r, uint8_t *h, uint64_t region_len, uint32_t expect_w, uint32_t expect_h,
                           int force, struct scfb_frame *out) {
    if (region_len < SCFB_FB_OFFSET || ld32(h) != SCFB_MAGIC) return SCFB_NOTHING; /* avfboot has not written it yet */
    uint32_t w = ld32(h + 8), hh = ld32(h + 12), stride = ld32(h + 16), format = ld32(h + 20), off = ld32(h + 24);
    uint32_t flags = ld32(h + 36);
    if (w != expect_w || hh != expect_h || stride != w * 4 || format != SCFB_FORMAT_XR24 || off != SCFB_FB_OFFSET ||
        off + (uint64_t)stride * hh > region_len || !(flags & SCFB_F_READY)) {
        r->invalid++;
        return SCFB_INVALID;
    }
    uint64_t seq = ld64(h + 48);
    int changed = !r->have_frame || seq != r->last_seq;
    if (!changed && !(flags & SCFB_F_POLL) && !force) return SCFB_NOTHING;

    st64(h + 96, 1); /* host_reading */
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    if (ld32(h + 44)) { /* the guest is drawing: come back later */
        st64(h + 96, 0);
        r->busy++;
        return SCFB_BUSY;
    }
    seq = ld64(h + 48);
    uint32_t x = 0, y = 0, cw = w, ch = hh;
    int damage_known = (flags & SCFB_F_DAMAGE) && r->have_frame && seq == r->last_seq + 1 && !force;
    if (damage_known) {
        uint32_t dx = ld32(h + 72), dy = ld32(h + 76), dw = ld32(h + 80), dh = ld32(h + 84);
        if (!dw || !dh) { /* exact damage and nothing changed */
            st64(h + 96, 0);
            r->last_seq = seq;
            return SCFB_NOTHING;
        }
        if (dx < w && dy < hh && dw <= w - dx && dh <= hh - dy) {
            x = dx; y = dy; cw = dw; ch = dh;
        }
    }
    if (cw == w && ch == hh) r->full_copies++;
    const uint8_t *src = h + off;
    for (uint32_t row = 0; row < ch; row++)
        memcpy(out->pixels + (uint64_t)row * cw * 4, src + (uint64_t)(y + row) * stride + (uint64_t)x * 4, (size_t)cw * 4);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    st64(h + 88, seq); /* host_seq: the last frame copied */
    st64(h + 96, 0);
    out->width = w; out->height = hh; out->x = x; out->y = y; out->w = cw; out->h = ch; out->seq = seq;
    r->last_seq = seq;
    r->have_frame = 1;
    r->frames++;
    return SCFB_FRAME;
}

void s24f_encode_header(uint8_t out[S24F_HEADER_BYTES], const struct scfb_frame *f) {
    memset(out, 0, S24F_HEADER_BYTES);
    put32(out + 0, S24F_MAGIC);
    put32(out + 4, 1);
    put32(out + 8, f->width);
    put32(out + 12, f->height);
    put64(out + 16, f->seq);
    put32(out + 24, f->x);
    put32(out + 28, f->y);
    put32(out + 32, f->w);
    put32(out + 36, f->h);
    put32(out + 40, SCFB_FORMAT_XR24);
    put32(out + 44, f->w * f->h * 4);
}

int s24t_decode(const uint8_t in[S24T_BYTES], struct s24t_touch *t) {
    if (get32(in) != S24T_MAGIC) return -1;
    t->slot = get32(in + 4);
    t->tracking_id = (int32_t)get32(in + 8);
    t->x = get32(in + 12);
    t->y = get32(in + 16);
    return t->slot < 10 && t->tracking_id >= -1 ? 0 : -1;
}
