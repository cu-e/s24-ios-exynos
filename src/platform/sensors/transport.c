/* SPDX-License-Identifier: MIT */
#include "transport.h"
static uint16_t le16(const uint8_t *p) {
    return (uint16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}
static uint64_t le64(const uint8_t *p) {
    uint64_t v = 0;
    for (unsigned i = 0; i < 8; ++i) v |= (uint64_t)p[i] << (8 * i);
    return v;
}
enum sen_result sen_shub_report(const struct sen_service *svc, const uint8_t *p,
                               size_t n, uint64_t receipt, struct sen_sample *out,
                               size_t cap, size_t *count) {
    if (!svc || !p || !out || !count) return SEN_ARGUMENT;
    if (!svc->online || !svc->clock_valid) return SEN_UNAVAILABLE;
    if (n < 15) return SEN_TRUNCATED;
    size_t total = le16(p + 3), len = le16(p + 5);
    if (len > total) return SEN_LENGTH;
    if (len > n - 15) return SEN_TRUNCATED;
    if (total != len) return SEN_UNSUPPORTED;
    if (p[0] != 5) return SEN_UNSUPPORTED; /* CMD_REPORT */
    if (len < 4) return SEN_TRUNCATED;
    const uint8_t *body = p + 15;
    if (body[0] != 0x37 || (body[1] != 1 && body[1] != 4))
        return SEN_UNSUPPORTED;
    size_t batch = le16(body + 2);
    if (!batch) return SEN_LENGTH;
    if (batch > (len - 4) / 14) return SEN_TRUNCATED;
    if (4 + batch * 14 != len) return SEN_UNSUPPORTED;
    if (batch > cap) return SEN_CAPACITY;
    /* All validation precedes publication: a cut batch emits no partial data. */
    for (size_t i = 0; i < batch; ++i) {
        const uint8_t *event = body + 4 + i * 14;
        struct sen_sample sample = {0};
        sample.type = body[1];
        for (unsigned j = 0; j < 6; ++j) sample.raw[j] = event[j];
        sample.hub_ns = le64(event + 6);
        sample.receipt_boot_ns = receipt;
        sample.future_clamped = sample.hub_ns > receipt;
        sample.effective_boot_ns = sample.future_clamped ? receipt : sample.hub_ns;
        out[i] = sample;
    }
    *count = batch;
    return SEN_OK;
}
enum sen_result sen_gnss_frame(const struct sen_service *svc, const uint8_t *p,
                              size_t n, struct sen_gnss_frame *out) {
    if (!svc || !p || !out) return SEN_ARGUMENT;
    if (!svc->online) return SEN_UNAVAILABLE;
    if (n < 12) return SEN_TRUNCATED;
    if (le16(p) != 0xabcd) return SEN_UNSUPPORTED;
    size_t len = le16(p + 6);
    if (len < 12) return SEN_LENGTH;
    size_t padded = (len + 3) & ~(size_t)3;
    if (padded > n) return SEN_TRUNCATED;
    if ((le16(p + 4) & 0xc000) != 0xc000 || p[8] != 0)
        return SEN_UNSUPPORTED;
    struct sen_gnss_frame frame = {le16(p + 2), p[9], p + 12, len - 12, padded};
    *out = frame;
    return SEN_OK;
}
