/* Owned host-only copied input admission. Never submits a hardware command. */
#ifndef S24_POWER_OBSERVE_H
#define S24_POWER_OBSERVE_H
#include <stddef.h>
#include <stdint.h>
#define POWER_MESSAGE_BYTES 16u
#define POWER_TMU_ZONES 8u
#define POWER_DVFS_DOMAINS 33u
#define POWER_FVMAP_COPY_BYTES 8192u
#define POWER_SOURCE_S5E9945 1u /* pinned public source profile, not firmware ID */
enum power_result {
    POWER_OK=0, POWER_ARGUMENT, POWER_LENGTH, POWER_UNIT, POWER_UNSUPPORTED,
    POWER_UNAVAILABLE, POWER_TRANSPORT_ERROR, POWER_FIRMWARE_ERROR,
    POWER_STALE, POWER_CLOCK, POWER_OVERFLOW, POWER_BUSY, POWER_STOPPED,
    POWER_EXHAUSTED
};
enum power_kind { POWER_TMU=1, POWER_CLOCK_REQUEST=2, POWER_MEASURED_CLOCK=3, POWER_VOLTAGE=4 };
enum power_unit { POWER_CELSIUS_U8=1, POWER_KHZ_U32=2, POWER_MILLI_CELSIUS=3, POWER_HZ=4 };
enum power_transport { POWER_TRANSPORT_OK=0, POWER_TRANSPORT_MISSING=1, POWER_TRANSPORT_FAILED=2 };
struct power_value { uint64_t value; uint32_t kind, source_id, unit, status; };
struct power_policy {
    uint64_t max_age_ns; /* application freshness only, never a thermal limit */
    uint32_t profile, kind, source_id, epoch;
};
struct power_ticket { uint32_t epoch, generation; };
struct power_extent { uint32_t selected_index, reported_domain, levels, offset, bytes; };
struct power_observer {
    struct power_policy policy;
    struct power_ticket ticket;
    struct power_value sample;
    uint64_t start_ns, deadline_ns, last_ns, sample_ns;
    uint32_t waiting, valid, stopped, last_error;
};
#ifdef __cplusplus
extern "C" {
#endif
uint32_t power_decode_tmu(const uint8_t *,size_t,uint32_t,uint32_t,struct power_value *);
uint32_t power_decode_clock_request(const uint8_t *,size_t,uint32_t,uint32_t,struct power_value *);
/* Source table diagnostic only: not firmware discovery or an actuation ID. */
uint32_t power_source_domain_id(uint32_t,uint32_t *);
/* Copied public-profile FVMAP extent only; no rate/voltage value is consumed. */
uint32_t power_fvmap_extent(const uint8_t *,size_t,uint32_t,uint32_t,struct power_extent *);
/* Fresh/retired storage only; init cannot stop an external backend. */
uint32_t power_observer_init(struct power_observer *,const struct power_policy *);
/* Creates state.ticket for logical correlation, never a firmware request. */
uint32_t power_observer_begin(struct power_observer *,uint64_t);
uint32_t power_observer_accept(struct power_observer *,const struct power_ticket *,
    const uint8_t *,size_t,uint32_t,uint32_t,uint64_t,uint64_t);
uint32_t power_observer_read(struct power_observer *,uint64_t,struct power_value *);
/* Invalidates host observations; no hardware Stop/quiescence is implied. */
uint32_t power_observer_stop(struct power_observer *);
#ifdef __cplusplus
}
#endif
#endif
