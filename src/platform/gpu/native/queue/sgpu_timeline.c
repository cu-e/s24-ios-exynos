/* See sgpu_timeline.h. Freestanding C: no allocator, no libc. */
#include "sgpu_timeline.h"

enum { JOB_FREE = 0, JOB_ACTIVE = 1, JOB_DONE = 2 };
#define NO_JOB 0xFFFFu

struct tl_job {
    uint64_t sequence;
    uint64_t waits[SGPU_MAX_DEPS];
    struct sgpu_be_ib ibs[SGPU_MAX_IBS];
    uint16_t wait_slots[SGPU_MAX_DEPS];
    uint32_t state, hw_context, count, wait_count;
};

struct tl_ring {
    uint16_t waiting[SGPU_TL_MAX_JOBS], running[SGPU_TL_MAX_DEPTH];
    uint32_t waiting_head, waiting_count, running_head, running_count;
    uint64_t last_counter, head_since;
};

struct sgpu_timeline {
    struct sgpu_tl_config config;
    struct sgpu_tl_hw hw;
    void *hw_context;
    struct sgpu_tl_sink sink;
    uint64_t mask, last_sequence;
    struct sgpu_tl_stats stats;
    uint32_t report_head, report_count, faulted, fault_reason, fault_pending, quiesced, quiesce_pending, reporting;
    uint16_t report[SGPU_TL_MAX_JOBS];
    struct tl_ring rings[SGPU_TL_MAX_RINGS];
    struct tl_job jobs[SGPU_TL_MAX_JOBS];
};

static void zero_bytes(void *target, size_t bytes)
{
    unsigned char *p = (unsigned char *)target;
    while (bytes--) *p++ = 0;
}

size_t sgpu_timeline_storage_size(void) { return sizeof(struct sgpu_timeline); }

int sgpu_timeline_init(struct sgpu_timeline *tl, const struct sgpu_tl_config *config, const struct sgpu_tl_hw *hw, void *hw_context, const struct sgpu_tl_sink *sink)
{
    uint64_t mask;
    uint32_t i;
    if (!tl || !config || !hw || !sink) return SGPU_TL_ARGUMENT;
    if (!hw->lock || !hw->unlock || !hw->now_ns || !hw->start || !hw->read_counter) return SGPU_TL_ARGUMENT;
    if (!sink->retire || !sink->fault || !sink->quiesced) return SGPU_TL_ARGUMENT;
    if (!config->rings || config->rings > SGPU_TL_MAX_RINGS) return SGPU_TL_ARGUMENT;
    if (!config->depth || config->depth > SGPU_TL_MAX_DEPTH) return SGPU_TL_ARGUMENT;
    if (config->counter_bits != 32 && config->counter_bits != 64) return SGPU_TL_ARGUMENT;
    if (!config->job_timeout_ns) return SGPU_TL_ARGUMENT;
    mask = config->counter_bits == 64 ? UINT64_MAX : UINT32_MAX;
    for (i = 0; i < config->rings; ++i) if (config->initial_counter[i] & ~mask) return SGPU_TL_ARGUMENT;
    zero_bytes(tl, sizeof(*tl));
    tl->config = *config;
    tl->hw = *hw;
    tl->hw_context = hw_context;
    tl->sink = *sink;
    tl->mask = mask;
    for (i = 0; i < config->rings; ++i) tl->rings[i].last_counter = config->initial_counter[i];
    return SGPU_TL_OK;
}

static uint32_t find_active(const struct sgpu_timeline *tl, uint64_t sequence)
{
    uint32_t i;
    for (i = 0; i < SGPU_TL_MAX_JOBS; ++i) if (tl->jobs[i].state == JOB_ACTIVE && tl->jobs[i].sequence == sequence) return i;
    return NO_JOB;
}

