/* Portable Xclipse kernel-backend core for the project's SGPU transport.
 *
 * This is the object-lifetime and validation layer only. It contains no register
 * programming, firmware, power, ring or IRQ code: every hardware effect goes
 * through struct sgpu_be_ops, and no implementation of those ops for real
 * hardware exists yet. Nothing here establishes that a GPU has executed anything.
 *
 * The core refuses every request except QUERY until a caller supplies
 * config.profile_verified != 0. No code in this tree sets it for real hardware;
 * doing so requires a validated firmware and chip profile.
 *
 * After a whole-buffer CACHE TO_GPU clears cpu_dirty, a client can still write
 * through a live CPU mapping of a data BO. That is a data race on its own pinned
 * buffer, not a lifetime or isolation failure, and the core cannot observe it. A
 * BO with a writable CPU mapping cannot hold an IB.
 */
#ifndef S24_SGPU_BACKEND_H
#define S24_SGPU_BACKEND_H
#include "sgpu_abi.h"

#ifdef __cplusplus
extern "C" {
#endif

#define SGPU_BE_MAX_CLIENTS 16u
#define SGPU_BE_MAX_BOS 1024u
#define SGPU_BE_MAX_CONTEXTS 64u
#define SGPU_BE_MAX_CPU_MAPS 256u
#define SGPU_BE_MAX_GPU_MAPS 4096u
#define SGPU_BE_MAX_FENCES 512u
#define SGPU_BE_MAX_READERS 8u

/* Each table divided across every client slot, so that one live client cannot
 * exhaust a table another live client needs. A closed client's zombies are outside
 * this guarantee: they stay until the hardware stops using them. */
#define SGPU_BE_CLIENT_MAX_BOS (SGPU_BE_MAX_BOS / SGPU_BE_MAX_CLIENTS)
#define SGPU_BE_CLIENT_MAX_CONTEXTS (SGPU_BE_MAX_CONTEXTS / SGPU_BE_MAX_CLIENTS)
#define SGPU_BE_CLIENT_MAX_CPU_MAPS (SGPU_BE_MAX_CPU_MAPS / SGPU_BE_MAX_CLIENTS)
#define SGPU_BE_CLIENT_MAX_GPU_MAPS (SGPU_BE_MAX_GPU_MAPS / SGPU_BE_MAX_CLIENTS)
#define SGPU_BE_CLIENT_MAX_FENCES (SGPU_BE_MAX_FENCES / SGPU_BE_MAX_CLIENTS)

/* Reasons reported by trusted hardware paths. Zero means clean retirement. */
enum sgpu_be_reason { SGPU_BE_REASON_NONE = 0, SGPU_BE_REASON_FAULT = 1, SGPU_BE_REASON_QUIESCED = 2 };

struct sgpu_be_ib { uint64_t va; uint32_t bytes, flags; };

/* Trusted hardware boundary. Methods returning int report success as zero.
 *
 * lock/unlock guard all core state. wait_locked is entered with the lock held
 * and must atomically release it while blocked, reacquiring before return, as
 * IOLockSleepDeadline does. It may return early; callers recheck their condition.
 *
 * backing_alloc must return pinned, zeroed backing.
 *
 * A failed vm_map must leave nothing mapped. Once vm_map has succeeded, a failed
 * tlb_flush, and any failed vm_unmap, retains the range and quarantines the device.
 * vm_unmap must be idempotent, because a range whose flush failed is unmapped again.
 *
 * submit must not start the work until every sequence in wait_sequences has retired.
 * Work must therefore retire after what it waits for. Lifetime references do not rely
 * on that order; hazard tracking does. A nonzero return must mean nothing was queued,
 * because the next submit reuses the sequence. An implementation that cannot tell
 * must return zero and later retire the sequence with a nonzero reason.
 */
struct sgpu_be_ops {
    void (*lock)(void *hw);
    void (*unlock)(void *hw);
    uint64_t (*now_ns)(void *hw);
    void (*wait_locked)(void *hw, uint64_t timeout_ns);
    void (*wake)(void *hw);
    int (*backing_alloc)(void *hw, uint64_t bytes, uint64_t alignment, uint64_t *token);
    void (*backing_free)(void *hw, uint64_t token, uint64_t bytes);
    int (*cpu_map)(void *hw, uint64_t token, uint64_t offset, uint64_t bytes, uint32_t access);
    void (*cpu_unmap)(void *hw, uint64_t token, uint64_t offset, uint64_t bytes);
    int (*context_create)(void *hw, uint32_t engine_class, uint32_t *hw_context);
    void (*context_destroy)(void *hw, uint32_t hw_context);
    int (*vm_map)(void *hw, uint32_t hw_context, uint64_t va, uint64_t token, uint64_t offset, uint64_t bytes, uint32_t access);
    int (*vm_unmap)(void *hw, uint32_t hw_context, uint64_t va, uint64_t bytes);
    int (*tlb_flush)(void *hw, uint32_t hw_context, uint64_t va, uint64_t bytes);
    int (*cache_sync)(void *hw, uint64_t token, uint64_t offset, uint64_t bytes, uint32_t direction);
    int (*submit)(void *hw, uint32_t hw_context, const struct sgpu_be_ib *ibs, uint32_t count, const uint64_t *wait_sequences, uint32_t wait_count, uint64_t sequence);
};

struct sgpu_be_config {
    /* max_alloc_bytes <= client_budget_bytes <= budget_bytes. QUERY reports the client budget. */
    uint64_t budget_bytes, client_budget_bytes, max_alloc_bytes, va_start, va_bytes, epoch;
    uint32_t cpu_hardware_page, cpu_vm_page, profile_verified, reserved;
};

struct sgpu_backend;
/* Connects one authenticated transport client to the sgpu_backend_fn callback. */
struct sgpu_be_binding { struct sgpu_backend *backend; uint32_t client; };

size_t sgpu_backend_storage_size(void);
/* storage must be sgpu_backend_storage_size() bytes, suitably aligned, stable
 * for the backend lifetime. Returns SGPU_OK or SGPU_BAD_FIELD. */
uint32_t sgpu_backend_init(struct sgpu_backend *storage, const struct sgpu_be_config *config, const struct sgpu_be_ops *ops, void *hw);
uint32_t sgpu_backend_client_open(struct sgpu_backend *backend, uint32_t *client);
void sgpu_backend_client_close(struct sgpu_backend *backend, uint32_t client);
void sgpu_backend_dispatch(void *binding, const struct sgpu_request_view *request, struct sgpu_backend_result *result);

/* Trusted observations from hardware paths; never reachable from the transport.
 * retire returns zero when a pending fence with that sequence exists. */
int sgpu_backend_retire(struct sgpu_backend *backend, uint64_t sequence, uint32_t reason);
void sgpu_backend_fault(struct sgpu_backend *backend, uint32_t reason);
/* Proof all DMA and queues stopped. Only meaningful after a fault; returns zero if accepted. */
int sgpu_backend_quiesced(struct sgpu_backend *backend);

#ifdef __cplusplus
}
#endif
#endif
