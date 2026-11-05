/* Project-owned STM protocol boundary. No hardware or Apple HID operations. */
#ifndef S24_STM_PROTOCOL_H
#define S24_STM_PROTOCOL_H
#include <stddef.h>
#include <stdint.h>
#include "../../display/contract.h"

#define STM_RECORD_BYTES 16u
#define STM_CONTACTS 10u
#define STM_RAW_MAX 4095u
enum stm_result {
    STM_OK=0, STM_EMPTY=1, STM_NOT_COORDINATE=2, STM_ARGUMENT=3,
    STM_LENGTH=4, STM_FORMAT=5, STM_RANGE=6, STM_UNSUPPORTED=7,
    STM_CONTROLLER_LOSS=8, STM_TRANSITION=9, STM_DESYNC=10,
    STM_CLOCK=11, STM_EXHAUSTED=12, STM_BUSY=13, STM_DELIVERY=14,
    STM_STOPPED=15
};
struct stm_coordinate {
    uint32_t slot, action, x, y, touch_type, pressure, major, minor, remaining;
};
struct stm_config { uint32_t max_x, max_y, flip, rotation; };
/* Return zero only after atomic acceptance; nonzero must publish nothing.
   The event pointer is valid only for the duration of this synchronous call. */
typedef int (*stm_emit_fn)(void *, const struct ui_event *);
struct stm_adapter {
    struct ui_input_state logical, candidate;
    struct ui_event pending;
    struct stm_config config;
    uint32_t pending_valid, dispatching, stop_after;
};
#ifdef __cplusplus
extern "C" {
#endif
uint32_t stm_decode(const uint8_t *, size_t, uint32_t, uint32_t, struct stm_coordinate *);
/* Fresh/retired storage only. Retire the previous consumer epoch before reuse. */
uint32_t stm_adapter_init(struct stm_adapter *, const struct stm_config *, uint32_t);
uint32_t stm_adapter_feed(struct stm_adapter *, const uint8_t *, size_t, uint64_t, stm_emit_fn, void *);
uint32_t stm_adapter_resync(struct stm_adapter *, uint64_t, stm_emit_fn, void *);
uint32_t stm_adapter_retry(struct stm_adapter *, stm_emit_fn, void *);
uint32_t stm_adapter_stop(struct stm_adapter *, uint64_t, stm_emit_fn, void *);
/* Exact owned UI-001 v1 bytes; does not emit or inject an event. */
uint32_t stm_event_wire(const struct ui_event *, uint8_t *, size_t);
#ifdef __cplusplus
}
#endif
#endif