static uint32_t free_slot(const struct sgpu_timeline *tl)
{
    uint32_t i;
    for (i = 0; i < SGPU_TL_MAX_JOBS; ++i) if (tl->jobs[i].state == JOB_FREE) return i;
    return NO_JOB;
}

/* A freed slot may hold a newer job; sequences never repeat, so the comparison is exact. */
static int job_blocked(const struct sgpu_timeline *tl, const struct tl_job *j)
{
    uint32_t i;
    for (i = 0; i < j->wait_count; ++i) {
        const struct tl_job *w = &tl->jobs[j->wait_slots[i]];
        if (w->sequence == j->waits[i] && w->state == JOB_ACTIVE) return 1;
    }
    return 0;
}

static uint32_t pop_waiting(struct tl_ring *r)
{
    uint32_t slot = r->waiting[r->waiting_head];
    r->waiting_head = (r->waiting_head + 1u) % SGPU_TL_MAX_JOBS;
    --r->waiting_count;
    return slot;
}

static uint32_t pop_running(struct tl_ring *r)
{
    uint32_t slot = r->running[r->running_head];
    r->running_head = (r->running_head + 1u) % SGPU_TL_MAX_DEPTH;
    --r->running_count;
    return slot;
}

static void mark_faulted(struct sgpu_timeline *tl, uint32_t reason)
{
    if (tl->faulted) return;
    tl->faulted = 1;
    tl->fault_reason = reason;
    tl->fault_pending = 1;
}

/* Zero when the head started, one when it cannot start yet, negative when hardware refused. */
static int start_head(struct sgpu_timeline *tl, struct tl_ring *r, uint32_t ring)
{
    uint32_t slot = r->waiting[r->waiting_head];
    struct tl_job *j = &tl->jobs[slot];
    uint64_t counter;
    if (job_blocked(tl, j) || r->running_count >= tl->config.depth) return 1;
    counter = (r->last_counter + r->running_count + 1u) & tl->mask;
    if (tl->hw.start(tl->hw_context, ring, j->hw_context, j->ibs, j->count, counter)) {
        ++tl->stats.start_failures;
        return -1;
    }
    (void)pop_waiting(r);
    if (!r->running_count) r->head_since = tl->hw.now_ns(tl->hw_context);
    r->running[(r->running_head + r->running_count) % SGPU_TL_MAX_DEPTH] = (uint16_t)slot;
    ++r->running_count;
    ++tl->stats.started;
    return 0;
}

/* A start here cannot be reported to its submitter any more, so a refusal faults the device. */
static void pump(struct sgpu_timeline *tl)
{
    uint32_t i;
    for (i = 0; i < tl->config.rings; ++i) {
        struct tl_ring *r = &tl->rings[i];
        while (r->waiting_count) {
            int result = start_head(tl, r, i);
            if (result > 0) break;
            if (result < 0) {
                mark_faulted(tl, SGPU_BE_REASON_FAULT);
                return;
            }
        }
    }
}

static int submit_locked(struct sgpu_timeline *tl, uint32_t ring, uint32_t hw_context, const struct sgpu_be_ib *ibs, uint32_t count, const uint64_t *waits, uint32_t wait_count, uint64_t sequence)
{
    struct tl_ring *r = &tl->rings[ring];
    struct tl_job *j;
    uint32_t i, slot, kept = 0;
    if (tl->faulted) return SGPU_TL_STOPPED;
    if (sequence <= tl->last_sequence) return SGPU_TL_ARGUMENT;
    for (i = 0; i < wait_count; ++i) if (waits[i] >= sequence) return SGPU_TL_ARGUMENT;
    slot = free_slot(tl);
    if (slot == NO_JOB) return SGPU_TL_FULL;
    j = &tl->jobs[slot];
    for (i = 0; i < wait_count; ++i) {
        uint32_t target = find_active(tl, waits[i]);
        /* Absent means it finished and no longer holds anything back. */
        if (target != NO_JOB) {
            j->waits[kept] = waits[i];
            j->wait_slots[kept] = (uint16_t)target;
            ++kept;
        }
    }
    for (i = 0; i < count; ++i) j->ibs[i] = ibs[i];
    j->sequence = sequence;
    j->hw_context = hw_context;
    j->count = count;
    j->wait_count = kept;
    j->state = JOB_ACTIVE;
    r->waiting[(r->waiting_head + r->waiting_count) % SGPU_TL_MAX_JOBS] = (uint16_t)slot;
    ++r->waiting_count;
    /* Only a new head can start here; anything already queued is held by a condition this
     * call does not change. A refusal therefore always concerns this job. */
    if (r->waiting_count == 1u && start_head(tl, r, ring) < 0) {
        (void)pop_waiting(r);
        j->state = JOB_FREE;
        return SGPU_TL_START_FAILED;
    }
    tl->last_sequence = sequence;
    return SGPU_TL_OK;
}

