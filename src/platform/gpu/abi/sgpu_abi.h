/* Project-owned SGPU transport proposal v1.0, not Linux/Apple's binary ABI.
 * All wire integers are little endian. Layouts are documentation/assertions;
 * never cast an untrusted byte buffer to these structures. No device I/O.
 */
#ifndef S24_SGPU_ABI_H
#define S24_SGPU_ABI_H
#include <stddef.h>
#include <stdint.h>

#define SGPU_MAGIC UINT32_C(0x31584753) /* bytes "SGX1" */
#define SGPU_ABI_MAJOR 1u
#define SGPU_ABI_MINOR 0u
#define SGPU_MAX_MESSAGE 4096u
#define SGPU_MAX_IBS 8u
#define SGPU_MAX_USES 64u
#define SGPU_MAX_DEPS 32u
#define SGPU_MAX_IB_BYTES UINT64_C(65536)
#define SGPU_MAX_ALLOC_BYTES UINT64_C(134217728)
#define SGPU_MAX_WAIT_NS UINT64_C(100000000)
#define SGPU_GPU_PAGE UINT64_C(4096)
#define SGPU_FEATURE_VALIDATION UINT64_C(1)
#define SGPU_FEATURE_SYNTHETIC (UINT64_C(1) << 63)

enum sgpu_opcode {
    SGPU_QUERY = 1, SGPU_ALLOC = 2, SGPU_FREE = 3,
    SGPU_CONTEXT_CREATE = 4, SGPU_CONTEXT_DESTROY = 5,
    SGPU_CPU_MAP = 6, SGPU_CPU_UNMAP = 7,
    SGPU_GPU_MAP = 8, SGPU_GPU_UNMAP = 9, SGPU_CACHE = 10,
    SGPU_SUBMIT = 11, SGPU_WAIT = 12, SGPU_STOP = 13
    /* Sharing/presentation require a later negotiated extension. No reset,
     * raw-register, physical-address or client-asserted completion operation. */
};
enum sgpu_status {
    SGPU_OK = 0, SGPU_BAD_SIZE = 1, SGPU_BAD_HEADER = 2,
    SGPU_BAD_VERSION = 3, SGPU_UNSUPPORTED = 4, SGPU_BAD_FIELD = 5,
    SGPU_LIMIT = 6, SGPU_TIMEOUT = 7, SGPU_STOPPED = 8,
    SGPU_BACKEND_ERROR = 9, SGPU_BAD_REPLY = 10
};
enum sgpu_access { SGPU_READ = 1, SGPU_WRITE = 2, SGPU_EXEC = 4 };
enum sgpu_cache_direction { SGPU_TO_GPU = 1, SGPU_TO_CPU = 2 };
enum sgpu_fence_state { SGPU_RETIRED = 1, SGPU_RETIRED_ERROR = 2 };

struct sgpu_request_header {
    uint32_t magic;
    uint16_t major, minor;
    uint32_t opcode, bytes;
    uint64_t request_id;
    uint32_t flags, reserved;
};
struct sgpu_reply_header {
    uint32_t magic;
    uint16_t major, minor;
    uint32_t opcode, bytes;
    uint64_t request_id;
    uint32_t status, reserved;
};
struct sgpu_query_request {
    uint16_t min_major, max_major, min_minor, max_minor;
    uint64_t required_features;
};
struct sgpu_alloc_request { uint64_t bytes, alignment; uint32_t access, reserved; };
struct sgpu_handle_request { uint64_t handle; };
struct sgpu_context_request { uint32_t engine_class, priority; uint64_t reserved; };
struct sgpu_cpu_map_request { uint64_t handle, offset, bytes; uint32_t access, reserved; };
struct sgpu_gpu_map_request {
    uint64_t context, handle, address, offset, bytes;
    uint32_t access, reserved;
};
struct sgpu_gpu_unmap_request { uint64_t context, address, bytes; };
struct sgpu_cache_request { uint64_t handle, offset, bytes; uint32_t direction, reserved; };
struct sgpu_submit_request {
    uint64_t context;
    uint32_t ib_count, use_count, dep_count, reserved;
    /* Exactly ib_count IBs, use_count uses, then dep_count dependencies follow. */
};
struct sgpu_ib { uint64_t handle, offset, bytes; uint32_t flags, reserved; };
struct sgpu_use { uint64_t handle; uint32_t access, reserved; };
struct sgpu_dependency { uint64_t fence; };
struct sgpu_wait_request { uint64_t fence, timeout_ns; };
struct sgpu_object_reply { uint64_t handle, value; };
struct sgpu_wait_reply { uint32_t state, reason; };
struct sgpu_query_reply {
    uint64_t features, epoch, budget_bytes, max_alloc_bytes, va_start, va_bytes;
    uint32_t cpu_hardware_page, cpu_vm_page, gpu_page, max_message;
    uint32_t max_ibs, max_uses, max_deps, max_wait_ms;
    uint32_t profile_verified, reserved;
};

