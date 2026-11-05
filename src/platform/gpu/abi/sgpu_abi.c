/* Independently authored bounds/encoding checks. No allocation or device I/O. */
#include "sgpu_abi.h"

uint16_t sgpu_get16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8)); }
uint32_t sgpu_get32(const uint8_t *p) { return (uint32_t)sgpu_get16(p) | ((uint32_t)sgpu_get16(p + 2) << 16); }
uint64_t sgpu_get64(const uint8_t *p) { return (uint64_t)sgpu_get32(p) | ((uint64_t)sgpu_get32(p + 4) << 32); }
void sgpu_put16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8); }
void sgpu_put32(uint8_t *p, uint32_t v) { sgpu_put16(p, (uint16_t)v); sgpu_put16(p + 2, (uint16_t)(v >> 16)); }
void sgpu_put64(uint8_t *p, uint64_t v) { sgpu_put32(p, (uint32_t)v); sgpu_put32(p + 4, (uint32_t)(v >> 32)); }

static int range_ok(uint64_t offset, uint64_t bytes) { return bytes && offset <= UINT64_MAX - bytes; }
static int page_range(uint64_t offset, uint64_t bytes) { return range_ok(offset, bytes) && !(offset % SGPU_GPU_PAGE) && !(bytes % SGPU_GPU_PAGE); }
static int access_ok(uint32_t access, uint32_t allowed) { return access && !(access & ~allowed); }
static uint32_t validate_submit(const uint8_t *p, size_t n)
{
    uint32_t ni, nu, nd, i, j;
    size_t use_base, dep_base;
    if (n < 24) return SGPU_BAD_SIZE;
    ni = sgpu_get32(p + 8); nu = sgpu_get32(p + 12); nd = sgpu_get32(p + 16);
    if (!ni || ni > SGPU_MAX_IBS || !nu || nu > SGPU_MAX_USES || nd > SGPU_MAX_DEPS) return SGPU_LIMIT;
    /* Counts are bounded before size arithmetic. Canonical contiguous order,
     * no caller offsets, aliases, trailing bytes or implicit padding accepted. */
    use_base = 24 + 32 * (size_t)ni; dep_base = use_base + 16 * (size_t)nu;
    if (n != dep_base + 8 * (size_t)nd) return SGPU_BAD_SIZE;
    if (!sgpu_get64(p) || sgpu_get32(p + 20)) return SGPU_BAD_FIELD;
    for (i = 0; i < nu; ++i) {
        const uint8_t *use = p + use_base + 16 * i;
        if (!sgpu_get64(use) || !access_ok(sgpu_get32(use + 8), SGPU_READ | SGPU_WRITE) || sgpu_get32(use + 12)) return SGPU_BAD_FIELD;
        for (j = 0; j < i; ++j) if (sgpu_get64(use) == sgpu_get64(p + use_base + 16 * j)) return SGPU_BAD_FIELD;
    }
    for (i = 0; i < ni; ++i) {
        const uint8_t *ib = p + 24 + 32 * i;
        uint64_t offset = sgpu_get64(ib + 8), bytes = sgpu_get64(ib + 16);
        int found = 0;
        if (!sgpu_get64(ib) || !range_ok(offset, bytes) || offset % 4 || bytes % 4 || bytes > SGPU_MAX_IB_BYTES || sgpu_get32(ib + 24) || sgpu_get32(ib + 28)) return SGPU_BAD_FIELD;
        for (j = 0; j < nu; ++j) {
            const uint8_t *use = p + use_base + 16 * j;
            if (sgpu_get64(ib) == sgpu_get64(use) && (sgpu_get32(use + 8) & SGPU_READ)) found = 1;
        }
        if (!found) return SGPU_BAD_FIELD;
    }
    for (i = 0; i < nd; ++i) {
        uint64_t fence = sgpu_get64(p + dep_base + 8 * i);
        if (!fence) return SGPU_BAD_FIELD;
        for (j = 0; j < i; ++j) if (fence == sgpu_get64(p + dep_base + 8 * j)) return SGPU_BAD_FIELD;
    }
    return SGPU_OK;
}

