/* Host tests for the SGPU timeline, against a fake sink and against the real backend core.
 * Hardware is a software fake. Passing says nothing about any GPU. */
#define main backend_tests_main
#include "test_backend.c"
#undef main
#include "sgpu_timeline.h"

#define EVENTS 4096u
enum { EV_RETIRE = 1, EV_FAULT = 2, EV_QUIESCED = 3 };

struct started { uint32_t ring, context, count; uint64_t counter; struct sgpu_be_ib ibs[SGPU_MAX_IBS]; };
struct event { int kind; uint64_t value; };

struct harness {
    int locked, threaded, fail_start, retire_status, quiesced_status;
    unsigned start_calls, event_count;
    uint64_t now, counter[SGPU_TL_MAX_RINGS];
    struct started started[EVENTS];
    struct event events[EVENTS];
    void (*on_retire)(uint64_t);
    pthread_mutex_t mutex;
    _Atomic uint64_t latest_counter;
    atomic_int stop;
};

static _Alignas(16) uint8_t tl_storage[1u << 20];
static struct harness H;
static struct sgpu_timeline *const TL = (struct sgpu_timeline *)tl_storage;
static const struct sgpu_be_ib IB = { 0x1000, 64, 0 };

static void h_held(void) { if (!H.threaded) CHECK(H.locked); }
static void h_lock(void *hw)
{
    (void)hw;
    if (H.threaded) { pthread_mutex_lock(&H.mutex); return; }
    CHECK(!H.locked);
    H.locked = 1;
}
static void h_unlock(void *hw)
{
    (void)hw;
    if (H.threaded) { pthread_mutex_unlock(&H.mutex); return; }
    CHECK(H.locked);
    H.locked = 0;
}
static uint64_t h_now(void *hw)
{
    struct timespec t;
    (void)hw;
    h_held();
    if (!H.threaded) return H.now;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static int h_start(void *hw, uint32_t ring, uint32_t context, const struct sgpu_be_ib *ibs, uint32_t count, uint64_t counter)
{
    uint32_t i;
    (void)hw;
    h_held();
    if (H.fail_start) return -1;
    if (H.threaded) { atomic_store(&H.latest_counter, counter); ++H.start_calls; return 0; }
    CHECK(H.start_calls < EVENTS);
    H.started[H.start_calls].ring = ring;
    H.started[H.start_calls].context = context;
    H.started[H.start_calls].count = count;
    H.started[H.start_calls].counter = counter;
    for (i = 0; i < count; ++i) H.started[H.start_calls].ibs[i] = ibs[i];
    ++H.start_calls;
    return 0;
}
static uint64_t h_read_counter(void *hw, uint32_t ring)
{
    (void)hw;
    h_held();
    if (H.threaded) return atomic_load(&H.latest_counter);
    return H.counter[ring];
}
static const struct sgpu_tl_hw HW = { h_lock, h_unlock, h_now, h_start, h_read_counter };

static void record(int kind, uint64_t value)
{
    CHECK(!H.locked);
    CHECK(H.event_count < EVENTS);
    H.events[H.event_count].kind = kind;
    H.events[H.event_count].value = value;
    ++H.event_count;
}
static int s_retire(void *context, uint64_t sequence, uint32_t reason)
{
    (void)context;
    CHECK_EQ(reason, SGPU_BE_REASON_NONE);
    record(EV_RETIRE, sequence);
    if (H.on_retire) H.on_retire(sequence);
    return H.retire_status;
}
static void s_fault(void *context, uint32_t reason) { (void)context; record(EV_FAULT, reason); }
static int s_quiesced(void *context) { (void)context; record(EV_QUIESCED, 0); return H.quiesced_status; }
static const struct sgpu_tl_sink SINK = { NULL, s_retire, s_fault, s_quiesced };

static struct sgpu_tl_config cfg(uint32_t rings, uint32_t depth, uint32_t bits)
{
    struct sgpu_tl_config c;
    memset(&c, 0, sizeof c);
    c.rings = rings; c.depth = depth; c.counter_bits = bits; c.job_timeout_ns = 1000;
    return c;
}
static void reset_h(void) { memset(&H, 0, sizeof H); H.now = 5000; }
static void tl_with(const struct sgpu_tl_config *c)
{
    reset_h();
    CHECK(sgpu_timeline_storage_size() <= sizeof tl_storage);
    CHECK_EQ(sgpu_timeline_init(TL, c, &HW, &H, &SINK), SGPU_TL_OK);
}
static void tl_setup(uint32_t rings, uint32_t depth, uint32_t bits) { struct sgpu_tl_config c = cfg(rings, depth, bits); tl_with(&c); }
static int sub(uint32_t ring, uint64_t sequence, const uint64_t *waits, uint32_t n) { return sgpu_timeline_submit(TL, ring, 7, &IB, 1, waits, n, sequence); }
static int obs(uint32_t ring, uint64_t value) { H.counter[ring % SGPU_TL_MAX_RINGS] = value; return sgpu_timeline_observe(TL, ring); }
static struct sgpu_tl_stats stats(void) { struct sgpu_tl_stats s; sgpu_timeline_stats(TL, &s); return s; }
static void event_is(unsigned i, int kind, uint64_t value) { CHECK(i < H.event_count); CHECK_EQ(H.events[i].kind, kind); CHECK_EQ(H.events[i].value, value); }

static void test_tl_init(void)
{
    struct sgpu_tl_config good = cfg(2, 4, 32), c;
    struct sgpu_tl_hw hw;
    struct sgpu_tl_sink sink;
    reset_h();
#define BAD(cfgp, hwp, sinkp) CHECK_EQ(sgpu_timeline_init(TL, cfgp, hwp, &H, sinkp), SGPU_TL_ARGUMENT)
    CHECK_EQ(sgpu_timeline_init(NULL, &good, &HW, &H, &SINK), SGPU_TL_ARGUMENT);
    BAD(NULL, &HW, &SINK); BAD(&good, NULL, &SINK); BAD(&good, &HW, NULL);
    hw = HW; hw.lock = NULL; BAD(&good, &hw, &SINK);
    hw = HW; hw.unlock = NULL; BAD(&good, &hw, &SINK);
    hw = HW; hw.now_ns = NULL; BAD(&good, &hw, &SINK);
    hw = HW; hw.start = NULL; BAD(&good, &hw, &SINK);
    hw = HW; hw.read_counter = NULL; BAD(&good, &hw, &SINK);
    sink = SINK; sink.retire = NULL; BAD(&good, &HW, &sink);
    sink = SINK; sink.fault = NULL; BAD(&good, &HW, &sink);
    sink = SINK; sink.quiesced = NULL; BAD(&good, &HW, &sink);
    c = good; c.rings = 0; BAD(&c, &HW, &SINK);
    c = good; c.rings = SGPU_TL_MAX_RINGS + 1; BAD(&c, &HW, &SINK);
    c = good; c.depth = 0; BAD(&c, &HW, &SINK);
    c = good; c.depth = SGPU_TL_MAX_DEPTH + 1; BAD(&c, &HW, &SINK);
    c = good; c.counter_bits = 31; BAD(&c, &HW, &SINK);
    c = good; c.counter_bits = 33; BAD(&c, &HW, &SINK);
    c = good; c.job_timeout_ns = 0; BAD(&c, &HW, &SINK);
    c = good; c.initial_counter[1] = UINT64_C(1) << 32; BAD(&c, &HW, &SINK);
#undef BAD
    c = good; c.rings = 1; c.initial_counter[1] = UINT64_C(1) << 32;
    CHECK_EQ(sgpu_timeline_init(TL, &c, &HW, &H, &SINK), SGPU_TL_OK);
    c = cfg(SGPU_TL_MAX_RINGS, SGPU_TL_MAX_DEPTH, 64);
    CHECK_EQ(sgpu_timeline_init(TL, &c, &HW, &H, &SINK), SGPU_TL_OK);
}

static void test_tl_start_and_retire(void)
{
    struct sgpu_be_ib ibs[2] = { { 0x1000, 64, 0 }, { 0x2000, 32, 1 } };
    tl_setup(1, 4, 32);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 9, ibs, 2, NULL, 0, 11), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(H.started[0].ring, 0);
    CHECK_EQ(H.started[0].context, 9);
    CHECK_EQ(H.started[0].count, 2);
    CHECK_EQ(H.started[0].counter, 1);
    CHECK_EQ(H.started[0].ibs[1].va, 0x2000);
    CHECK_EQ(H.event_count, 0);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 1);
    event_is(0, EV_RETIRE, 11);
    CHECK_EQ(stats().started, 1);
    CHECK_EQ(stats().completed, 1);
}

