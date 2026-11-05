/* SPDX-License-Identifier: MIT */
#include "transport.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void put16(uint8_t *p, unsigned v) { p[0] = v; p[1] = v >> 8; }
static void put64(uint8_t *p, uint64_t v) {
    for (unsigned i = 0; i < 8; ++i) p[i] = v >> (8 * i);
}
int main(void) {
    const struct sen_service ready = {true, true}, down = {false, true},
                             no_clock = {true, false};
    /* Independent byte fixture: packed15-byte header and two14-byte events. */
    uint8_t bytes[80] = {0}, *p = bytes + 1; /* deliberately unaligned */
    p[0] = 5; put16(p + 3, 32); put16(p + 5, 32);
    put64(p + 7, UINT64_MAX); /* transaction token must not affect samples */
    p[15] = 0x37; p[16] = 1; put16(p + 17, 2);
    p[19] = 0xff; p[20] = 0x7f; p[21] = 0; p[22] = 0x80;
    put64(p + 25, 900); put64(p + 39, 1100);
    struct sen_sample out[2], saved[2]; memset(out, 0xa5, sizeof(out));
    memcpy(saved, out, sizeof(out)); size_t count = 99;
    for (size_t n = 0; n < 47; ++n) {
        assert(sen_shub_report(&ready, p, n, 1000, out, 2, &count) == SEN_TRUNCATED);
        assert(count == 99 && memcmp(out, saved, sizeof(out)) == 0);
    }
    assert(sen_shub_report(&ready, p, 47, 1000, out, 1, &count) == SEN_CAPACITY);
    assert(count == 99 && memcmp(out, saved, sizeof(out)) == 0);
    assert(sen_shub_report(&down, p, 47, 1000, out, 2, &count) == SEN_UNAVAILABLE);
    assert(sen_shub_report(&no_clock, p, 47, 1000, out, 2, &count) == SEN_UNAVAILABLE);
    assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_OK);
    assert(count == 2 && out[0].hub_ns == 900 && out[0].effective_boot_ns == 900);
    assert(out[0].receipt_boot_ns == 1000 && !out[0].future_clamped);
    assert(out[0].raw[0] == 0xff && out[0].raw[3] == 0x80);
    assert(out[1].hub_ns == 1100 && out[1].effective_boot_ns == 1000 && out[1].future_clamped);
    p[16] = 4; put64(p + 25, 0); put64(p + 39, UINT64_MAX);
    assert(sen_shub_report(&ready, p, 64, 0, out, 2, &count) == SEN_OK);
    assert(out[0].type == 4 && out[0].effective_boot_ns == 0 && out[1].future_clamped);
    put64(p + 25, 1000); put64(p + 39, 900); /* batching need not be monotonic */
    assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_OK);
    p[16] = 8; assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_UNSUPPORTED);
    p[16] = 1; put16(p + 17, 0);
    assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_LENGTH);
    put16(p + 17, 65535);
    assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_TRUNCATED);
    put16(p + 3, 33);
    assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_UNSUPPORTED);
    put16(p + 3, 1);
    assert(sen_shub_report(&ready, p, 47, 1000, out, 2, &count) == SEN_LENGTH);
    assert(sen_shub_report(NULL, p, 47, 0, out, 2, &count) == SEN_ARGUMENT);
    puts("SHUB: every prefix, atomic publication, size/count, padding, unsupported type/fragment, unavailable and timestamp controls pass");
    uint8_t gnss[] = {0xcd,0xab,0xfe,0xff,0,0xc0,15,0,0,0xff,0x55,0x55,'a','b','c',0xaa};
    struct sen_gnss_frame frame, prior; memset(&frame, 0xa5, sizeof(frame));
    memcpy(&prior, &frame, sizeof(frame));
    for (size_t n = 0; n < sizeof(gnss); ++n) {
        assert(sen_gnss_frame(&ready, gnss, n, &frame) == SEN_TRUNCATED);
        assert(memcmp(&frame, &prior, sizeof(frame)) == 0);
    }
    assert(sen_gnss_frame(&down, gnss, 16, &frame) == SEN_UNAVAILABLE);
    assert(sen_gnss_frame(&ready, gnss, 16, &frame) == SEN_OK);
    assert(frame.sequence == 65534 && frame.channel_sequence == 255);
    assert(frame.payload_size == 3 && frame.consumed == 16 && memcmp(frame.payload, "abc", 3) == 0);
    gnss[5] = 0x80; assert(sen_gnss_frame(&ready, gnss, 16, &frame) == SEN_UNSUPPORTED);
    gnss[5] = 0xc0; gnss[8] = 82; assert(sen_gnss_frame(&ready, gnss, 16, &frame) == SEN_UNSUPPORTED);
    gnss[8] = 0; gnss[0] = 0; assert(sen_gnss_frame(&ready, gnss, 16, &frame) == SEN_UNSUPPORTED);
    gnss[0] = 0xcd; gnss[6] = 11; assert(sen_gnss_frame(&ready, gnss, 16, &frame) == SEN_LENGTH);
    gnss[6] = 255; gnss[7] = 255; assert(sen_gnss_frame(&ready, gnss, 16, &frame) == SEN_TRUNCATED);
    puts("GNSS: every prefix including padding, borrowed opaque body, framing/channel/length, unavailable controls pass");
    return 0;
}