uint32_t sgpu_validate_request(const void *wire, size_t bytes, struct sgpu_request_view *view)
{
    const uint8_t *p = (const uint8_t *)wire;
    uint32_t op, status = SGPU_OK;
    size_t expected = 0, n;
    if (!view) return SGPU_BAD_FIELD;
    view->payload = NULL; view->opcode = 0; view->payload_bytes = 0; view->request_id = 0;
    if (!p || bytes < 32 || bytes > SGPU_MAX_MESSAGE) return SGPU_BAD_SIZE;
    if (sgpu_get32(p) != SGPU_MAGIC || sgpu_get32(p + 12) != bytes || !sgpu_get64(p + 16) || sgpu_get32(p + 24) || sgpu_get32(p + 28)) return SGPU_BAD_HEADER;
    if (sgpu_get16(p + 4) != SGPU_ABI_MAJOR || sgpu_get16(p + 6) != SGPU_ABI_MINOR) return SGPU_BAD_VERSION;
    op = sgpu_get32(p + 8); p += 32; n = bytes - 32;
    switch (op) {
    case SGPU_QUERY: expected = 16; break;
    case SGPU_ALLOC: expected = 24; break;
    case SGPU_FREE: case SGPU_CONTEXT_DESTROY: case SGPU_CPU_UNMAP: expected = 8; break;
    case SGPU_CONTEXT_CREATE: case SGPU_WAIT: expected = 16; break;
    case SGPU_CPU_MAP: case SGPU_CACHE: expected = 32; break;
    case SGPU_GPU_MAP: expected = 48; break;
    case SGPU_GPU_UNMAP: expected = 24; break;
    case SGPU_STOP: expected = 0; break;
    case SGPU_SUBMIT: expected = n; break;
    default: return SGPU_UNSUPPORTED;
    }
    if (n != expected) return SGPU_BAD_SIZE;
    switch (op) {
    case SGPU_QUERY:
        if (sgpu_get16(p) > sgpu_get16(p + 2) || sgpu_get16(p + 4) > sgpu_get16(p + 6)) return SGPU_BAD_FIELD;
        if (sgpu_get16(p) > SGPU_ABI_MAJOR || sgpu_get16(p + 2) < SGPU_ABI_MAJOR || sgpu_get16(p + 4) > SGPU_ABI_MINOR) return SGPU_BAD_VERSION;
        break;
    case SGPU_ALLOC: {
        uint64_t size = sgpu_get64(p), align = sgpu_get64(p + 8);
        if (!size || size > SGPU_MAX_ALLOC_BYTES || align < SGPU_GPU_PAGE || align > SGPU_MAX_ALLOC_BYTES || (align & (align - 1)) || !access_ok(sgpu_get32(p + 16), 7) || sgpu_get32(p + 20)) return SGPU_BAD_FIELD;
        break;
    }
    case SGPU_FREE: case SGPU_CONTEXT_DESTROY: case SGPU_CPU_UNMAP:
        if (!sgpu_get64(p)) return SGPU_BAD_FIELD;
        break;
    case SGPU_CONTEXT_CREATE:
        if (sgpu_get32(p) > 1 || sgpu_get32(p + 4) || sgpu_get64(p + 8)) return SGPU_BAD_FIELD;
        break;
    case SGPU_CPU_MAP: case SGPU_CACHE:
        if (!sgpu_get64(p) || !range_ok(sgpu_get64(p + 8), sgpu_get64(p + 16)) || sgpu_get32(p + 28)) return SGPU_BAD_FIELD;
        if (op == SGPU_CPU_MAP && !access_ok(sgpu_get32(p + 24), SGPU_READ | SGPU_WRITE)) return SGPU_BAD_FIELD;
        if (op == SGPU_CACHE && sgpu_get32(p + 24) != SGPU_TO_GPU && sgpu_get32(p + 24) != SGPU_TO_CPU) return SGPU_BAD_FIELD;
        break;
    case SGPU_GPU_MAP:
        if (!sgpu_get64(p) || !sgpu_get64(p + 8) || !sgpu_get64(p + 16) || !page_range(sgpu_get64(p + 16), sgpu_get64(p + 32)) || !page_range(sgpu_get64(p + 24), sgpu_get64(p + 32)) || !access_ok(sgpu_get32(p + 40), 7) || sgpu_get32(p + 44)) return SGPU_BAD_FIELD;
        break;
    case SGPU_GPU_UNMAP:
        if (!sgpu_get64(p) || !sgpu_get64(p + 8) || !page_range(sgpu_get64(p + 8), sgpu_get64(p + 16))) return SGPU_BAD_FIELD;
        break;
    case SGPU_SUBMIT: status = validate_submit(p, n); break;
    case SGPU_WAIT:
        if (!sgpu_get64(p) || sgpu_get64(p + 8) > SGPU_MAX_WAIT_NS) return SGPU_BAD_FIELD;
        break;
    default: break;
    }
    if (status) return status;
    view->payload = p; view->opcode = op; view->payload_bytes = (uint32_t)n;
    view->request_id = sgpu_get64((const uint8_t *)wire + 16);
    return SGPU_OK;
}