int sgpu_timeline_submit(struct sgpu_timeline *tl, uint32_t ring, uint32_t hw_context, const struct sgpu_be_ib *ibs, uint32_t count, const uint64_t *waits, uint32_t wait_count, uint64_t sequence)
{
    int status;
    if (ring >= tl->config.rings || !ibs || !count || count > SGPU_MAX_IBS) return SGPU_TL_ARGUMENT;
    if (wait_count > SGPU_MAX_DEPS || (wait_count && !waits)) return SGPU_TL_ARGUMENT;
    tl->hw.lock(tl->hw_context);
    status = submit_locked(tl, ring, hw_context, ibs, count, waits, wait_count, sequence);
    tl->hw.unlock(tl->hw_context);
    return status;
}

/* One reporter at a time keeps the sink's order equal to completion order. */
static void deliver(struct sgpu_timeline *tl)
{
    tl->hw.lock(tl->hw_context);
    if (tl->reporting) {
        tl->hw.unlock(tl->hw_context);
        return;
    }
    tl->reporting = 1;
    for (;;) {
        if (tl->report_count) {
            struct tl_job *j = &tl->jobs[tl->report[tl->report_head]];
            uint64_t sequence = j->sequence;
            int result;
            tl->report_head = (tl->report_head + 1u) % SGPU_TL_MAX_JOBS;
            --tl->report_count;
            j->state = JOB_FREE;
            tl->hw.unlock(tl->hw_context);
            result = tl->sink.retire(tl->sink.context, sequence, SGPU_BE_REASON_NONE);
            tl->hw.lock(tl->hw_context);
            if (result) ++tl->stats.unknown_retirements;
        } else if (tl->fault_pending) {
            uint32_t reason = tl->fault_reason;
            tl->fault_pending = 0;
            tl->hw.unlock(tl->hw_context);
            tl->sink.fault(tl->sink.context, reason);
            tl->hw.lock(tl->hw_context);
        } else if (tl->quiesce_pending) {
            int result;
            tl->quiesce_pending = 0;
            tl->hw.unlock(tl->hw_context);
            result = tl->sink.quiesced(tl->sink.context);
            tl->hw.lock(tl->hw_context);
            if (result) ++tl->stats.quiesce_rejected;
        } else {
            break;
        }
    }
    tl->reporting = 0;
    tl->hw.unlock(tl->hw_context);
}

