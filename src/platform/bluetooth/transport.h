/* Independently authored H4 stream decoder and initialization-command model.
 * No UART, GPIO, firmware, file, network or clock I/O. No native driver here. */
#ifndef S24_BT_TRANSPORT_H
#define S24_BT_TRANSPORT_H
#include <stddef.h>
#include <stdint.h>
#define BT_MAX_FRAME 65540u
#define BT_FEED_BYTES 4096u
#define BT_FEED_FRAMES 64u
#define BT_MAX_FRAME_TIMEOUT_MS 5000u
#define BT_MAX_COMMAND_TIMEOUT_MS 30000u
enum bt_direction { BT_FROM_CONTROLLER = 1, BT_TO_CONTROLLER = 2 };
enum bt_parse_result {
    BT_PARSE_OK = 0, BT_PARSE_MORE = 1, BT_PARSE_YIELD = 2,
    BT_PARSE_TYPE = 3, BT_PARSE_SIZE = 4, BT_PARSE_TIMEOUT = 5,
    BT_PARSE_CLOCK = 6, BT_PARSE_BUSY = 7, BT_PARSE_ARGUMENT = 8,
    BT_PARSE_CONSUMER = 9, BT_PARSE_DIRECTION = 10
};
struct bt_h4 {
    uint8_t *storage;
    size_t capacity, used, header, expected;
    uint64_t started_ms, last_ms;
    uint32_t timeout_ms, direction, ibs, fault, clock_seen, busy;
};
/* A synchronous borrowed full frame, including packet indicator. Returning
 * nonzero quarantines the stream; no automatic callback retry or resync. */
typedef int (*bt_frame_fn)(void *, uint8_t, const uint8_t *, size_t);
#if defined(__cplusplus)
extern "C" {
#endif
uint32_t bt_h4_init(struct bt_h4 *, uint8_t *, size_t, uint32_t, uint32_t, uint32_t);
uint32_t bt_h4_feed(struct bt_h4 *, const uint8_t *, size_t, uint64_t, bt_frame_fn, void *, size_t *);

enum bt_command_result {
    BT_COMMAND_OK = 0, BT_COMMAND_COMPLETE = 1, BT_COMMAND_ACCEPTED = 2,
    BT_COMMAND_REJECTED = 3, BT_COMMAND_UNRELATED = 4,
    BT_COMMAND_PENDING = 5, BT_COMMAND_NO_CREDIT = 6,
    BT_COMMAND_TIMEOUT = 7, BT_COMMAND_QUARANTINED = 8,
    BT_COMMAND_STOPPED = 9, BT_COMMAND_ARGUMENT = 10, BT_COMMAND_CLOCK = 11
};
/* Exclusive initialization channel, one outstanding command. This is not an
 * asynchronous Bluetooth procedure/connection state machine or daemon bridge. */
struct bt_command {
    uint64_t epoch, started_ms, last_ms;
    uint32_t timeout_ms, pending, stopped, quarantined, clock_seen;
    uint16_t opcode;
    uint8_t credits;
};
struct bt_command_reply {
    const uint8_t *parameters;
    size_t parameter_bytes;
    uint16_t opcode;
    uint8_t credits, status, status_valid;
};
uint32_t bt_command_init(struct bt_command *, uint64_t, uint8_t);
uint32_t bt_command_begin(struct bt_command *, uint16_t, uint64_t, uint32_t);
uint32_t bt_command_tick(struct bt_command *, uint64_t);
uint32_t bt_command_event(struct bt_command *, const uint8_t *, size_t, uint64_t, struct bt_command_reply *);
void bt_command_stop(struct bt_command *);
#if defined(__cplusplus)
}
#endif
#endif