static void test_tl_ibs_copied(void)
{
    struct sgpu_be_ib ibs[1] = { { 0x7000, 64, 0 } };
    uint64_t waits[1] = { 1 };
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 3, ibs, 1, waits, 1, 2), SGPU_TL_OK);
    ibs[0].va = 0xBAD0; waits[0] = 99;
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(H.started[1].ibs[0].va, 0x7000);
    CHECK_EQ(H.started[1].context, 3);
}

static void test_tl_counters_from_initial(void)
{
    struct sgpu_tl_config c = cfg(2, 4, 32);
    c.initial_counter[0] = 41; c.initial_counter[1] = 500;
    tl_with(&c);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, 3, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.started[0].counter, 42);
    CHECK_EQ(H.started[1].counter, 43);
    CHECK_EQ(H.started[2].counter, 501);
    CHECK_EQ(H.started[2].ring, 1);
    CHECK_EQ(obs(0, 42), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 1);
    event_is(0, EV_RETIRE, 1);
    CHECK_EQ(obs(1, 501), SGPU_TL_OK);
    event_is(1, EV_RETIRE, 3);
    CHECK_EQ(obs(0, 43), SGPU_TL_OK);
    event_is(2, EV_RETIRE, 2);
}

static void test_tl_batch_retires_in_order(void)
{
    tl_setup(1, 8, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 3, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 2);
    event_is(0, EV_RETIRE, 1);
    event_is(1, EV_RETIRE, 2);
    CHECK_EQ(obs(0, 3), SGPU_TL_OK);
    event_is(2, EV_RETIRE, 3);
    CHECK_EQ(stats().completed, 3);
}

