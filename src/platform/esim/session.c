#include "session.h"

static uint32_t be16(const uint8_t *p)
{
    return ((uint32_t)p[0] << 8) | p[1];
}

enum esim_result esim_parse_command(const uint8_t *bytes, size_t length,
                                    struct esim_apdu *result)
{
    uint32_t data;
    if (!result) return ESIM_E_ARGUMENT;
    *result = (struct esim_apdu){0};
    if (!bytes || length < 4 || length > ESIM_MAX_COMMAND)
        return ESIM_E_ARGUMENT;
    if (length == 4) return ESIM_OK;
    if (length == 5) {
        result->has_expected_length = 1;
        result->expected_length = bytes[4] ? bytes[4] : 256u;
        return ESIM_OK;
    }
    if (bytes[4]) {
        data = bytes[4];
        if (length != 5u + data && length != 6u + data)
            return ESIM_E_PROTOCOL;
        result->data_offset = 5;
        result->data_length = data;
        if (length == 6u + data) {
            result->has_expected_length = 1;
            result->expected_length = bytes[length - 1] ? bytes[length - 1] : 256u;
        }
        return ESIM_OK;
    }
    if (length < 7) return ESIM_E_PROTOCOL;
    data = be16(bytes + 5);
    if (length == 7) {
        result->extended = 1;
        result->has_expected_length = 1;
        result->expected_length = data ? data : 65536u;
        return ESIM_OK;
    }
    if (!data || (length != 7u + data && length != 9u + data))
        return ESIM_E_PROTOCOL;
    result->extended = 1;
    result->data_offset = 7;
    result->data_length = data;
    if (length == 9u + data) {
        uint32_t le = be16(bytes + length - 2);
        result->has_expected_length = 1;
        result->expected_length = le ? le : 65536u;
    }
    return ESIM_OK;
}

static int cancelled(const struct esim_session *s)
{
#if defined(__clang__)
    return __c11_atomic_load(&s->cancel_requested, __ATOMIC_ACQUIRE) != 0;
#elif defined(__GNUC__)
    return __atomic_load_n(&s->cancel_requested, __ATOMIC_ACQUIRE) != 0;
#else
#error "ESIM session requires Clang or GCC atomic intrinsics"
#endif
}

static enum esim_result ready(struct esim_session *s)
{
    if (!s || !s->initialized) return ESIM_E_ARGUMENT;
    if (s->busy) return ESIM_E_BUSY;
    if (s->state == ESIM_POISONED) return ESIM_E_CLEANUP;
    return ESIM_OK;
}

static void cleanup(struct esim_session *s)
{
    int status;
    if (s->channel_owned) {
        uint8_t handle = s->handle;
        s->channel_owned = 0;
        s->handle = 0;
        status = s->transport.close_channel(s->transport.context, handle);
        if (status) {
            if (!s->cleanup_status) s->cleanup_status = status;
            s->cleanup_uncertain = 1;
        }
    }
    if (s->transport_owned) {
        s->transport_owned = 0;
        status = s->transport.disconnect(s->transport.context);
        if (status) {
            if (!s->cleanup_status) s->cleanup_status = status;
            s->cleanup_uncertain = 1;
        }
    }
    s->state = s->cleanup_uncertain ? ESIM_POISONED :
               (cancelled(s) ? ESIM_CLOSED : ESIM_IDLE);
}

static enum esim_result fail(struct esim_session *s, enum esim_result result,
                             int backend_status)
{
    s->last_error = result;
    s->backend_status = backend_status;
    cleanup(s);
    s->busy = 0;
    return result;
}

enum esim_result esim_session_init(struct esim_session *s,
                                  const struct esim_transport *transport,
                                  const struct esim_limits *limits)
{
    if (!s) return ESIM_E_ARGUMENT;
    *s = (struct esim_session){0};
#if defined(__clang__)
    __c11_atomic_init(&s->cancel_requested, 0);
#else
    __atomic_store_n(&s->cancel_requested, 0, __ATOMIC_RELAXED);
#endif
    if (!transport || !limits || !transport->connect ||
        !transport->open_channel || !transport->exchange ||
        !transport->close_channel || !transport->disconnect ||
        limits->max_command < 4 || limits->max_command > ESIM_MAX_COMMAND ||
        limits->max_response < 2 || limits->max_response > ESIM_MAX_RESPONSE ||
        !limits->max_exchanges || limits->max_exchanges > ESIM_MAX_EXCHANGES)
        return ESIM_E_ARGUMENT;
    s->transport = *transport;
    s->limits = *limits;
    s->initialized = 1;
    return ESIM_OK;
}

