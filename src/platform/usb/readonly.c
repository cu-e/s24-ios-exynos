#include "readonly.h"

struct request { uint64_t session, id, offset; uint32_t length; uint16_t op; };
static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t rd32(const uint8_t *p) {
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}
static uint64_t rd64(const uint8_t *p) { return (uint64_t)rd32(p) | ((uint64_t)rd32(p + 4) << 32); }
static void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
static void wr32(uint8_t *p, uint32_t v) { for (unsigned i = 0; i != 4; ++i) p[i] = (uint8_t)(v >> (8u * i)); }
static void wr64(uint8_t *p, uint64_t v) { for (unsigned i = 0; i != 8; ++i) p[i] = (uint8_t)(v >> (8u * i)); }
static void clear(uint8_t *p, size_t n) { for (size_t i = 0; i < n; ++i) p[i] = 0; }
static int geometry_valid(const struct s24r_geometry *g) {
    return g && g->block_bytes >= 512 && g->block_bytes <= 4096 &&
        (g->block_bytes & (g->block_bytes - 1)) == 0 && g->bytes != 0 &&
        g->bytes % g->block_bytes == 0 && g->max_transfer >= g->block_bytes &&
        g->max_transfer <= S24R_MAX_TRANSFER && g->max_transfer % g->block_bytes == 0;
}
static int range_valid(const struct s24r_geometry *g, uint64_t offset, uint32_t n) {
    return n != 0 && n <= g->max_transfer && n % g->block_bytes == 0 &&
        offset % g->block_bytes == 0 && offset <= g->bytes && n <= g->bytes - offset;
}
static enum s24r_result decode(const uint8_t *p, size_t bytes, struct request *r) {
    if (!p || bytes < S24R_HEADER_BYTES) return S24R_BAD_FRAME;
    if (p[0] != 'S' || p[1] != '2' || p[2] != '4' || p[3] != 'R' ||
        rd16(p + 4) != S24R_VERSION || rd32(p + 36) != 0) return S24R_BAD_FRAME;
    r->op = rd16(p + 6); r->session = rd64(p + 8); r->id = rd64(p + 16);
    r->offset = rd64(p + 24); r->length = rd32(p + 32);
    return S24R_OK;
}
static void encode(uint8_t *p, const struct request *r) {
    p[0] = 'S'; p[1] = '2'; p[2] = '4'; p[3] = 'R'; wr16(p + 4, S24R_VERSION);
    wr16(p + 6, r->op); wr64(p + 8, r->session); wr64(p + 16, r->id);
    wr64(p + 24, r->offset); wr32(p + 32, r->length); wr32(p + 36, 0);
}
enum s24r_result s24r_server_connect(struct s24r_server *s,
    const struct s24r_geometry *g, uint64_t session, s24r_read_fn read, void *context) {
    if (!s || !read) return S24R_BAD_ARGUMENT;
    if (!geometry_valid(g)) return S24R_BAD_GEOMETRY;
    if (s->connected || s->inflight) return S24R_BUSY;
    if (!session || session <= s->last_session) return S24R_STALE;
    s->geometry = *g; s->session = session; s->last_session = session;
    s->last_request = 0; s->read = read; s->context = context; s->connected = 1;
    return S24R_OK;
}
void s24r_server_disconnect(struct s24r_server *s) {
    if (s) s->connected = 0; /* inflight is released only by its returning owner */
}
enum s24r_result s24r_server_handle(struct s24r_server *s, const uint8_t *frame,
    size_t frame_bytes, uint8_t *output, size_t capacity, size_t *written) {
    struct request r; uint32_t actual = 0; int result;
    if (!written) return S24R_BAD_ARGUMENT;
    *written = 0;
    if (!s || !output) return S24R_BAD_ARGUMENT;
    if (!s->connected) return S24R_DISCONNECTED;
    if (s->inflight) return S24R_BUSY;
    if (frame_bytes != S24R_HEADER_BYTES || decode(frame, frame_bytes, &r) != S24R_OK) return S24R_BAD_FRAME;
    if (r.op != S24R_READ) return S24R_UNSUPPORTED_OPERATION;
    if (r.session != s->session || r.id == 0 || r.id <= s->last_request) return S24R_STALE;
    if (!range_valid(&s->geometry, r.offset, r.length)) return S24R_RANGE;
    if (capacity < S24R_HEADER_BYTES || r.length > capacity - S24R_HEADER_BYTES) return S24R_BUFFER_SMALL;
    s->last_request = r.id; s->inflight = 1;
    result = s->read(s->context, r.offset, output + S24R_HEADER_BYTES, r.length, &actual);
    s->inflight = 0;
    if (!s->connected || s->session != r.session) {
        clear(output, S24R_HEADER_BYTES + r.length); return S24R_DISCONNECTED;
    }
    if (result != 0 || actual != r.length) {
        clear(output, S24R_HEADER_BYTES + r.length); return S24R_BACKEND_ERROR;
    }
    r.op = S24R_REPLY; encode(output, &r); *written = S24R_HEADER_BYTES + r.length;
    return S24R_OK;
}
enum s24r_result s24r_client_connect(struct s24r_client *c,
    const struct s24r_geometry *g, uint64_t session) {
    if (!c) return S24R_BAD_ARGUMENT;
    if (!geometry_valid(g)) return S24R_BAD_GEOMETRY;
    if (c->connected || c->pending) return S24R_BUSY;
    if (!session || session <= c->last_session) return S24R_STALE;
    c->geometry = *g; c->session = session; c->last_session = session;
    c->next_request = 1; c->connected = 1; return S24R_OK;
}
void s24r_client_disconnect(struct s24r_client *c) {
    if (c) { c->connected = 0; c->pending = 0; c->pending_length = 0; }
}
enum s24r_result s24r_client_request(struct s24r_client *c, uint64_t lba,
    uint32_t blocks, uint8_t *output, size_t capacity) {
    struct request r;
    if (!c || !output) return S24R_BAD_ARGUMENT;
    if (!c->connected) return S24R_DISCONNECTED;
    if (c->pending) return S24R_BUSY;
    if (c->next_request == 0 || c->next_request == UINT64_MAX) return S24R_ID_EXHAUSTED;
    if (capacity < S24R_HEADER_BYTES) return S24R_BUFFER_SMALL;
    if (!blocks || lba > UINT64_MAX / c->geometry.block_bytes ||
        blocks > c->geometry.max_transfer / c->geometry.block_bytes) return S24R_RANGE;
    r.offset = lba * c->geometry.block_bytes; r.length = blocks * c->geometry.block_bytes;
    if (!range_valid(&c->geometry, r.offset, r.length)) return S24R_RANGE;
    r.op = S24R_READ; r.session = c->session; r.id = c->next_request++;
    encode(output, &r); c->pending_request = r.id; c->pending_offset = r.offset;
    c->pending_length = r.length; c->pending = 1; return S24R_OK;
}
enum s24r_result s24r_client_complete(struct s24r_client *c, const uint8_t *frame,
    size_t bytes, struct s24r_view *view) {
    struct request r;
    if (!view) return S24R_BAD_ARGUMENT;
    view->data = NULL; view->offset = 0; view->length = 0;
    if (!c) return S24R_BAD_ARGUMENT;
    if (!c->connected) return S24R_DISCONNECTED;
    if (!c->pending) return S24R_STALE;
    if (decode(frame, bytes, &r) != S24R_OK || r.op != S24R_REPLY ||
        r.session != c->session || r.id != c->pending_request ||
        r.offset != c->pending_offset || r.length != c->pending_length ||
        bytes != S24R_HEADER_BYTES + (size_t)r.length) {
        s24r_client_disconnect(c); return S24R_BAD_FRAME;
    }
    view->data = frame + S24R_HEADER_BYTES; view->offset = r.offset; view->length = r.length;
    c->pending = 0; c->pending_length = 0; return S24R_OK;
}
enum s24r_result s24_usb_dma_slice(const struct s24_usb_dma_window *w,
    uintptr_t cpu, size_t bytes, uint64_t *bus) {
    uint64_t offset, first, last, mask;
    if (!w || !bus || !bytes || !w->bytes || !w->address_bits || w->address_bits > 64) return S24R_BAD_ARGUMENT;
    if (w->bytes - 1 > UINTPTR_MAX - w->cpu_start || cpu < w->cpu_start) return S24R_RANGE;
    mask = w->address_bits == 64 ? UINT64_MAX : ((UINT64_C(1) << w->address_bits) - 1);
    if (w->bytes - 1 > UINT64_MAX - w->bus_start || w->bus_start + w->bytes - 1 > mask) return S24R_RANGE;
    offset = (uint64_t)(cpu - w->cpu_start);
    if (offset > w->bytes || bytes > w->bytes - offset || offset > UINT64_MAX - w->bus_start) return S24R_RANGE;
    first = w->bus_start + offset;
    if (bytes - 1 > UINT64_MAX - first) return S24R_RANGE;
    last = first + bytes - 1;
    if (last > mask) return S24R_RANGE;
    *bus = first; return S24R_OK;
}