static void test_tl_ring_indices_wrap(void)
{
    unsigned i;
    tl_setup(1, 4, 32);
    for (i = 1; i <= 2u * SGPU_TL_MAX_DEPTH + 10u; ++i) {
        CHECK_EQ(sub(0, i, NULL, 0), SGPU_TL_OK);
        CHECK_EQ(obs(0, i), SGPU_TL_OK);
        CHECK_EQ(H.event_count, 1);
        event_is(0, EV_RETIRE, i);
        H.event_count = 0;
        H.start_calls = 0;
    }
}

static void test_tl_report_queue_wraps(void)
{
    unsigned i, round;
    uint64_t sequence = 0;
    tl_setup(1, 200, 32);
    for (round = 0; round < 6; ++round) {
        for (i = 0; i < 150; ++i) CHECK_EQ(sub(0, ++sequence, NULL, 0), SGPU_TL_OK);
        H.event_count = 0;
        CHECK_EQ(obs(0, sequence), SGPU_TL_OK);
        CHECK_EQ(H.event_count, 150);
        for (i = 0; i < 150; ++i) event_is(i, EV_RETIRE, sequence - 149 + i);
    }
}

static void test_tl_wrap_32(void)
{
    struct sgpu_tl_config c = cfg(1, 4, 32);
    c.initial_counter[0] = UINT32_MAX;
    tl_with(&c);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.started[0].counter, 0);
    CHECK_EQ(H.started[1].counter, 1);
    CHECK_EQ(obs(0, 0), SGPU_TL_OK);
    event_is(0, EV_RETIRE, 1);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    event_is(1, EV_RETIRE, 2);
}

static void test_tl_counter_64(void)
{
    struct sgpu_tl_config c = cfg(1, 4, 64);
    uint64_t start = UINT64_C(0x1234567800000000);
    c.initial_counter[0] = start;
    tl_with(&c);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.started[0].counter, start + 1);
    CHECK_EQ(obs(0, start + 1), SGPU_TL_OK);
    event_is(0, EV_RETIRE, 1);
    c.initial_counter[0] = UINT64_MAX;
    tl_with(&c);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.started[0].counter, 0);
    CHECK_EQ(obs(0, 0), SGPU_TL_OK);
    event_is(0, EV_RETIRE, 1);
}

static void bad_counter_faulted(int retired_before)
{
    CHECK_EQ(stats().bad_counters, 1);
    CHECK_EQ((int)H.event_count, retired_before + 1);
    event_is((unsigned)retired_before, EV_FAULT, SGPU_BE_REASON_FAULT);
}

static void test_tl_bad_counters(void)
{
    /* Upper bits set are impossible for a 32-bit counter, even when the low bits look right. */
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(obs(0, (UINT64_C(1) << 32) | 1u), SGPU_TL_BAD_COUNTER);
    bad_counter_faulted(0);

    /* Further ahead than what is running. */
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(obs(0, 3), SGPU_TL_BAD_COUNTER);
    bad_counter_faulted(0);

    /* Exactly what is running is accepted. */
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    CHECK_EQ(stats().bad_counters, 0);

    /* A regression looks like a huge forward distance. */
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(obs(0, 0), SGPU_TL_BAD_COUNTER);
    bad_counter_faulted(1);

    /* Nothing running means any change is impossible. */
    tl_setup(1, 4, 32);
    CHECK_EQ(obs(0, 1), SGPU_TL_BAD_COUNTER);
    bad_counter_faulted(0);
}

static void test_tl_spurious_observation(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(obs(0, 0), SGPU_TL_OK);
    CHECK_EQ(stats().spurious_observations, 1);
    CHECK_EQ(H.event_count, 0);
    CHECK_EQ(obs(5, 0), SGPU_TL_ARGUMENT);
}

static void test_tl_nothing_retires_after_fault(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_fault(TL, 2), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 1);
    event_is(0, EV_FAULT, 2);
    CHECK_EQ(obs(0, 1), SGPU_TL_STOPPED);
    CHECK_EQ(H.event_count, 1);
    CHECK_EQ(stats().ignored_after_fault, 1);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_STOPPED);
    CHECK_EQ(H.start_calls, 1);
}

static void test_tl_wait_same_ring(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, waits, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(H.started[1].counter, 2);
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    event_is(0, EV_RETIRE, 1);
    event_is(1, EV_RETIRE, 2);
}