enum esim_result esim_session_begin(struct esim_session *s,
                                   const uint8_t *aid, size_t length)
{
    enum esim_result guard = ready(s);
    int status;
    int32_t handle = -1;
    if (guard != ESIM_OK) return guard;
    if (cancelled(s)) {
        s->state = ESIM_CLOSED;
        return ESIM_E_CANCELLED;
    }
    if (s->state != ESIM_IDLE) return ESIM_E_STATE;
    if (!aid || !length || length > ESIM_MAX_AID) return ESIM_E_ARGUMENT;
    s->exchanges = 0;
    s->backend_status = 0;
    s->cleanup_status = 0;
    s->last_error = ESIM_OK;
    s->busy = 1;
    /* A failed connect can still own partial transport resources. */
    s->transport_owned = 1;
    status = s->transport.connect(s->transport.context);
    if (cancelled(s)) return fail(s, ESIM_E_CANCELLED, status);
    if (status) return fail(s, ESIM_E_TRANSPORT, status);
    status = s->transport.open_channel(s->transport.context, aid, length, &handle);
    if (handle > 0 && handle <= (int32_t)UINT8_MAX) {
        s->handle = (uint8_t)handle;
        s->channel_owned = 1;
    } else if (!status || handle != -1) {
        /* Only failed open with -1 promises no partial channel ownership. */
        s->cleanup_uncertain = 1;
    }
    if (cancelled(s)) return fail(s, ESIM_E_CANCELLED, status);
    if (status) return fail(s, ESIM_E_TRANSPORT, status);
    if (!s->channel_owned) return fail(s, ESIM_E_PROTOCOL, 0);
    s->state = ESIM_OPEN;
    s->busy = 0;
    return ESIM_OK;
}

enum esim_result esim_session_exchange(struct esim_session *s,
                                      const uint8_t *command, size_t length,
                                      uint8_t *response, size_t capacity,
                                      struct esim_reply *reply)
{
    struct esim_apdu parsed;
    size_t received = 0;
    int status;
    enum esim_result guard;
    if (reply) *reply = (struct esim_reply){0};
    guard = ready(s);
    if (guard != ESIM_OK) return guard;
    if (cancelled(s)) return esim_service_cancel(s);
    if (s->state != ESIM_OPEN) return ESIM_E_STATE;
    if (!reply || !response || capacity < 2 || length > s->limits.max_command)
        return ESIM_E_ARGUMENT;
    guard = esim_parse_command(command, length, &parsed);
    if (guard != ESIM_OK) return guard;
    s->busy = 1;
    if (s->exchanges >= s->limits.max_exchanges)
        return fail(s, ESIM_E_BUDGET, 0);
    if (capacity > s->limits.max_response) capacity = s->limits.max_response;
    s->exchanges++;
    status = s->transport.exchange(s->transport.context, s->handle, command,
                                  length, response, capacity, &received);
    if (cancelled(s)) return fail(s, ESIM_E_CANCELLED, status);
    if (status) return fail(s, ESIM_E_TRANSPORT, status);
    if (received < 2 || received > capacity)
        return fail(s, ESIM_E_PROTOCOL, 0);
    reply->length = received;
    reply->data_length = received - 2;
    reply->sw1 = response[received - 2];
    reply->sw2 = response[received - 1];
    s->last_error = ESIM_OK;
    s->backend_status = 0;
    s->busy = 0;
    return ESIM_OK;
}

enum esim_result esim_session_end(struct esim_session *s)
{
    enum esim_result guard = ready(s);
    if (guard != ESIM_OK) return guard;
    s->busy = 1;
    cleanup(s);
    s->busy = 0;
    s->last_error = s->cleanup_uncertain ? ESIM_E_CLEANUP :
                    (cancelled(s) ? ESIM_E_CANCELLED : ESIM_OK);
    return s->last_error;
}

void esim_request_cancel(struct esim_session *s)
{
    if (!s) return;
#if defined(__clang__)
    __c11_atomic_store(&s->cancel_requested, 1, __ATOMIC_RELEASE);
#else
    __atomic_store_n(&s->cancel_requested, 1, __ATOMIC_RELEASE);
#endif
}

enum esim_result esim_service_cancel(struct esim_session *s)
{
    enum esim_result guard = ready(s);
    if (guard != ESIM_OK) return guard;
    if (!cancelled(s)) return ESIM_OK;
    s->busy = 1;
    return fail(s, ESIM_E_CANCELLED, 0);
}
