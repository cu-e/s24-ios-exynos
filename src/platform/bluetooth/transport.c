#include "transport.h"

static uint16_t read16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8)); }
static uint32_t poison(struct bt_h4 *p, uint32_t error) { p->fault = error; return error; }

uint32_t bt_h4_init(struct bt_h4 *p, uint8_t *storage, size_t capacity, uint32_t direction, uint32_t ibs, uint32_t timeout_ms)
{
    struct bt_h4 empty = {0};
    if (!p) return BT_PARSE_ARGUMENT;
    *p = empty;
    p->fault = BT_PARSE_ARGUMENT;
    if (!storage || capacity < 5 || capacity > BT_MAX_FRAME || (direction != BT_FROM_CONTROLLER && direction != BT_TO_CONTROLLER) || ibs > 1 || !timeout_ms || timeout_ms > BT_MAX_FRAME_TIMEOUT_MS) return BT_PARSE_ARGUMENT;
    p->storage = storage; p->capacity = capacity; p->direction = direction; p->ibs = ibs; p->timeout_ms = timeout_ms; p->fault = 0;
    return BT_PARSE_OK;
}

uint32_t bt_h4_feed(struct bt_h4 *p, const uint8_t *data, size_t bytes, uint64_t now, bt_frame_fn emit, void *context, size_t *consumed)
{
    size_t at = 0, frames = 0;
    if (!consumed) return BT_PARSE_ARGUMENT;
    *consumed = 0;
    if (!p) return BT_PARSE_ARGUMENT;
    if (p->busy) return BT_PARSE_BUSY;
    if (p->fault) return p->fault;
    if ((!data && bytes) || (!emit && bytes) || !p->storage) return BT_PARSE_ARGUMENT;
    if (p->clock_seen && now < p->last_ms) return poison(p, BT_PARSE_CLOCK);
    p->last_ms = now; p->clock_seen = 1;
    if (p->used && now - p->started_ms >= p->timeout_ms) return poison(p, BT_PARSE_TIMEOUT);
    while (at < bytes && at < BT_FEED_BYTES && frames < BT_FEED_FRAMES) {
        if (!p->used) {
            uint8_t type = data[at++];
            *consumed = at;
            p->started_ms = now; p->storage[0] = type; p->used = 1;
            p->expected = 0;
            switch (type) {
            case 1: p->header = 4; if (p->direction != BT_TO_CONTROLLER) return poison(p, BT_PARSE_DIRECTION); break;
            case 2: p->header = 5; break;
            case 3: p->header = 4; break;
            case 4: p->header = 3; if (p->direction != BT_FROM_CONTROLLER) return poison(p, BT_PARSE_DIRECTION); break;
            case 5: p->header = 5; break;
            case 0xfc: case 0xfd: case 0xfe:
                if (!p->ibs) return poison(p, BT_PARSE_TYPE);
                p->header = 1; p->expected = 1; break;
            default: return poison(p, BT_PARSE_TYPE);
            }
        }
        while (at < bytes && at < BT_FEED_BYTES && p->used < p->header) {
            p->storage[p->used++] = data[at++];
        }
        *consumed = at;
        if (p->used < p->header) break;
        if (!p->expected) {
            size_t payload;
            switch (p->storage[0]) {
            case 1: case 3: payload = p->storage[3]; break;
            case 4: payload = p->storage[2]; break;
            case 5: payload = read16(p->storage + 3) & 0x3fff; break;
            default: payload = read16(p->storage + 3); break;
            }
            p->expected = p->header + payload;
            if (p->expected > p->capacity) return poison(p, BT_PARSE_SIZE);
        }
        while (at < bytes && at < BT_FEED_BYTES && p->used < p->expected) {
            p->storage[p->used++] = data[at++];
        }
        *consumed = at;
        if (p->used < p->expected) break;
        /* Prevent same-parser recursion while its borrowed frame is live. */
        p->busy = 1;
        if (emit(context, p->storage[0], p->storage, p->expected)) {
            p->busy = 0;
            return poison(p, BT_PARSE_CONSUMER);
        }
        p->busy = 0;
        p->used = 0; p->expected = 0; p->header = 0; ++frames;
    }
    if (at < bytes) return BT_PARSE_YIELD;
    return p->used ? BT_PARSE_MORE : BT_PARSE_OK;
}