static void test_tl_wait_across_rings(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(2, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, 2, waits, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(H.started[1].ring, 1);
    CHECK_EQ(H.started[1].counter, 1);
}

static void test_tl_all_waits_required(void)
{
    uint64_t waits[2] = { 1, 2 };
    tl_setup(2, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 3, waits, 2), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(obs(1, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 3);
}

static void test_tl_wait_on_waiting_job(void)
{
    uint64_t first[1] = { 1 }, second[1] = { 2 };
    tl_setup(2, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, 2, first, 1), SGPU_TL_OK);
    CHECK_EQ(sub(0, 3, second, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(H.started[1].ring, 1);
    CHECK_EQ(obs(1, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 3);
    CHECK_EQ(H.started[2].ring, 0);
}

static void test_tl_freed_wait_slot_reused(void)
{
    uint64_t waits[2] = { 1, 2 };
    tl_setup(3, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(2, 3, waits, 2), SGPU_TL_OK);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    /* The new job takes the slot of finished job 1; job 3 must not wait for it. */
    CHECK_EQ(sub(0, 4, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 3);
    CHECK_EQ(obs(1, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 4);
    CHECK_EQ(H.started[3].ring, 2);
}

static void test_tl_waiting_queue_wraps(void)
{
    uint64_t sequence = 0, waits[1];
    unsigned i, round;
    tl_setup(2, 200, 32);
    for (round = 0; round < 6; ++round) {
        uint64_t gate = ++sequence;
        CHECK_EQ(sub(1, gate, NULL, 0), SGPU_TL_OK);
        waits[0] = gate;
        H.start_calls = 0;
        H.event_count = 0;
        for (i = 0; i < 150; ++i) CHECK_EQ(sub(0, ++sequence, waits, 1), SGPU_TL_OK);
        CHECK_EQ(H.start_calls, 0);
        CHECK_EQ(obs(1, round + 1u), SGPU_TL_OK);
        CHECK_EQ(H.start_calls, 150);
        CHECK_EQ(obs(0, sequence - round - 1u), SGPU_TL_OK);
        CHECK_EQ(H.event_count, 151);
        for (i = 0; i < 150; ++i) event_is(i + 1u, EV_RETIRE, gate + 1u + i);
    }
}

static void test_tl_blocked_head_holds_followers(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(2, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, 2, waits, 1), SGPU_TL_OK);
    CHECK_EQ(sub(1, 3, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 3);
    CHECK_EQ(H.started[1].counter, 1);
    CHECK_EQ(H.started[2].counter, 2);
}

static uint64_t submitted_from_hook;
static void submit_waiting_on_retired(uint64_t sequence)
{
    uint64_t waits[1];
    waits[0] = sequence;
    H.on_retire = NULL;
    CHECK_EQ(sub(0, submitted_from_hook, waits, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
}

static void test_tl_wait_on_gone_or_reporting_job(void)
{
    uint64_t waits[2] = { 40, 41 };
    tl_setup(1, 4, 32);
    /* Never known here: already reported long ago. */
    CHECK_EQ(sub(0, 50, waits, 2), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 1);
    /* Finished and being reported: must not hold the new job back. */
    H.on_retire = submit_waiting_on_retired;
    submitted_from_hook = 51;
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    event_is(1, EV_RETIRE, 51);
}

static void test_tl_wait_table_capacity(void)
{
    uint64_t waits[SGPU_MAX_DEPS];
    unsigned i;
    tl_setup(1, 64, 32);
    for (i = 0; i < SGPU_MAX_DEPS; ++i) { waits[i] = i + 1u; CHECK_EQ(sub(0, i + 1u, NULL, 0), SGPU_TL_OK); }
    CHECK_EQ(sub(0, SGPU_MAX_DEPS + 1u, waits, SGPU_MAX_DEPS), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, SGPU_MAX_DEPS);
    CHECK_EQ(obs(0, SGPU_MAX_DEPS - 1u), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, SGPU_MAX_DEPS);
    CHECK_EQ(obs(0, SGPU_MAX_DEPS), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, SGPU_MAX_DEPS + 1u);
}

static void test_tl_depth_limits(void)
{
    tl_setup(1, 2, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    /* Depth bounds only running work; queued work is bounded by the job table. */
    CHECK_EQ(sub(0, 3, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 4, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 5, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.start_calls, 3);
    CHECK_EQ(H.started[2].counter, 3);
}

static void test_tl_job_table_exhausted(void)
{
    struct sgpu_tl_config c = cfg(3, SGPU_TL_MAX_DEPTH, 32);
    uint64_t sequence = 0;
    unsigned i;
    tl_with(&c);
    for (i = 0; i < 2u * SGPU_TL_MAX_DEPTH; ++i) CHECK_EQ(sub(0, ++sequence, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(1, ++sequence, NULL, 0), SGPU_TL_FULL);
    CHECK_EQ(H.start_calls, SGPU_TL_MAX_DEPTH);
    /* A rejected sequence is not consumed. */
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(sub(1, sequence, NULL, 0), SGPU_TL_OK);
}

static void test_tl_submit_checks(void)
{
    struct sgpu_be_ib ibs[SGPU_MAX_IBS + 1];
    uint64_t waits[SGPU_MAX_DEPS + 1];
    memset(ibs, 0, sizeof ibs);
    memset(waits, 0, sizeof waits);
    tl_setup(2, 4, 32);
    CHECK_EQ(sgpu_timeline_submit(TL, 2, 1, ibs, 1, NULL, 0, 1), SGPU_TL_ARGUMENT);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 1, NULL, 1, NULL, 0, 1), SGPU_TL_ARGUMENT);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 1, ibs, 0, NULL, 0, 1), SGPU_TL_ARGUMENT);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 1, ibs, SGPU_MAX_IBS + 1, NULL, 0, 1), SGPU_TL_ARGUMENT);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 1, ibs, 1, waits, SGPU_MAX_DEPS + 1, 1), SGPU_TL_ARGUMENT);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 1, ibs, 1, NULL, 1, 1), SGPU_TL_ARGUMENT);
    waits[0] = 1;
    CHECK_EQ(sub(0, 1, waits, 1), SGPU_TL_ARGUMENT);
    waits[0] = 2;
    CHECK_EQ(sub(0, 1, waits, 1), SGPU_TL_ARGUMENT);
    CHECK_EQ(H.start_calls, 0);
    CHECK_EQ(sub(0, 5, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 5, NULL, 0), SGPU_TL_ARGUMENT);
    CHECK_EQ(sub(0, 4, NULL, 0), SGPU_TL_ARGUMENT);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(sub(0, 6, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_submit(TL, 0, 1, ibs, SGPU_MAX_IBS, NULL, 0, 7), SGPU_TL_OK);
}

static void test_tl_own_start_failure(void)
{
    unsigned i;
    tl_setup(1, 4, 32);
    H.fail_start = 1;
    for (i = 0; i < SGPU_TL_MAX_JOBS + 16u; ++i) CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_START_FAILED);
    CHECK_EQ(stats().start_failures, SGPU_TL_MAX_JOBS + 16u);
    CHECK_EQ(H.event_count, 0);
    H.fail_start = 0;
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(H.started[0].counter, 1);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    event_is(0, EV_RETIRE, 1);
}

static void test_tl_queued_start_failure_faults(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, waits, 1), SGPU_TL_OK);
    H.fail_start = 1;
    CHECK_EQ(obs(0, 1), SGPU_TL_START_FAILED);
    CHECK_EQ(H.event_count, 2);
    event_is(0, EV_RETIRE, 1);
    event_is(1, EV_FAULT, SGPU_BE_REASON_FAULT);
    CHECK_EQ(sub(0, 3, NULL, 0), SGPU_TL_STOPPED);
    CHECK_EQ(stats().start_failures, 1);
}