static int response_ok(const struct sgpu_request_view *v, const struct sgpu_backend_result *r)
{
    uint32_t expected;
    if (r->status > SGPU_BAD_REPLY || r->bytes > sizeof(r->payload)) return 0;
    if (r->status != SGPU_OK) return r->bytes == 0;
    switch (v->opcode) {
    case SGPU_QUERY:
        expected = 88;
        if (r->bytes != expected || sgpu_get32(r->payload + 84)) return 0;
        /* Required features must be honored; no silent fallback to a weaker
         * implementation. Native profile/page/limit claims require GPU-007. */
        if ((sgpu_get64(v->payload + 8) & sgpu_get64(r->payload)) != sgpu_get64(v->payload + 8)) return 0;
        if (sgpu_get32(r->payload + 60) < 120 || sgpu_get32(r->payload + 60) > SGPU_MAX_MESSAGE || sgpu_get32(r->payload + 64) > SGPU_MAX_IBS || sgpu_get32(r->payload + 68) > SGPU_MAX_USES || sgpu_get32(r->payload + 72) > SGPU_MAX_DEPS || sgpu_get32(r->payload + 76) > SGPU_MAX_WAIT_NS / 1000000) return 0;
        if (sgpu_get32(r->payload + 80) > 1) return 0;
        if (!sgpu_get32(r->payload + 80)) {
            size_t i;
            for (i = 8; i < 60; ++i) if (r->payload[i]) return 0;
        } else {
            uint32_t hw = sgpu_get32(r->payload + 48), vm = sgpu_get32(r->payload + 52);
            uint64_t budget = sgpu_get64(r->payload + 16), alloc = sgpu_get64(r->payload + 24);
            uint64_t va = sgpu_get64(r->payload + 32), span = sgpu_get64(r->payload + 40);
            if ((sgpu_get64(r->payload) & SGPU_FEATURE_SYNTHETIC) || !sgpu_get64(r->payload + 8) || (hw != 4096 && hw != 16384) || (vm != 4096 && vm != 16384) || sgpu_get32(r->payload + 56) != SGPU_GPU_PAGE || !budget || !alloc || alloc > budget || alloc > SGPU_MAX_ALLOC_BYTES || !va || !page_range(va, span)) return 0;
        }
        break;
    case SGPU_ALLOC: case SGPU_CONTEXT_CREATE: case SGPU_CPU_MAP: case SGPU_SUBMIT:
        expected = 16;
        if (r->bytes != expected || !sgpu_get64(r->payload) || !sgpu_get64(r->payload + 8)) return 0;
        if (v->opcode == SGPU_ALLOC && sgpu_get64(r->payload + 8) < sgpu_get64(v->payload)) return 0;
        if (v->opcode == SGPU_CPU_MAP && sgpu_get64(r->payload + 8) < sgpu_get64(v->payload + 16)) return 0;
        break;
    case SGPU_WAIT:
        expected = 8;
        if (r->bytes != expected || (sgpu_get32(r->payload) != SGPU_RETIRED && sgpu_get32(r->payload) != SGPU_RETIRED_ERROR) || (sgpu_get32(r->payload) == SGPU_RETIRED && sgpu_get32(r->payload + 4))) return 0;
        break;
    default: expected = 0; break;
    }
    return r->bytes == expected;
}

uint32_t sgpu_dispatch(const void *wire, size_t bytes, void *reply, size_t capacity, size_t *reply_bytes, sgpu_backend_fn backend, void *context)
{
    struct sgpu_request_view view;
    struct sgpu_backend_result result = {0, 0, {0}};
    uint8_t *out = (uint8_t *)reply;
    uint32_t status;
    size_t i;
    uintptr_t input_start = (uintptr_t)wire, output_start = (uintptr_t)reply;
    if (!reply_bytes) return SGPU_BAD_FIELD;
    *reply_bytes = 0;
    if (!out || capacity < 120 || capacity > SGPU_MAX_MESSAGE) return SGPU_BAD_SIZE;
    /* Reject aliasing before writing anything; also reject address arithmetic
     * overflow. The caller must provide valid, non-aliasing storage/lengths. */
    if (bytes > SGPU_MAX_MESSAGE || input_start > UINTPTR_MAX - bytes || output_start > UINTPTR_MAX - capacity) return SGPU_BAD_SIZE;
    if (bytes && input_start < output_start + capacity && output_start < input_start + bytes) return SGPU_BAD_FIELD;
    for (i = 0; i < capacity; ++i) out[i] = 0;
    status = sgpu_validate_request(wire, bytes, &view);
    if (status == SGPU_OK) {
        if (backend) {
            backend(context, &view, &result);
            if (!response_ok(&view, &result)) status = SGPU_BAD_REPLY;
            else status = result.status;
        } else status = SGPU_UNSUPPORTED;
    }
    sgpu_put32(out, SGPU_MAGIC); sgpu_put16(out + 4, SGPU_ABI_MAJOR); sgpu_put16(out + 6, SGPU_ABI_MINOR);
    /* Only echo header identifiers from a complete, bounded input. They are
     * correlation data, never authenticated client/context identity. */
    if (wire && bytes >= 32) {
        sgpu_put32(out + 8, sgpu_get32((const uint8_t *)wire + 8));
        sgpu_put64(out + 16, sgpu_get64((const uint8_t *)wire + 16));
    }
    sgpu_put32(out + 24, status);
    *reply_bytes = 32;
    if (status == SGPU_OK) {
        for (i = 0; i < result.bytes; ++i) out[32 + i] = result.payload[i];
        *reply_bytes += result.bytes;
    }
    sgpu_put32(out + 12, (uint32_t)*reply_bytes);
    return status;
}
