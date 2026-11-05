#include "Policy.hpp"

namespace s24gpu {

static bool intersects(const void *left, size_t left_bytes, const void *right, size_t right_bytes)
{
    const uintptr_t l = reinterpret_cast<uintptr_t>(left);
    const uintptr_t r = reinterpret_cast<uintptr_t>(right);
    if (l > UINTPTR_MAX - left_bytes || r > UINTPTR_MAX - right_bytes) return true;
    return left_bytes && right_bytes && l < r + right_bytes && r < l + left_bytes;
}

static Transport shape_status(const Shape &shape)
{
    if (!shape.current_argument_version || shape.reserved_nonzero) return Transport::bad_argument;
    if (shape.selector || shape.argument_selector != shape.selector) return Transport::unsupported;
    if (shape.scalar_inputs || shape.scalar_outputs || shape.async_references || shape.async_port || shape.async_pointer ||
        shape.input_descriptor || shape.output_descriptor || shape.variable_output) return Transport::bad_argument;
    if (!shape.input || shape.input_bytes < 32 || shape.input_bytes > SGPU_MAX_MESSAGE || !shape.output ||
        shape.output_capacity < 120 || shape.output_capacity > SGPU_MAX_MESSAGE) return Transport::bad_argument;
    if (intersects(shape.input, shape.input_bytes, shape.output, shape.output_capacity)) return Transport::bad_argument;
    return Transport::ok;
}

Transport admit(Session &session, uintptr_t owner, bool authenticated, bool ready)
{
    if (!owner || !authenticated) return Transport::not_privileged;
    if (!ready) return Transport::not_ready;
    if (session.phase != Phase::unopened || session.provider_hold) return Transport::busy;
    session.owner = owner;
    session.phase = Phase::open;
    session.active_calls = 0;
    session.provider_hold = true;
    session.close_notified = false;
    return Transport::ok;
}

Transport begin(Session &session, uintptr_t caller, const Shape &shape, bool ready)
{
    if (!caller || caller != session.owner) return Transport::not_privileged;
    const Transport check = shape_status(shape);
    if (check != Transport::ok) return check;
    if (session.phase != Phase::open || !session.provider_hold) return Transport::not_open;
    if (!ready) return Transport::not_ready;
    if (session.active_calls) return Transport::busy;
    session.active_calls = 1;
    return Transport::ok;
}

void finish(Session &session, uint32_t status)
{
    if (session.active_calls) --session.active_calls;
    if (session.phase == Phase::open && (status == SGPU_BAD_REPLY || status == SGPU_BACKEND_ERROR))
        session.phase = Phase::faulted;
    // Boundary return or protocol error is never proof of GPU quiescence.
}

void close(Session &session)
{
    session.phase = Phase::closed;
    // Keep provider_hold and any active call. Closing cannot retire resources.
}

bool release_session_hold(Session &session, Quiescence proof)
{
    if (proof != Quiescence::provider_proven || !session.provider_hold || session.active_calls ||
        (session.phase != Phase::closed && session.phase != Phase::faulted)) return false;
    session.provider_hold = false;
    return true;
}

Completion snapshot_dispatch(const Shape &shape, Storage &storage, sgpu_backend_fn callback, void *context)
{
    const Transport check = shape_status(shape);
    if (check != Transport::ok) return {check, SGPU_BACKEND_ERROR, 0};
    if (!callback || intersects(shape.input, shape.input_bytes, &storage, sizeof(storage)) ||
        intersects(shape.output, shape.output_capacity, &storage, sizeof(storage)))
        return {Transport::bad_argument, SGPU_BACKEND_ERROR, 0};
    const uint8_t *source = static_cast<const uint8_t *>(shape.input);
    for (size_t i = 0; i < shape.input_bytes; ++i) storage.input[i] = source[i];
    storage.reply_bytes = 0;
    const uint32_t protocol = sgpu_dispatch(storage.input, shape.input_bytes, storage.output,
        shape.output_capacity, &storage.reply_bytes, callback, context);
    if (storage.reply_bytes < 32 || storage.reply_bytes > shape.output_capacity)
        return {Transport::io_error, protocol, 0};
    uint8_t *output = static_cast<uint8_t *>(shape.output);
    for (size_t i = 0; i < storage.reply_bytes; ++i) output[i] = storage.output[i];
    return {Transport::ok, protocol, storage.reply_bytes};
}

} // namespace s24gpu
