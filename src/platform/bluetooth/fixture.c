/* Owned host mutation/clock/lifecycle fixture. No UART or device API. */
#include "transport.h"
#include <stdio.h>
#include <string.h>
#define CHECK(c) do { if (!(c)) { fprintf(stderr,"check failed at %d: %s\n",__LINE__,#c); return 1; } } while (0)
static unsigned frames;
static int emit(void *context, uint8_t type, const uint8_t *wire, size_t n)
{
    (void)context;
    if (!wire || !n || n > 264 || type != wire[0]) return 1;
    ++frames;
    return 0;
}
static uint32_t random_step(uint32_t *s) { *s ^= *s << 13; *s ^= *s >> 17; *s ^= *s << 5; return *s; }

int main(void)
{
    static const uint8_t packets[5][8] = {
        {1,3,12,0}, {2,1,32,3,0,0xfd,0xfc,0xfe}, {3,1,0,2,0x61,0x62},
        {4,0xff,3,0xfd,0xfc,0xfe}, {5,1,0,3,0xc0,0x11,0xfd,0xfe}
    };
    static const size_t lengths[5] = {4,8,6,6,8};
    uint8_t guarded[280], input[8];
    struct bt_h4 p;
    struct bt_command cmd;
    struct bt_command_reply reply;
    uint32_t seed = UINT32_C(0x2400b7), result;
    size_t i, used, split, count = 20000, quarantined = 0;
    for (i = 0; i < count; ++i) {
        size_t which = random_step(&seed) % 5, n = lengths[which], j;
        uint32_t direction = which == 0 ? BT_TO_CONTROLLER : BT_FROM_CONTROLLER;
        unsigned before;
        memset(guarded, 0xA5, sizeof(guarded));
        memcpy(input, packets[which], sizeof(input));
        if (i % 3) input[random_step(&seed) % n] ^= (uint8_t)(1u << (random_step(&seed) % 8));
        split = random_step(&seed) % (n + 1);
        CHECK(bt_h4_init(&p, guarded + 8, 264, direction, 0, 100) == BT_PARSE_OK);
        result = bt_h4_feed(&p, input, split, 10, emit, NULL, &used);
        CHECK(used <= split);
        if (!p.fault) result = bt_h4_feed(&p, input + split, n - split, 11, emit, NULL, &used);
        if (!p.fault && p.used) result = bt_h4_feed(&p, NULL, 0, 111, emit, NULL, &used);
        if (p.fault) {
            ++quarantined; before = frames;
            CHECK(bt_h4_feed(&p, packets[3], lengths[3], 112, emit, NULL, &used) == result);
            CHECK(used == 0 && before == frames);
        }
        for (j = 0; j < 8; ++j) CHECK(guarded[j] == 0xA5 && guarded[272 + j] == 0xA5);
    }
    CHECK(quarantined > 1000 && frames > 6000);
    CHECK(bt_command_init(&cmd, 1, 0) == BT_COMMAND_OK);
    CHECK(bt_command_begin(&cmd, 0x0c03, 100, 10) == BT_COMMAND_NO_CREDIT);
    {
        const uint8_t credit[] = {4,14,3,1,0,0};
        const uint8_t status[] = {4,15,4,0,1,3,12};
        const uint8_t error[] = {4,14,4,1,3,12,12};
        CHECK(bt_command_event(&cmd, credit, sizeof(credit), 101, &reply) == BT_COMMAND_UNRELATED);
        CHECK(bt_command_begin(&cmd, 0x0c03, 102, 10) == BT_COMMAND_OK);
        CHECK(bt_command_event(&cmd, status, sizeof(status), 103, &reply) == BT_COMMAND_ACCEPTED && cmd.pending);
        CHECK(bt_command_event(&cmd, error, sizeof(error), 104, &reply) == BT_COMMAND_COMPLETE);
        CHECK(!reply.status_valid && reply.parameter_bytes == 1 && reply.parameters[0] == 12);
    }
    CHECK(bt_command_begin(&cmd, 0xfc00, 105, 10) == BT_COMMAND_OK);
    bt_command_stop(&cmd);
    CHECK(cmd.pending && bt_command_begin(&cmd, 0x1001, 106, 10) == BT_COMMAND_STOPPED);
    CHECK(bt_command_tick(&cmd, 115) == BT_COMMAND_TIMEOUT && cmd.pending);
    CHECK(bt_command_begin(&cmd, 0xfc00, 116, 10) == BT_COMMAND_QUARANTINED);
    printf("{\"outcome\":\"pass\",\"environment\":\"synthetic-h4-command-model\",\"mutation_control_attempts\":%zu,\"quarantined_streams\":%zu,\"frame_callbacks\":%u,\"device_io\":false}\n",count,quarantined,frames);
    return 0;
}
