/* SPDX-License-Identifier: MIT
 * Owned host boundary; protocol provenance in README.md. No hardware access.
 */
#ifndef S24_SENSOR_TRANSPORT_H
#define S24_SENSOR_TRANSPORT_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
enum sen_result { SEN_OK, SEN_ARGUMENT, SEN_UNAVAILABLE, SEN_TRUNCATED,
                  SEN_LENGTH, SEN_UNSUPPORTED, SEN_CAPACITY };
/* Caller-provided liveness is an explicit test/backend input, never discovery. */
struct sen_service { bool online; bool clock_valid; };
struct sen_sample {
    uint8_t type;
    uint8_t raw[6]; /* Pinned accelerometer/gyro payload, no SI scale claim. */
    uint64_t hub_ns, receipt_boot_ns, effective_boot_ns;
    bool future_clamped;
};
/* One complete SHUB CMD_REPORT containing one BYPASS record, type 1 or 4.
 * Failure leaves samples and count unchanged. Header timestamp is a transaction
 * token, NOT a sample timestamp. No fragment reassembly or unknown record skip.
 */
enum sen_result sen_shub_report(const struct sen_service *, const uint8_t *, size_t,
                               uint64_t receipt_boot_ns, struct sen_sample *,
                               size_t capacity, size_t *count);
struct sen_gnss_frame {
    uint16_t sequence;
    uint8_t channel_sequence;
    const uint8_t *payload; /* Borrowed until input buffer is released. */
    size_t payload_size, consumed;
};
/* Complete single-channel/single-frame KEPLER shared-memory IPC, opaque body.
 * Four-byte transport padding is consumed, never returned as body bytes.
 */
enum sen_result sen_gnss_frame(const struct sen_service *, const uint8_t *, size_t,
                              struct sen_gnss_frame *);
#endif
