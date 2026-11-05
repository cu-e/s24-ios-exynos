/* Protocol tests only. No BO allocation, GPU submission, fence completion,
 * sleeping, cache/VM operation, reset, firmware or hardware access exists here. */
#include "sgpu_fake.h"

static void fake_backend(void *context, const struct sgpu_request_view *v, struct sgpu_backend_result *r)
{
    struct sgpu_fake *state = (struct sgpu_fake *)context;
    ++state->calls;
    if (v->opcode == SGPU_QUERY) {
        uint64_t features = SGPU_FEATURE_SYNTHETIC | SGPU_FEATURE_VALIDATION;
        if (sgpu_get64(v->payload + 8) & ~features) { r->status = SGPU_UNSUPPORTED; return; }
        r->bytes = 88;
        sgpu_put64(r->payload, features);
        /* Hardware/profile/budget/VA fields remain explicitly zero. */
        sgpu_put32(r->payload + 60, SGPU_MAX_MESSAGE);
        sgpu_put32(r->payload + 64, SGPU_MAX_IBS);
        sgpu_put32(r->payload + 68, SGPU_MAX_USES);
        sgpu_put32(r->payload + 72, SGPU_MAX_DEPS);
        sgpu_put32(r->payload + 76, (uint32_t)(SGPU_MAX_WAIT_NS / 1000000));
    } else if (v->opcode == SGPU_STOP) {
        state->stopped = 1;
    } else {
        r->status = state->stopped ? SGPU_STOPPED : SGPU_UNSUPPORTED;
    }
}

uint32_t sgpu_fake_exchange(struct sgpu_fake *state, const void *wire, size_t bytes, void *reply, size_t capacity, size_t *reply_bytes)
{
    if (!state) { if (reply_bytes) *reply_bytes = 0; return SGPU_BAD_FIELD; }
    return sgpu_dispatch(wire, bytes, reply, capacity, reply_bytes, fake_backend, state);
}
