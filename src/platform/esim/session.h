#ifndef S24_ESIM_SESSION_H
#define S24_ESIM_SESSION_H

#include <stddef.h>
#include <stdint.h>

/* Project-owned, transport-neutral boundary. No hardware backend is included. */
#define ESIM_MAX_COMMAND 65544u
#define ESIM_MAX_RESPONSE 65538u
#define ESIM_MAX_AID 16u
#define ESIM_MAX_EXCHANGES 4096u

enum esim_result {
    ESIM_OK = 0,
    ESIM_E_ARGUMENT,
    ESIM_E_STATE,
    ESIM_E_BUSY,
    ESIM_E_TRANSPORT,
    ESIM_E_PROTOCOL,
    ESIM_E_CANCELLED,
    ESIM_E_BUDGET,
    ESIM_E_CLEANUP
};

enum esim_state { ESIM_IDLE = 0, ESIM_OPEN, ESIM_CLOSED, ESIM_POISONED };

struct esim_apdu {
    uint32_t data_offset;
    uint32_t data_length;
    uint32_t expected_length;
    uint8_t extended;
    uint8_t has_expected_length;
};

struct esim_reply {
    size_t length;
    size_t data_length;
    uint8_t sw1;
    uint8_t sw2;
};

struct esim_limits {
    uint32_t max_command;
    uint32_t max_response;
    uint32_t max_exchanges;
};

/*
 * Callbacks execute serially on the owner thread and must implement their own
 * bounded timeout/quiescence. They may call esim_request_cancel(), but cannot
 * recursively run session operations. The wrapper cannot preempt a callback.
 *
 * open_channel: return the owned handle even on partial failure, if one was
 * created. An unsuccessful open with handle -1 guarantees none was created.
 * Handles 1..255 are opaque local handles (lpac's close API is uint8_t), not a
 * claim about a modem's physical channel count. No CLA bits are rewritten.
 *
 * exchange must respect capacity; returned length includes SW1/SW2. Backend
 * memory corruption cannot be contained by this C interface. Caller buffers
 * remain valid until a synchronous callback returns.
 */
struct esim_transport {
    void *context;
    int (*connect)(void *context);
    int (*open_channel)(void *context, const uint8_t *aid, size_t length,
                        int32_t *handle);
    int (*exchange)(void *context, uint8_t handle, const uint8_t *command,
                    size_t length, uint8_t *response, size_t capacity,
                    size_t *response_length);
    int (*close_channel)(void *context, uint8_t handle);
    int (*disconnect)(void *context);
};

struct esim_session {
    struct esim_transport transport;
    struct esim_limits limits;
    _Atomic(unsigned) cancel_requested;
    uint32_t exchanges;
    enum esim_state state;
    enum esim_result last_error;
    int backend_status;
    int cleanup_status;
    uint8_t handle;
    uint8_t transport_owned;
    uint8_t channel_owned;
    uint8_t cleanup_uncertain;
    uint8_t busy;
    uint8_t initialized;
};

enum esim_result esim_parse_command(const uint8_t *bytes, size_t length,
                                    struct esim_apdu *result);
enum esim_result esim_session_init(struct esim_session *session,
                                  const struct esim_transport *transport,
                                  const struct esim_limits *limits);
enum esim_result esim_session_begin(struct esim_session *session,
                                   const uint8_t *aid, size_t length);
enum esim_result esim_session_exchange(struct esim_session *session,
                                      const uint8_t *command, size_t length,
                                      uint8_t *response, size_t capacity,
                                      struct esim_reply *reply);
enum esim_result esim_session_end(struct esim_session *session);

/* Only this operation may run concurrently;session initialization/lifetime must
 * already be established and remain stable until the requesting thread joins. */
void esim_request_cancel(struct esim_session *session);
enum esim_result esim_service_cancel(struct esim_session *session);

#endif