static void test_tl_queued_failure_stops_other_rings(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(2, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, waits, 1), SGPU_TL_OK);
    CHECK_EQ(sub(1, 3, waits, 1), SGPU_TL_OK);
    H.fail_start = 1;
    CHECK_EQ(obs(0, 1), SGPU_TL_START_FAILED);
    H.fail_start = 0;
    CHECK_EQ(stats().start_failures, 1);
    CHECK_EQ(H.start_calls, 1);
}

static void test_tl_timeout_measures_head(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    H.now = 5900;
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    H.now = 5999;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_OK);
    /* The second start must not have pushed back the head's deadline. */
    H.now = 5950;
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    H.now = 6949;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_OK);
    H.now = 6950;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_TIMED_OUT);
    CHECK_EQ(H.event_count, 2);
    event_is(1, EV_FAULT, SGPU_BE_REASON_FAULT);
    CHECK_EQ(stats().timeouts, 1);
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_STOPPED);
    CHECK_EQ(H.event_count, 2);
    CHECK_EQ(stats().timeouts, 1);
}

static void test_tl_timeout_uses_first_start(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    H.now = 5900;
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    H.now = 6000;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_TIMED_OUT);
}

static void test_tl_timeout_after_idle(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    H.now = 5100;
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    H.now = 100000;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    H.now = 100500;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_OK);
}

static void test_tl_timeout_clock_and_rings(void)
{
    tl_setup(2, 4, 32);
    CHECK_EQ(sub(1, 1, NULL, 0), SGPU_TL_OK);
    H.now = 4000;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_OK);
    H.now = 6000;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_TIMED_OUT);
}

static void test_tl_fault_reasons(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sgpu_timeline_fault(TL, 0), SGPU_TL_OK);
    event_is(0, EV_FAULT, SGPU_BE_REASON_FAULT);
    CHECK_EQ(sgpu_timeline_fault(TL, 2), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 1);
    tl_setup(1, 4, 32);
    CHECK_EQ(sgpu_timeline_fault(TL, 2), SGPU_TL_OK);
    event_is(0, EV_FAULT, 2);
}