uint32_t bt_command_init(struct bt_command *p, uint64_t epoch, uint8_t credits)
{
    struct bt_command empty = {0};
    if (!p) return BT_COMMAND_ARGUMENT;
    *p = empty;
    p->quarantined = 1;
    if (!epoch) return BT_COMMAND_ARGUMENT;
    p->epoch = epoch; p->credits = credits; p->quarantined = 0;
    return BT_COMMAND_OK;
}

uint32_t bt_command_tick(struct bt_command *p, uint64_t now)
{
    if (!p) return BT_COMMAND_ARGUMENT;
    if (p->quarantined) return BT_COMMAND_QUARANTINED;
    if (p->clock_seen && now < p->last_ms) { p->quarantined = 1; return BT_COMMAND_CLOCK; }
    p->clock_seen = 1; p->last_ms = now;
    if (p->pending && now - p->started_ms >= p->timeout_ms) { p->quarantined = 1; return BT_COMMAND_TIMEOUT; }
    return BT_COMMAND_OK;
}

uint32_t bt_command_begin(struct bt_command *p, uint16_t opcode, uint64_t now, uint32_t timeout_ms)
{
    uint32_t result;
    if (!p || !opcode || !timeout_ms || timeout_ms > BT_MAX_COMMAND_TIMEOUT_MS) return BT_COMMAND_ARGUMENT;
    result = bt_command_tick(p, now);
    if (result) return result;
    if (p->stopped) return BT_COMMAND_STOPPED;
    if (p->pending) return BT_COMMAND_PENDING;
    if (!p->credits) return BT_COMMAND_NO_CREDIT;
    --p->credits; p->pending = 1; p->opcode = opcode; p->started_ms = now; p->timeout_ms = timeout_ms;
    return BT_COMMAND_OK;
}

uint32_t bt_command_event(struct bt_command *p, const uint8_t *packet, size_t bytes, uint64_t now, struct bt_command_reply *reply)
{
    uint32_t result;
    struct bt_command_reply empty = {0};
    if (!reply) return BT_COMMAND_ARGUMENT;
    *reply = empty;
    if (!p || !packet || bytes < 3 || packet[0] != 4 || bytes != 3u + packet[2]) return BT_COMMAND_ARGUMENT;
    result = bt_command_tick(p, now);
    if (result) return result;
    if (packet[1] == 0x0e) {
        if (packet[2] < 3) return BT_COMMAND_ARGUMENT;
        reply->credits = packet[3]; reply->opcode = read16(packet + 4);
        reply->parameters = packet + 6; reply->parameter_bytes = bytes - 6;
        p->credits = reply->credits;
        if (!p->pending || !reply->opcode || p->opcode != reply->opcode) return BT_COMMAND_UNRELATED;
        p->pending = 0;
        /* Return parameters remain raw: completion is not status=success and
         * vendor EDL response layouts are ROM/profile dependent. */
        return BT_COMMAND_COMPLETE;
    }
    if (packet[1] == 0x0f) {
        if (packet[2] != 4) return BT_COMMAND_ARGUMENT;
        reply->status = packet[3]; reply->status_valid = 1; reply->credits = packet[4]; reply->opcode = read16(packet + 5);
        p->credits = reply->credits;
        if (!p->pending || !reply->opcode || p->opcode != reply->opcode) return BT_COMMAND_UNRELATED;
        if (!reply->status) return BT_COMMAND_ACCEPTED;
        p->pending = 0;
        return BT_COMMAND_REJECTED;
    }
    return BT_COMMAND_UNRELATED;
}

void bt_command_stop(struct bt_command *p) { if (p) p->stopped = 1; }
