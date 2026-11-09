/* Bounded per-ring queues and trusted retirement for the SGPU backend core.
 *
 * This module sits between hardware signals and sgpu_backend_retire/fault/quiesced.
 * It holds no register, firmware, IRQ or ring-layout knowledge: starting work and
 * reading a completion counter belong to the caller, and no implementation of those
 * for real hardware exists yet. Nothing here establishes that a GPU executed anything.
 *
 * Rules:
 *  - Fixed tables only. A full queue refuses work before any hardware effect.
 *  - Each ring starts jobs in submission order. A job starts only once every sequence
 *    it waits for has finished, so a blocked head also holds back the jobs behind it.
 *  - Sequences strictly increase and waits refer only to earlier ones, so the oldest
 *    unfinished job can always start and waits cannot deadlock.
 *  - The completion counter is checked before it is believed. A value above the
 *    configured width, or further ahead than the work actually running on that ring,
 *    faults the device and retires nothing. A regression appears as a huge forward
 *    distance and is caught by the same check.
 *  - Once faulted, the counter is ignored and no work starts. Running work is released
 *    only by sgpu_timeline_quiesced, which the caller may call only with proof that
 *    all DMA and queues have stopped. A timeline that has faulted never restarts:
 *    recovery needs a new timeline after a real reset, which is not implemented.
 *  - Retirements reach the sink one at a time, from one reporter, in completion order,
 *    so a dependent is always reported after what it waits for. Then the fault, then
 *    quiescence. The timeline lock is never held across a sink call.
 *
 * Locking: sgpu_timeline_submit runs under the backend lock from sgpu_be_ops.submit and
 * never calls the sink. The other entry points must be called without the backend lock,
 * because the sink takes it. The order is backend lock, then timeline lock.
 *
 * Limits are software table sizes, not hardware facts. A real ring's capacity and
 * counter width must come from a validated chip profile through sgpu_tl_config.
 */
#ifndef S24_SGPU_TIMELINE_H
#define S24_SGPU_TIMELINE_H
#include "sgpu_backend.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SGPU_TL_MAX_RINGS 8u
#define SGPU_TL_MAX_DEPTH 256u
#define SGPU_TL_MAX_JOBS SGPU_BE_MAX_FENCES

enum sgpu_tl_status {
    SGPU_TL_OK = 0, SGPU_TL_ARGUMENT = 1, SGPU_TL_FULL = 2, SGPU_TL_STOPPED = 3,
    SGPU_TL_START_FAILED = 4, SGPU_TL_BAD_COUNTER = 5, SGPU_TL_TIMED_OUT = 6, SGPU_TL_NOT_FAULTED = 7
};

/* Trusted hardware boundary. lock must be usable from the completion path.
 * start is called with the lock held and must not block or call back here. A nonzero
 * return means the job was not given to the hardware. `counter` is the value the
 * completion counter reaches when this job finishes. */
struct sgpu_tl_hw {
    void (*lock)(void *hw);
    void (*unlock)(void *hw);
    uint64_t (*now_ns)(void *hw);
    int (*start)(void *hw, uint32_t ring, uint32_t hw_context, const struct sgpu_be_ib *ibs, uint32_t count, uint64_t counter);
};

/* Normally forwards to sgpu_backend_retire, sgpu_backend_fault and sgpu_backend_quiesced. */
struct sgpu_tl_sink {
    void *context;
    int (*retire)(void *context, uint64_t sequence, uint32_t reason);
    void (*fault)(void *context, uint32_t reason);
    int (*quiesced)(void *context);
};

struct sgpu_tl_config {
    uint32_t rings, depth, counter_bits, reserved;
    uint64_t job_timeout_ns;
    uint64_t initial_counter[SGPU_TL_MAX_RINGS];
};

struct sgpu_tl_stats {
    uint64_t started, completed, spurious_observations, ignored_after_fault, bad_counters;
    uint64_t timeouts, start_failures, unknown_retirements, quiesce_rejected;
};

struct sgpu_timeline;

size_t sgpu_timeline_storage_size(void);
int sgpu_timeline_init(struct sgpu_timeline *storage, const struct sgpu_tl_config *config, const struct sgpu_tl_hw *hw, void *hw_context, const struct sgpu_tl_sink *sink);

/* A nonzero return means nothing was queued and the sequence may be reused. */
int sgpu_timeline_submit(struct sgpu_timeline *timeline, uint32_t ring, uint32_t hw_context, const struct sgpu_be_ib *ibs, uint32_t count, const uint64_t *waits, uint32_t wait_count, uint64_t sequence);

/* Trusted observations; never reachable from a client. */
int sgpu_timeline_observe(struct sgpu_timeline *timeline, uint32_t ring, uint64_t counter);
int sgpu_timeline_tick(struct sgpu_timeline *timeline);
int sgpu_timeline_fault(struct sgpu_timeline *timeline, uint32_t reason);
int sgpu_timeline_quiesced(struct sgpu_timeline *timeline);
void sgpu_timeline_stats(struct sgpu_timeline *timeline, struct sgpu_tl_stats *out);

#ifdef __cplusplus
}
#endif
#endif