static void test_tl_note_fault_defers_the_sink(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, waits, 1), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_note_fault(TL, 0), SGPU_TL_OK);
    /* Callable under the backend lock, so it must not reach the sink. */
    CHECK_EQ(H.event_count, 0);
    /* Queued work must not start on a device already known to have failed. */
    CHECK_EQ(obs(0, 1), SGPU_TL_STOPPED);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(H.event_count, 1);
    event_is(0, EV_FAULT, SGPU_BE_REASON_FAULT);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    event_is(1, EV_QUIESCED, 0);
    /* A timer alone also delivers it, and the first reason is kept. */
    tl_setup(1, 4, 32);
    CHECK_EQ(sgpu_timeline_note_fault(TL, 2), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_note_fault(TL, 1), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 0);
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_STOPPED);
    CHECK_EQ(H.event_count, 1);
    event_is(0, EV_FAULT, 2);
}

static void test_tl_quiesced_needs_fault(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_NOT_FAULTED);
    CHECK_EQ(H.event_count, 0);
    CHECK_EQ(sgpu_timeline_fault(TL, 1), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 2);
    event_is(0, EV_FAULT, 1);
    event_is(1, EV_QUIESCED, 0);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 2);
    CHECK_EQ(stats().quiesce_rejected, 0);
    tl_setup(1, 4, 32);
    H.quiesced_status = -1;
    CHECK_EQ(sgpu_timeline_fault(TL, 1), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    CHECK_EQ(stats().quiesce_rejected, 1);
}

static void fault_and_quiesce_from_hook(uint64_t sequence)
{
    (void)sequence;
    H.on_retire = NULL;
    CHECK_EQ(sgpu_timeline_fault(TL, 2), SGPU_TL_OK);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 1);
}

static void test_tl_delivery_order(void)
{
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    H.on_retire = fault_and_quiesce_from_hook;
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 4);
    event_is(0, EV_RETIRE, 1);
    event_is(1, EV_RETIRE, 2);
    event_is(2, EV_FAULT, 2);
    event_is(3, EV_QUIESCED, 0);
}

static void observe_second_from_hook(uint64_t sequence)
{
    (void)sequence;
    H.on_retire = NULL;
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    /* A nested observation queues behind the active reporter. */
    CHECK_EQ(H.event_count, 1);
}

static void test_tl_nested_observation_keeps_order(void)
{
    uint64_t waits[1] = { 1 };
    tl_setup(1, 4, 32);
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, waits, 1), SGPU_TL_OK);
    H.on_retire = observe_second_from_hook;
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    CHECK_EQ(H.event_count, 2);
    event_is(0, EV_RETIRE, 1);
    event_is(1, EV_RETIRE, 2);
}