#if defined(__cplusplus)
#define SGPU_ASSERT(c) static_assert(c, #c)
extern "C" {
#else
#define SGPU_ASSERT(c) _Static_assert(c, #c)
#endif
#define SGPU_LAYOUT(type, bytes, member, offset) \
    SGPU_ASSERT(sizeof(struct type) == bytes); \
    SGPU_ASSERT(offsetof(struct type, member) == offset)
SGPU_LAYOUT(sgpu_request_header, 32, request_id, 16);
SGPU_LAYOUT(sgpu_reply_header, 32, status, 24);
SGPU_LAYOUT(sgpu_query_request, 16, required_features, 8);
SGPU_LAYOUT(sgpu_alloc_request, 24, access, 16);
SGPU_LAYOUT(sgpu_handle_request, 8, handle, 0);
SGPU_LAYOUT(sgpu_context_request, 16, reserved, 8);
SGPU_LAYOUT(sgpu_cpu_map_request, 32, access, 24);
SGPU_LAYOUT(sgpu_gpu_map_request, 48, access, 40);
SGPU_LAYOUT(sgpu_gpu_unmap_request, 24, bytes, 16);
SGPU_LAYOUT(sgpu_cache_request, 32, direction, 24);
SGPU_LAYOUT(sgpu_submit_request, 24, reserved, 20);
SGPU_LAYOUT(sgpu_ib, 32, flags, 24);
SGPU_LAYOUT(sgpu_use, 16, access, 8);
SGPU_LAYOUT(sgpu_dependency, 8, fence, 0);
SGPU_LAYOUT(sgpu_wait_request, 16, timeout_ns, 8);
SGPU_LAYOUT(sgpu_object_reply, 16, value, 8);
SGPU_LAYOUT(sgpu_wait_reply, 8, reason, 4);
SGPU_LAYOUT(sgpu_query_reply, 88, profile_verified, 80);
SGPU_ASSERT(32 + 24 + 32 * SGPU_MAX_IBS + 16 * SGPU_MAX_USES + 8 * SGPU_MAX_DEPS <= SGPU_MAX_MESSAGE);
#undef SGPU_LAYOUT
#undef SGPU_ASSERT

/* These are trusted in-process C interfaces, not wire structures. The caller
 * supplies a bounded immutable kernel-owned snapshot, never a userspace pointer.
 * A view is borrowed only until the callback returns; do not retain it.
 */
struct sgpu_request_view { const uint8_t *payload; uint32_t opcode, payload_bytes; uint64_t request_id; };
struct sgpu_backend_result { uint32_t status, bytes; uint8_t payload[88]; };
typedef void (*sgpu_backend_fn)(void *, const struct sgpu_request_view *, struct sgpu_backend_result *);
uint16_t sgpu_get16(const uint8_t *);
uint32_t sgpu_get32(const uint8_t *);
uint64_t sgpu_get64(const uint8_t *);
void sgpu_put16(uint8_t *, uint16_t);
void sgpu_put32(uint8_t *, uint32_t);
void sgpu_put64(uint8_t *, uint64_t);
uint32_t sgpu_validate_request(const void *, size_t, struct sgpu_request_view *);
/* Returns protocol status; reply_bytes=0 for insufficient output capacity or
 * overlapping input/output. Other errors produce a zero-padded header reply.
 * Output capacity must be at least 120, checked before invoking any backend.
 */
uint32_t sgpu_dispatch(const void *, size_t, void *, size_t, size_t *, sgpu_backend_fn, void *);
#ifdef __cplusplus
}
#endif
#endif