/* Reads the counter and retires what it proves finished. Called with the lock held. */
static int observe_locked(struct sgpu_timeline *tl, uint32_t ring)
{
    struct tl_ring *r = &tl->rings[ring];
    uint64_t counter, distance, i;
    if (!r->running_count) {
        ++tl->stats.idle_observations;
        return SGPU_TL_OK;
    }
    counter = tl->hw.read_counter(tl->hw_context, ring);
    distance = (counter - r->last_counter) & tl->mask;
    if ((counter & ~tl->mask) || distance > r->running_count) {
        ++tl->stats.bad_counters;
        mark_faulted(tl, SGPU_BE_REASON_FAULT);
        return SGPU_TL_BAD_COUNTER;
    }
    if (!distance) {
        ++tl->stats.spurious_observations;
        return SGPU_TL_OK;
    }
    for (i = 0; i < distance; ++i) {
        uint32_t slot = pop_running(r);
        tl->jobs[slot].state = JOB_DONE;
        tl->report[(tl->report_head + tl->report_count) % SGPU_TL_MAX_JOBS] = (uint16_t)slot;
        ++tl->report_count;
        ++tl->stats.completed;
    }
    r->last_counter = counter;
    r->head_since = tl->hw.now_ns(tl->hw_context);
    pump(tl);
    return tl->faulted ? SGPU_TL_START_FAILED : SGPU_TL_OK;
}

int sgpu_timeline_observe(struct sgpu_timeline *tl, uint32_t ring)
{
    int status = SGPU_TL_STOPPED;
    if (ring >= tl->config.rings) return SGPU_TL_ARGUMENT;
    tl->hw.lock(tl->hw_context);
    if (tl->faulted) ++tl->stats.ignored_after_fault;
    else status = observe_locked(tl, ring);
    tl->hw.unlock(tl->hw_context);
    deliver(tl);
    return status;
}

/* The clock must not go backwards; if it appears to, no time has passed. */
static int overdue(const struct sgpu_timeline *tl, const struct tl_ring *r, uint64_t now)
{
    return r->running_count && now > r->head_since && now - r->head_since >= tl->config.job_timeout_ns;
}

int sgpu_timeline_tick(struct sgpu_timeline *tl)
{
    int status = SGPU_TL_OK;
    tl->hw.lock(tl->hw_context);
    if (tl->faulted) {
        status = SGPU_TL_STOPPED;
    } else {
        uint64_t now = tl->hw.now_ns(tl->hw_context);
        uint32_t i;
        for (i = 0; i < tl->config.rings; ++i) {
            const struct tl_ring *r = &tl->rings[i];
            if (!overdue(tl, r, now)) continue;
            /* One last look: the head may have finished with its observation still on the way. */
            status = observe_locked(tl, i);
            if (status != SGPU_TL_OK) break;
            if (overdue(tl, r, now)) {
                ++tl->stats.timeouts;
                mark_faulted(tl, SGPU_BE_REASON_FAULT);
                status = SGPU_TL_TIMED_OUT;
                break;
            }
        }
    }
    tl->hw.unlock(tl->hw_context);
    deliver(tl);
    return status;
}

int sgpu_timeline_note_fault(struct sgpu_timeline *tl, uint32_t reason)
{
    tl->hw.lock(tl->hw_context);
    mark_faulted(tl, reason ? reason : (uint32_t)SGPU_BE_REASON_FAULT);
    tl->hw.unlock(tl->hw_context);
    return SGPU_TL_OK;
}

int sgpu_timeline_fault(struct sgpu_timeline *tl, uint32_t reason)
{
    (void)sgpu_timeline_note_fault(tl, reason);
    deliver(tl);
    return SGPU_TL_OK;
}

int sgpu_timeline_quiesced(struct sgpu_timeline *tl)
{
    int status = SGPU_TL_OK;
    tl->hw.lock(tl->hw_context);
    if (!tl->faulted) {
        status = SGPU_TL_NOT_FAULTED;
    } else if (!tl->quiesced) {
        /* The job table stays frozen: a faulted timeline never starts or retires again. */
        tl->quiesced = 1;
        tl->quiesce_pending = 1;
    }
    tl->hw.unlock(tl->hw_context);
    deliver(tl);
    return status;
}

void sgpu_timeline_stats(struct sgpu_timeline *tl, struct sgpu_tl_stats *out)
{
    tl->hw.lock(tl->hw_context);
    *out = tl->stats;
    tl->hw.unlock(tl->hw_context);
}