static void test_tl_unknown_retirement_counted(void)
{
    tl_setup(1, 4, 32);
    H.retire_status = -1;
    CHECK_EQ(sub(0, 1, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(sub(0, 2, NULL, 0), SGPU_TL_OK);
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    CHECK_EQ(stats().unknown_retirements, 2);
    CHECK_EQ(H.event_count, 2);
}

/* ---- The same module driving the real backend core. ---- */
static int be_submit(void *hw, uint32_t context, const struct sgpu_be_ib *ibs, uint32_t count, const uint64_t *waits, uint32_t wait_count, uint64_t sequence)
{
    (void)hw;
    fake_held();
    ++F.submit_calls;
    if (F.fail_submit) return -1;
    return sgpu_timeline_submit(TL, 0, context, ibs, count, waits, wait_count, sequence);
}
static int core_retire(void *context, uint64_t sequence, uint32_t reason) { (void)context; return sgpu_backend_retire(BE, sequence, reason); }
static void core_fault(void *context, uint32_t reason) { (void)context; sgpu_backend_fault(BE, reason); }
static int core_quiesced(void *context) { (void)context; return sgpu_backend_quiesced(BE); }
static const struct sgpu_tl_sink CORE_SINK = { NULL, core_retire, core_fault, core_quiesced };

static void core_init(uint32_t depth, uint64_t timeout)
{
    struct sgpu_be_ops ops = OPS;
    struct sgpu_be_config c = config_verified(4096, KB(1024), KB(32));
    struct sgpu_tl_config t = cfg(1, depth, 32);
    t.job_timeout_ns = timeout;
    ops.submit = be_submit;
    CHECK_EQ(sgpu_backend_init(BE, &c, &ops, &F), SGPU_OK);
    CHECK_EQ(sgpu_timeline_init(TL, &t, &HW, &H, &CORE_SINK), SGPU_TL_OK);
}

static void fence_is(struct fixture f, uint64_t fence, uint32_t expected_state, uint32_t expected_reason)
{
    uint32_t state = 0, reason = 0;
    CHECK_EQ(wait_fence(f.client, fence, 0, &state, &reason), SGPU_OK);
    CHECK_EQ(state, expected_state);
    CHECK_EQ(reason, expected_reason);
}

static void test_core_retires_through_timeline(void)
{
    struct fixture f;
    uint64_t a, b, sa, sb;
    reset_fake();
    reset_h();
    core_init(4, 1000000);
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &a, &sa), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &a, 1, &b, &sb), SGPU_OK);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(wait_fence(f.client, a, 0, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(obs(0, 1), SGPU_TL_OK);
    fence_is(f, a, SGPU_RETIRED, 0);
    CHECK_EQ(H.start_calls, 2);
    CHECK_EQ(wait_fence(f.client, b, 0, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(obs(0, 2), SGPU_TL_OK);
    fence_is(f, b, SGPU_RETIRED, 0);
    CHECK_EQ(stats().unknown_retirements, 0);
}

static void test_core_one_client_cannot_fill_a_ring(void)
{
    struct fixture a, b;
    uint64_t previous = 0, fence, s;
    unsigned i;
    reset_fake();
    reset_h();
    core_init(1, 1000000);
    a = make_fixture(VA);
    b = make_fixture(VA + (UINT64_C(1) << 24));
    for (i = 0; i < SGPU_BE_CLIENT_MAX_FENCES; ++i) {
        CHECK_EQ(submit_one(a.client, a.context, a.bo, RW, i ? &previous : NULL, i ? 1 : 0, &fence, &s), SGPU_OK);
        previous = fence;
    }
    /* The core's quota stops the first client; the ring still takes the second. */
    CHECK_EQ(submit_one(a.client, a.context, a.bo, RW, &previous, 1, NULL, NULL), SGPU_LIMIT);
    CHECK_EQ(submit_one(b.client, b.context, b.bo, RW, NULL, 0, &fence, &s), SGPU_OK);
    CHECK_EQ(H.start_calls, 1);
}

static int be_tlb(void *hw, uint32_t context, uint64_t va, uint64_t bytes)
{
    (void)va; (void)bytes; (void)context; (void)hw;
    fake_held();
    ++F.tlb_calls;
    if (!F.fail_tlb) return 0;
    /* What a real sgpu_be_ops layer must do: it holds the backend lock here. */
    CHECK_EQ(sgpu_timeline_note_fault(TL, SGPU_BE_REASON_FAULT), SGPU_TL_OK);
    return -1;
}

static void test_core_quarantine_reaches_timeline(void)
{
    struct sgpu_be_ops ops = OPS;
    struct sgpu_be_config c = config_verified(4096, KB(1024), KB(32));
    struct sgpu_tl_config t = cfg(1, 4, 32);
    struct fixture f;
    uint64_t a, b, idle, s;
    reset_fake();
    reset_h();
    ops.submit = be_submit;
    ops.tlb_flush = be_tlb;
    CHECK_EQ(sgpu_backend_init(BE, &c, &ops, &F), SGPU_OK);
    CHECK_EQ(sgpu_timeline_init(TL, &t, &HW, &H, &CORE_SINK), SGPU_TL_OK);
    f = make_fixture(VA);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &idle, NULL), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &a, &s), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &a, 1, &b, &s), SGPU_OK);
    CHECK_EQ(H.start_calls, 1);
    F.fail_tlb = 1;
    CHECK_EQ(gpu_map(f.client, f.context, idle, VA + KB(64), 0, KB(4), SGPU_READ), SGPU_BACKEND_ERROR);
    F.fail_tlb = 0;
    /* Without the fault note this would start b on a quarantined device. */
    CHECK_EQ(obs(0, 1), SGPU_TL_STOPPED);
    CHECK_EQ(H.start_calls, 1);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    CHECK_EQ(stats().quiesce_rejected, 0);
    fence_is(f, a, SGPU_RETIRED_ERROR, SGPU_BE_REASON_QUIESCED);
    fence_is(f, b, SGPU_RETIRED_ERROR, SGPU_BE_REASON_QUIESCED);
}

static void test_core_bad_counter_then_quiesce(void)
{
    struct fixture f;
    uint64_t a, b, s;
    reset_fake();
    reset_h();
    core_init(4, 1000000);
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &a, &s), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &a, 1, &b, &s), SGPU_OK);
    CHECK_EQ(obs(0, 99), SGPU_TL_BAD_COUNTER);
    /* Nothing retired: the fence stays pending and references stay held. */
    CHECK_EQ(wait_fence(f.client, a, 1000, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &b, 1, NULL, NULL), SGPU_STOPPED);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_STOPPED);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    fence_is(f, a, SGPU_RETIRED_ERROR, SGPU_BE_REASON_QUIESCED);
    fence_is(f, b, SGPU_RETIRED_ERROR, SGPU_BE_REASON_QUIESCED);
    CHECK_EQ(stats().quiesce_rejected, 0);
}

static void test_core_timeout_then_quiesce(void)
{
    struct fixture f;
    uint64_t a, s;
    reset_fake();
    reset_h();
    core_init(4, 1000);
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &a, &s), SGPU_OK);
    H.now += 1000;
    CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_TIMED_OUT);
    CHECK_EQ(wait_fence(f.client, a, 1000, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(sgpu_timeline_quiesced(TL), SGPU_TL_OK);
    fence_is(f, a, SGPU_RETIRED_ERROR, SGPU_BE_REASON_QUIESCED);
}

#define TL_THREADS 3
#define TL_OBSERVERS 2 /* Two observers: a stale counter would fault the device. */
#define TL_ROUNDS 300

static void *tl_submitter(void *opaque)
{
    struct fixture *f = (struct fixture *)opaque;
    unsigned i;
    for (i = 0; i < TL_ROUNDS; ++i) {
        uint64_t fence, sequence;
        uint32_t state = 0, reason = 0, status;
        unsigned tries = 0;
        CHECK_EQ(submit_one(f->client, f->context, f->bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
        do status = wait_fence(f->client, fence, SGPU_MAX_WAIT_NS, &state, &reason);
        while (status == SGPU_TIMEOUT && ++tries < 100);
        CHECK_EQ(status, SGPU_OK);
        CHECK_EQ(state, SGPU_RETIRED);
    }
    return NULL;
}

static void *tl_observer(void *opaque)
{
    (void)opaque;
    while (!atomic_load(&H.stop)) {
        CHECK_EQ(sgpu_timeline_observe(TL, 0), SGPU_TL_OK);
        CHECK_EQ(sgpu_timeline_tick(TL), SGPU_TL_OK);
    }
    return NULL;
}

static void test_core_threaded(void)
{
    struct fixture fixtures[TL_THREADS];
    pthread_t submitters[TL_THREADS], observers[TL_OBSERVERS];
    pthread_condattr_t attr;
    unsigned i;
    reset_fake();
    reset_h();
    F.threaded = 1;
    H.threaded = 1;
    pthread_mutex_init(&F.mutex, NULL);
    pthread_mutex_init(&H.mutex, NULL);
    pthread_condattr_init(&attr);
    pthread_condattr_setclock(&attr, CLOCK_MONOTONIC);
    pthread_cond_init(&F.cond, &attr);
    pthread_condattr_destroy(&attr);
    core_init(8, UINT64_MAX);
    for (i = 0; i < TL_THREADS; ++i) fixtures[i] = make_fixture(VA + (uint64_t)i * (UINT64_C(1) << 24));
    for (i = 0; i < TL_OBSERVERS; ++i) CHECK_EQ(pthread_create(&observers[i], NULL, tl_observer, NULL), 0);
    for (i = 0; i < TL_THREADS; ++i) CHECK_EQ(pthread_create(&submitters[i], NULL, tl_submitter, &fixtures[i]), 0);
    for (i = 0; i < TL_THREADS; ++i) pthread_join(submitters[i], NULL);
    atomic_store(&H.stop, 1);
    for (i = 0; i < TL_OBSERVERS; ++i) pthread_join(observers[i], NULL);
    CHECK_EQ(stats().completed, TL_THREADS * TL_ROUNDS);
    CHECK_EQ(stats().unknown_retirements, 0);
    CHECK_EQ(stats().bad_counters, 0);
    pthread_mutex_destroy(&H.mutex);
    H.threaded = 0;
    teardown_threaded();
}

int main(void)
{
    void (*const tests[])(void) = {
        test_tl_init, test_tl_start_and_retire, test_tl_ibs_copied, test_tl_counters_from_initial, test_tl_batch_retires_in_order,
        test_tl_ring_indices_wrap, test_tl_report_queue_wraps, test_tl_wrap_32, test_tl_counter_64, test_tl_bad_counters, test_tl_spurious_observation,
        test_tl_nothing_retires_after_fault, test_tl_wait_same_ring, test_tl_wait_across_rings, test_tl_all_waits_required, test_tl_wait_on_waiting_job,
        test_tl_freed_wait_slot_reused, test_tl_waiting_queue_wraps, test_tl_blocked_head_holds_followers, test_tl_wait_on_gone_or_reporting_job, test_tl_wait_table_capacity, test_tl_depth_limits, test_tl_job_table_exhausted,
        test_tl_submit_checks, test_tl_own_start_failure, test_tl_queued_start_failure_faults, test_tl_queued_failure_stops_other_rings, test_tl_timeout_measures_head,
        test_tl_timeout_uses_first_start, test_tl_timeout_after_idle, test_tl_timeout_clock_and_rings, test_tl_fault_reasons, test_tl_note_fault_defers_the_sink, test_tl_quiesced_needs_fault,
        test_tl_delivery_order, test_tl_nested_observation_keeps_order, test_tl_unknown_retirement_counted, test_core_retires_through_timeline, test_core_one_client_cannot_fill_a_ring, test_core_quarantine_reaches_timeline,
        test_core_bad_counter_then_quiesce, test_core_timeout_then_quiesce, test_core_threaded
    };
    size_t i;
    (void)backend_tests_main;
    for (i = 0; i < sizeof tests / sizeof tests[0]; ++i) tests[i]();
    printf("{\"tests\": %zu}\n", sizeof tests / sizeof tests[0]);
    return 0;
}
