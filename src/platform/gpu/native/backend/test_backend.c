/* Host tests for the SGPU backend core: every request goes through sgpu_dispatch.
 *
 * The hardware is a software fake with failure injection. Passing here says the
 * object-lifetime rules hold against that fake. It says nothing about any GPU.
 */
#define _POSIX_C_SOURCE 200809L
#include "sgpu_backend.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __func__, __LINE__, #c); exit(1); } } while (0)
#define CHECK_EQ(a, b) do { unsigned long long a_ = (unsigned long long)(a), b_ = (unsigned long long)(b); \
    if (a_ != b_) { fprintf(stderr, "FAIL %s:%d: %s=%llu expected %s=%llu\n", __func__, __LINE__, #a, a_, #b, b_); exit(1); } } while (0)

#define VA UINT64_C(0x100000000)
#define KB(n) (UINT64_C(1024) * (n))
#define RW (SGPU_READ | SGPU_WRITE)
#define RWX (SGPU_READ | SGPU_WRITE | SGPU_EXEC)

struct fake {
    int fail_backing, fail_cpu_map, fail_context, fail_vm_map, fail_vm_unmap, fail_tlb, fail_cache, fail_submit;
    unsigned alloc_calls, free_calls, cpu_map_calls, cpu_unmap_calls, context_create_calls, context_destroy_calls;
    unsigned vm_map_calls, vm_unmap_calls, tlb_calls, cache_calls, submit_calls, wake_calls;
    uint64_t next_token, now, last_alloc_bytes, last_alloc_alignment, last_sequence;
    uint32_t next_context, last_count, last_context;
    struct sgpu_be_ib last_ibs[SGPU_MAX_IBS];
    int locked, threaded;
    uint64_t retire_on_wait; /* Nonzero: the first wait observes this retirement. */
    uint32_t retire_reason;
    struct sgpu_backend *owner;
    pthread_mutex_t mutex;
    pthread_cond_t cond;
};

static _Alignas(16) uint8_t storage[1u << 21];
static struct fake F;
static struct sgpu_backend *const BE = (struct sgpu_backend *)storage;
static uint64_t request_id = 1;

static void fake_held(void) { if (!F.threaded) CHECK(F.locked); }

static void op_lock(void *hw)
{
    (void)hw;
    if (F.threaded) { pthread_mutex_lock(&F.mutex); return; }
    CHECK(!F.locked);
    F.locked = 1;
}
static void op_unlock(void *hw)
{
    (void)hw;
    if (F.threaded) { pthread_mutex_unlock(&F.mutex); return; }
    CHECK(F.locked);
    F.locked = 0;
}
static uint64_t op_now(void *hw)
{
    struct timespec t;
    (void)hw;
    fake_held();
    if (!F.threaded) return F.now;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}
static void op_wait(void *hw, uint64_t timeout)
{
    (void)hw;
    fake_held();
    if (F.threaded) {
        struct timespec t;
        uint64_t end;
        clock_gettime(CLOCK_MONOTONIC, &t);
        end = (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec + timeout;
        t.tv_sec = (time_t)(end / UINT64_C(1000000000));
        t.tv_nsec = (long)(end % UINT64_C(1000000000));
        pthread_cond_timedwait(&F.cond, &F.mutex, &t);
        return;
    }
    if (F.retire_on_wait) {
        uint64_t sequence = F.retire_on_wait;
        F.retire_on_wait = 0;
        F.locked = 0; /* The real primitive releases the lock while asleep. */
        CHECK_EQ(sgpu_backend_retire(F.owner, sequence, F.retire_reason), 0);
        CHECK(!F.locked);
        F.locked = 1;
        return;
    }
    F.now += timeout;
}
static void op_wake(void *hw)
{
    (void)hw;
    fake_held();
    ++F.wake_calls;
    if (F.threaded) pthread_cond_broadcast(&F.cond);
}
static int op_backing_alloc(void *hw, uint64_t bytes, uint64_t alignment, uint64_t *token)
{
    (void)hw;
    fake_held();
    ++F.alloc_calls;
    F.last_alloc_bytes = bytes;
    F.last_alloc_alignment = alignment;
    if (F.fail_backing) return -1;
    *token = ++F.next_token;
    return 0;
}
static void op_backing_free(void *hw, uint64_t token, uint64_t bytes)
{
    (void)hw; (void)token; (void)bytes;
    fake_held();
    ++F.free_calls;
}
static int op_cpu_map(void *hw, uint64_t token, uint64_t offset, uint64_t bytes, uint32_t access)
{
    (void)hw; (void)token; (void)offset; (void)bytes; (void)access;
    fake_held();
    ++F.cpu_map_calls;
    return F.fail_cpu_map ? -1 : 0;
}
static void op_cpu_unmap(void *hw, uint64_t token, uint64_t offset, uint64_t bytes)
{
    (void)hw; (void)token; (void)offset; (void)bytes;
    fake_held();
    ++F.cpu_unmap_calls;
}
static int op_context_create(void *hw, uint32_t engine, uint32_t *context)
{
    (void)hw; (void)engine;
    fake_held();
    ++F.context_create_calls;
    if (F.fail_context) return -1;
    *context = ++F.next_context;
    return 0;
}
static void op_context_destroy(void *hw, uint32_t context)
{
    (void)hw; (void)context;
    fake_held();
    ++F.context_destroy_calls;
}
static int op_vm_map(void *hw, uint32_t context, uint64_t va, uint64_t token, uint64_t offset, uint64_t bytes, uint32_t access)
{
    (void)hw; (void)context; (void)va; (void)token; (void)offset; (void)bytes; (void)access;
    fake_held();
    ++F.vm_map_calls;
    return F.fail_vm_map ? -1 : 0;
}
static int op_vm_unmap(void *hw, uint32_t context, uint64_t va, uint64_t bytes)
{
    (void)hw; (void)context; (void)va; (void)bytes;
    fake_held();
    ++F.vm_unmap_calls;
    return F.fail_vm_unmap ? -1 : 0;
}
static int op_tlb(void *hw, uint32_t context, uint64_t va, uint64_t bytes)
{
    (void)hw; (void)context; (void)va; (void)bytes;
    fake_held();
    ++F.tlb_calls;
    return F.fail_tlb ? -1 : 0;
}
static int op_cache(void *hw, uint64_t token, uint64_t offset, uint64_t bytes, uint32_t direction)
{
    (void)hw; (void)token; (void)offset; (void)bytes; (void)direction;
    fake_held();
    ++F.cache_calls;
    return F.fail_cache ? -1 : 0;
}
static int op_submit(void *hw, uint32_t context, const struct sgpu_be_ib *ibs, uint32_t count, uint64_t sequence)
{
    uint32_t i;
    (void)hw;
    fake_held();
    ++F.submit_calls;
    if (F.fail_submit) return -1;
    F.last_context = context;
    F.last_count = count;
    F.last_sequence = sequence;
    for (i = 0; i < count; ++i) F.last_ibs[i] = ibs[i];
    return 0;
}

static const struct sgpu_be_ops OPS = {
    op_lock, op_unlock, op_now, op_wait, op_wake, op_backing_alloc, op_backing_free, op_cpu_map, op_cpu_unmap,
    op_context_create, op_context_destroy, op_vm_map, op_vm_unmap, op_tlb, op_cache, op_submit
};

static struct sgpu_be_config config_verified(uint32_t page, uint64_t budget, uint64_t max_alloc)
{
    struct sgpu_be_config c;
    memset(&c, 0, sizeof c);
    c.budget_bytes = budget; c.max_alloc_bytes = max_alloc; c.va_start = VA; c.va_bytes = UINT64_C(1) << 32;
    c.epoch = 7; c.cpu_hardware_page = page; c.cpu_vm_page = page; c.profile_verified = 1;
    return c;
}

static void reset_fake(void)
{
    memset(&F, 0, sizeof F);
    F.owner = BE;
    F.next_token = 100;
    F.next_context = 200;
    F.now = 1000;
}

static void setup_with(const struct sgpu_be_config *c)
{
    reset_fake();
    CHECK(sgpu_backend_storage_size() <= sizeof storage);
    CHECK_EQ(sgpu_backend_init(BE, c, &OPS, &F), SGPU_OK);
}

static void setup(uint32_t page, uint64_t budget, uint64_t max_alloc)
{
    struct sgpu_be_config c = config_verified(page, budget, max_alloc);
    setup_with(&c);
}

static uint32_t open_client(void)
{
    uint32_t client = 0;
    CHECK_EQ(sgpu_backend_client_open(BE, &client), SGPU_OK);
    return client;
}

static unsigned hw_effects(void)
{
    return F.alloc_calls + F.free_calls + F.cpu_map_calls + F.cpu_unmap_calls + F.context_create_calls + F.context_destroy_calls
        + F.vm_map_calls + F.vm_unmap_calls + F.tlb_calls + F.cache_calls + F.submit_calls;
}

static void header(uint8_t *wire, uint32_t opcode, size_t total)
{
    memset(wire, 0, 32);
    sgpu_put32(wire, SGPU_MAGIC);
    sgpu_put16(wire + 4, SGPU_ABI_MAJOR);
    sgpu_put16(wire + 6, SGPU_ABI_MINOR);
    sgpu_put32(wire + 8, opcode);
    sgpu_put32(wire + 12, (uint32_t)total);
    sgpu_put64(wire + 16, request_id++);
}

static uint32_t call_raw(uint32_t client, const uint8_t *wire, size_t n, uint8_t *out)
{
    struct sgpu_be_binding binding;
    uint8_t reply[256];
    size_t bytes = 0;
    uint32_t status;
    binding.backend = BE;
    binding.client = client;
    status = sgpu_dispatch(wire, n, reply, sizeof reply, &bytes, sgpu_backend_dispatch, &binding);
    if (out && bytes > 32) memcpy(out, reply + 32, bytes - 32);
    return status;
}

static uint32_t call(uint32_t client, uint32_t opcode, const uint8_t *payload, size_t n, uint8_t *out)
{
    uint8_t wire[SGPU_MAX_MESSAGE];
    header(wire, opcode, 32 + n);
    if (n) memcpy(wire + 32, payload, n);
    return call_raw(client, wire, 32 + n, out);
}

static uint32_t query(uint32_t client, uint64_t required, uint8_t *out)
{
    uint8_t p[16] = {0};
    sgpu_put16(p, 1); sgpu_put16(p + 2, 1);
    sgpu_put64(p + 8, required);
    return call(client, SGPU_QUERY, p, sizeof p, out);
}

static uint32_t alloc_bo(uint32_t client, uint64_t bytes, uint32_t access, uint64_t *handle, uint64_t *value)
{
    uint8_t p[24] = {0}, out[16] = {0};
    uint32_t status;
    sgpu_put64(p, bytes); sgpu_put64(p + 8, 4096); sgpu_put32(p + 16, access);
    status = call(client, SGPU_ALLOC, p, sizeof p, out);
    if (handle) *handle = sgpu_get64(out);
    if (value) *value = sgpu_get64(out + 8);
    return status;
}

static uint32_t handle_op(uint32_t client, uint32_t opcode, uint64_t handle)
{
    uint8_t p[8];
    sgpu_put64(p, handle);
    return call(client, opcode, p, sizeof p, NULL);
}

static uint32_t free_bo(uint32_t client, uint64_t handle) { return handle_op(client, SGPU_FREE, handle); }

static uint32_t create_context(uint32_t client, uint64_t *handle)
{
    uint8_t p[16] = {0}, out[16] = {0};
    uint32_t status = call(client, SGPU_CONTEXT_CREATE, p, sizeof p, out);
    if (handle) *handle = sgpu_get64(out);
    return status;
}

static uint32_t cpu_map(uint32_t client, uint64_t bo, uint64_t offset, uint64_t bytes, uint32_t access, uint64_t *mapping)
{
    uint8_t p[32] = {0}, out[16] = {0};
    uint32_t status;
    sgpu_put64(p, bo); sgpu_put64(p + 8, offset); sgpu_put64(p + 16, bytes); sgpu_put32(p + 24, access);
    status = call(client, SGPU_CPU_MAP, p, sizeof p, out);
    if (mapping) *mapping = sgpu_get64(out);
    return status;
}

static uint32_t gpu_map(uint32_t client, uint64_t context, uint64_t bo, uint64_t va, uint64_t offset, uint64_t bytes, uint32_t access)
{
    uint8_t p[48] = {0};
    sgpu_put64(p, context); sgpu_put64(p + 8, bo); sgpu_put64(p + 16, va); sgpu_put64(p + 24, offset); sgpu_put64(p + 32, bytes); sgpu_put32(p + 40, access);
    return call(client, SGPU_GPU_MAP, p, sizeof p, NULL);
}

static uint32_t gpu_unmap(uint32_t client, uint64_t context, uint64_t va, uint64_t bytes)
{
    uint8_t p[24] = {0};
    sgpu_put64(p, context); sgpu_put64(p + 8, va); sgpu_put64(p + 16, bytes);
    return call(client, SGPU_GPU_UNMAP, p, sizeof p, NULL);
}

static uint32_t cache_op(uint32_t client, uint64_t bo, uint64_t offset, uint64_t bytes, uint32_t direction)
{
    uint8_t p[32] = {0};
    sgpu_put64(p, bo); sgpu_put64(p + 8, offset); sgpu_put64(p + 16, bytes); sgpu_put32(p + 24, direction);
    return call(client, SGPU_CACHE, p, sizeof p, NULL);
}

struct ib { uint64_t bo, offset, bytes; };
struct use { uint64_t bo; uint32_t access; };

static size_t build_submit(uint8_t *p, uint64_t context, const struct ib *ibs, uint32_t ni, const struct use *uses, uint32_t nu, const uint64_t *deps, uint32_t nd)
{
    size_t at = 24;
    uint32_t i;
    memset(p, 0, 24 + 32 * (size_t)ni + 16 * (size_t)nu + 8 * (size_t)nd);
    sgpu_put64(p, context); sgpu_put32(p + 8, ni); sgpu_put32(p + 12, nu); sgpu_put32(p + 16, nd);
    for (i = 0; i < ni; ++i, at += 32) { sgpu_put64(p + at, ibs[i].bo); sgpu_put64(p + at + 8, ibs[i].offset); sgpu_put64(p + at + 16, ibs[i].bytes); }
    for (i = 0; i < nu; ++i, at += 16) { sgpu_put64(p + at, uses[i].bo); sgpu_put32(p + at + 8, uses[i].access); }
    for (i = 0; i < nd; ++i, at += 8) sgpu_put64(p + at, deps[i]);
    return at;
}

static uint32_t submit(uint32_t client, uint64_t context, const struct ib *ibs, uint32_t ni, const struct use *uses, uint32_t nu, const uint64_t *deps, uint32_t nd, uint64_t *fence, uint64_t *sequence)
{
    uint8_t p[SGPU_MAX_MESSAGE], out[16] = {0};
    size_t n = build_submit(p, context, ibs, ni, uses, nu, deps, nd);
    uint32_t status = call(client, SGPU_SUBMIT, p, n, out);
    if (fence) *fence = sgpu_get64(out);
    if (sequence) *sequence = sgpu_get64(out + 8);
    return status;
}

/* One IB inside bo, one use of bo. access must include READ because the IB is fetched. */
static uint32_t submit_one(uint32_t client, uint64_t context, uint64_t bo, uint32_t access, const uint64_t *deps, uint32_t nd, uint64_t *fence, uint64_t *sequence)
{
    struct ib i; struct use u;
    i.bo = bo; i.offset = 0; i.bytes = 16;
    u.bo = bo; u.access = access;
    return submit(client, context, &i, 1, &u, 1, deps, nd, fence, sequence);
}

static uint32_t wait_fence(uint32_t client, uint64_t fence, uint64_t timeout, uint32_t *state, uint32_t *reason)
{
    uint8_t p[16], out[8] = {0};
    uint32_t status;
    sgpu_put64(p, fence); sgpu_put64(p + 8, timeout);
    status = call(client, SGPU_WAIT, p, sizeof p, out);
    if (state) *state = sgpu_get32(out);
    if (reason) *reason = sgpu_get32(out + 4);
    return status;
}

struct fixture { uint32_t client; uint64_t context, bo; };

/* A client with a context and a 16K BO mapped RW at va. */
static struct fixture make_fixture(uint64_t va)
{
    struct fixture f;
    f.client = open_client();
    CHECK_EQ(create_context(f.client, &f.context), SGPU_OK);
    CHECK_EQ(alloc_bo(f.client, KB(16), RWX, &f.bo, NULL), SGPU_OK);
    CHECK_EQ(gpu_map(f.client, f.context, f.bo, va, 0, KB(16), RW), SGPU_OK);
    return f;
}

static void test_unverified_refuses_all_but_query(void)
{
    static const uint32_t refused[] = { SGPU_FREE, SGPU_CONTEXT_DESTROY, SGPU_CPU_UNMAP };
    struct sgpu_be_config c;
    uint8_t out[88], p[64] = {0};
    uint32_t client, i;
    memset(&c, 0, sizeof c);
    setup_with(&c);
    client = open_client();

    CHECK_EQ(query(client, SGPU_FEATURE_VALIDATION, out), SGPU_OK);
    CHECK_EQ(sgpu_get64(out), SGPU_FEATURE_VALIDATION);
    for (i = 8; i < 60; ++i) CHECK_EQ(out[i], 0);
    CHECK_EQ(sgpu_get32(out + 80), 0);
    CHECK_EQ(query(client, SGPU_FEATURE_SYNTHETIC, NULL), SGPU_UNSUPPORTED);

    CHECK_EQ(alloc_bo(client, KB(4), RW, NULL, NULL), SGPU_UNSUPPORTED);
    CHECK_EQ(create_context(client, NULL), SGPU_UNSUPPORTED);
    for (i = 0; i < sizeof refused / sizeof refused[0]; ++i) CHECK_EQ(handle_op(client, refused[i], 1), SGPU_UNSUPPORTED);
    CHECK_EQ(cpu_map(client, 1, 0, KB(4), SGPU_READ, NULL), SGPU_UNSUPPORTED);
    CHECK_EQ(gpu_map(client, 1, 1, VA, 0, KB(4), SGPU_READ), SGPU_UNSUPPORTED);
    CHECK_EQ(gpu_unmap(client, 1, VA, KB(4)), SGPU_UNSUPPORTED);
    CHECK_EQ(cache_op(client, 1, 0, KB(4), SGPU_TO_GPU), SGPU_UNSUPPORTED);
    CHECK_EQ(submit_one(client, 1, 1, SGPU_READ, NULL, 0, NULL, NULL), SGPU_UNSUPPORTED);
    CHECK_EQ(wait_fence(client, 1, 0, NULL, NULL), SGPU_UNSUPPORTED);
    CHECK_EQ(call(client, SGPU_STOP, p, 0, NULL), SGPU_UNSUPPORTED);
    CHECK_EQ(hw_effects(), 0);

    c.budget_bytes = KB(16);
    reset_fake();
    CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
}

static void test_init_rejects_bad_profiles(void)
{
    struct sgpu_be_config good = config_verified(4096, KB(64), KB(16)), c;
    struct sgpu_be_ops ops = OPS;
    reset_fake();
    c = good; c.cpu_vm_page = 8192; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.cpu_hardware_page = 0; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.max_alloc_bytes = KB(128); CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.va_start = VA + 1; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.va_start = 0; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.va_start = UINT64_MAX - 4095; c.va_bytes = KB(8); CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.epoch = 0; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.profile_verified = 2; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    c = good; c.reserved = 1; CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_BAD_FIELD);
    ops.submit = NULL; CHECK_EQ(sgpu_backend_init(BE, &good, &ops, &F), SGPU_BAD_FIELD);
    CHECK_EQ(sgpu_backend_init(BE, &good, NULL, &F), SGPU_BAD_FIELD);
    CHECK_EQ(sgpu_backend_init(BE, NULL, &OPS, &F), SGPU_BAD_FIELD);
}

static void test_verified_query_passes_reply_validation(void)
{
    uint8_t out[88];
    uint32_t client;
    setup(16384, KB(64), KB(16));
    client = open_client();
    CHECK_EQ(query(client, 0, out), SGPU_OK);
    CHECK_EQ(sgpu_get64(out) & SGPU_FEATURE_SYNTHETIC, 0);
    CHECK_EQ(sgpu_get64(out + 8), 7);
    CHECK_EQ(sgpu_get64(out + 16), KB(64));
    CHECK_EQ(sgpu_get64(out + 24), KB(16));
    CHECK_EQ(sgpu_get64(out + 32), VA);
    CHECK_EQ(sgpu_get32(out + 48), 16384);
    CHECK_EQ(sgpu_get32(out + 52), 16384);
    CHECK_EQ(sgpu_get32(out + 56), 4096);
    CHECK_EQ(sgpu_get32(out + 80), 1);
}

static void test_page_accounting_and_budget(void)
{
    uint64_t a, b, c, value;
    uint32_t client;

    setup(4096, KB(64), KB(32));
    client = open_client();
    CHECK_EQ(alloc_bo(client, 1, RW, &a, &value), SGPU_OK);
    CHECK_EQ(value, KB(4));
    CHECK_EQ(F.last_alloc_alignment, 4096);
    CHECK_EQ(alloc_bo(client, KB(32) + 1, RW, NULL, NULL), SGPU_LIMIT);

    setup(16384, KB(32), KB(32));
    client = open_client();
    CHECK_EQ(alloc_bo(client, 1, RW, &a, &value), SGPU_OK);
    CHECK_EQ(value, KB(16));
    CHECK_EQ(F.last_alloc_bytes, KB(16));
    CHECK_EQ(F.last_alloc_alignment, KB(16));
    CHECK_EQ(alloc_bo(client, KB(4) + 1, RW, &b, &value), SGPU_OK);
    CHECK_EQ(value, KB(16));
    CHECK_EQ(alloc_bo(client, 1, RW, &c, NULL), SGPU_LIMIT);
    CHECK_EQ(free_bo(client, a), SGPU_OK);
    CHECK_EQ(alloc_bo(client, 1, RW, &c, NULL), SGPU_OK);

    /* A failed backing allocation charges nothing. */
    setup(4096, KB(8), KB(8));
    client = open_client();
    F.fail_backing = 1;
    CHECK_EQ(alloc_bo(client, KB(8), RW, NULL, NULL), SGPU_BACKEND_ERROR);
    F.fail_backing = 0;
    CHECK_EQ(alloc_bo(client, KB(8), RW, NULL, NULL), SGPU_OK);
}

static void test_foreign_stale_and_confused_handles(void)
{
    uint64_t bo, again, context, fence, mapping, mangled;
    uint32_t a, b;
    struct fixture f;
    setup(4096, KB(256), KB(32));
    a = open_client();
    b = open_client();
    CHECK(a != b);
    CHECK_EQ(alloc_bo(a, KB(4), RW, &bo, NULL), SGPU_OK);
    CHECK_EQ(create_context(a, &context), SGPU_OK);

    CHECK_EQ(free_bo(b, bo), SGPU_BAD_FIELD);
    CHECK_EQ(cpu_map(b, bo, 0, KB(4), SGPU_READ, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(handle_op(b, SGPU_CONTEXT_DESTROY, context), SGPU_BAD_FIELD);

    /* A context handle is not a BO handle, and the reverse. */
    CHECK_EQ(free_bo(a, context), SGPU_BAD_FIELD);
    CHECK_EQ(handle_op(a, SGPU_CONTEXT_DESTROY, bo), SGPU_BAD_FIELD);

    /* Well-typed handles naming a slot outside the table or slot zero. */
    mangled = (bo & UINT64_C(0xFFFFFFFF00000000)) | (SGPU_BE_MAX_BOS + 1u);
    CHECK_EQ(free_bo(a, mangled), SGPU_BAD_FIELD);
    mangled = bo & UINT64_C(0xFFFFFFFF00000000);
    CHECK_EQ(free_bo(a, mangled), SGPU_BAD_FIELD);

    /* A freed slot is reused with a new generation; the old handle stays dead. */
    CHECK_EQ(free_bo(a, bo), SGPU_OK);
    CHECK_EQ(free_bo(a, bo), SGPU_BAD_FIELD);
    CHECK_EQ(alloc_bo(a, KB(4), RW, &again, NULL), SGPU_OK);
    CHECK(again != bo);
    CHECK_EQ((uint32_t)again, (uint32_t)bo);
    CHECK_EQ(free_bo(a, bo), SGPU_BAD_FIELD);

    CHECK_EQ(cpu_map(a, again, 0, KB(4), SGPU_READ, &mapping), SGPU_OK);
    CHECK_EQ(handle_op(b, SGPU_CPU_UNMAP, mapping), SGPU_BAD_FIELD);
    CHECK_EQ(handle_op(a, SGPU_CPU_UNMAP, mapping), SGPU_OK);
    CHECK_EQ(handle_op(a, SGPU_CPU_UNMAP, mapping), SGPU_BAD_FIELD);

    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, &fence, NULL), SGPU_OK);
    CHECK_EQ(wait_fence(b, fence, 0, NULL, NULL), SGPU_BAD_FIELD);

    /* A closed client's identity is dead even when its slot is reused. */
    sgpu_backend_client_close(BE, b);
    CHECK_EQ(alloc_bo(b, KB(4), RW, NULL, NULL), SGPU_BAD_FIELD);
    {
        uint32_t reopened = open_client();
        CHECK(reopened != b);
        CHECK_EQ(alloc_bo(b, KB(4), RW, NULL, NULL), SGPU_BAD_FIELD);
        CHECK_EQ(alloc_bo(reopened, KB(4), RW, NULL, NULL), SGPU_OK);
    }
}

static void test_free_and_destroy_need_no_references(void)
{
    struct fixture f;
    uint64_t mapping, fence, sequence;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);

    CHECK_EQ(free_bo(f.client, f.bo), SGPU_LIMIT); /* GPU mapping */
    CHECK_EQ(handle_op(f.client, SGPU_CONTEXT_DESTROY, f.context), SGPU_LIMIT);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
    CHECK_EQ(cpu_map(f.client, f.bo, 0, KB(4), SGPU_READ, &mapping), SGPU_OK);
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_LIMIT); /* CPU mapping */
    CHECK_EQ(handle_op(f.client, SGPU_CPU_UNMAP, mapping), SGPU_OK);

    CHECK_EQ(gpu_map(f.client, f.context, f.bo, VA, 0, KB(16), RW), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, &fence, &sequence), SGPU_OK);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_LIMIT); /* in flight */
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_LIMIT);
    CHECK_EQ(handle_op(f.client, SGPU_CONTEXT_DESTROY, f.context), SGPU_LIMIT);
    CHECK_EQ(F.free_calls, 0);
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_OK);
    CHECK_EQ(handle_op(f.client, SGPU_CONTEXT_DESTROY, f.context), SGPU_OK);
    CHECK_EQ(F.free_calls, 1);
    CHECK_EQ(F.context_destroy_calls, 1);
}

static void test_cpu_map_rules(void)
{
    uint64_t bo, read_only, mapping;
    uint32_t client;
    setup(16384, KB(256), KB(32));
    client = open_client();
    CHECK_EQ(alloc_bo(client, KB(32), RW, &bo, NULL), SGPU_OK);
    CHECK_EQ(alloc_bo(client, KB(16), SGPU_READ, &read_only, NULL), SGPU_OK);

    CHECK_EQ(cpu_map(client, bo, KB(4), KB(16), SGPU_READ, NULL), SGPU_BAD_FIELD); /* offset below CPU granule */
    CHECK_EQ(cpu_map(client, bo, 0, KB(4), SGPU_READ, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(cpu_map(client, bo, KB(16), KB(32), SGPU_READ, NULL), SGPU_BAD_FIELD); /* beyond backing */
    CHECK_EQ(cpu_map(client, read_only, 0, KB(16), RW, NULL), SGPU_BAD_FIELD);

    F.fail_cpu_map = 1;
    CHECK_EQ(cpu_map(client, bo, 0, KB(16), SGPU_READ, NULL), SGPU_BACKEND_ERROR);
    F.fail_cpu_map = 0;
    CHECK_EQ(free_bo(client, read_only), SGPU_OK);

    CHECK_EQ(cpu_map(client, bo, 0, KB(16), SGPU_READ, &mapping), SGPU_OK);
    CHECK_EQ(cpu_map(client, bo, KB(16), KB(16), SGPU_READ, NULL), SGPU_LIMIT); /* one mapping per BO */
    CHECK_EQ(handle_op(client, SGPU_CPU_UNMAP, mapping), SGPU_OK);
    CHECK_EQ(F.cpu_unmap_calls, 1);
}

static void test_gpu_map_rules(void)
{
    struct fixture a, b;
    uint64_t other_context, small, fence, sequence;
    setup(4096, KB(256), KB(64));
    a = make_fixture(VA);
    b = make_fixture(VA); /* Another client may use the same VA. */
    CHECK_EQ(create_context(a.client, &other_context), SGPU_OK);
    CHECK_EQ(alloc_bo(a.client, KB(8), SGPU_READ, &small, NULL), SGPU_OK);
    (void)b;

    CHECK_EQ(gpu_map(a.client, a.context, small, VA - KB(4), 0, KB(4), SGPU_READ), SGPU_BAD_FIELD); /* below window */
    CHECK_EQ(gpu_map(a.client, a.context, small, VA + (UINT64_C(1) << 32) - KB(4), 0, KB(8), SGPU_READ), SGPU_BAD_FIELD); /* past end */
    CHECK_EQ(gpu_map(a.client, a.context, small, VA + KB(12), 0, KB(8), SGPU_READ), SGPU_BAD_FIELD); /* overlap */
    CHECK_EQ(gpu_map(a.client, other_context, small, VA, 0, KB(8), SGPU_READ), SGPU_BAD_FIELD); /* client-wide VA */
    CHECK_EQ(gpu_map(a.client, a.context, small, VA + KB(64), KB(4), KB(8), SGPU_READ), SGPU_BAD_FIELD); /* beyond BO */
    CHECK_EQ(gpu_map(a.client, a.context, small, VA + KB(64), 0, KB(8), RW), SGPU_BAD_FIELD); /* more access than BO */
    CHECK_EQ(gpu_map(a.client, a.context, small, VA + 1, 0, KB(8), SGPU_READ), SGPU_BAD_FIELD); /* transport: unaligned */
    CHECK_EQ(gpu_map(a.client, a.context, small, UINT64_MAX - 4095, 0, KB(8), SGPU_READ), SGPU_BAD_FIELD); /* overflow */

    CHECK_EQ(gpu_map(a.client, a.context, small, VA + (UINT64_C(1) << 32) - KB(8), 0, KB(8), SGPU_READ), SGPU_OK); /* ends at window end */
    CHECK_EQ(gpu_unmap(a.client, a.context, VA + (UINT64_C(1) << 32) - KB(8), KB(4)), SGPU_BAD_FIELD); /* size must match */
    CHECK_EQ(gpu_unmap(a.client, a.context, VA + KB(128), KB(4)), SGPU_BAD_FIELD); /* absent */

    CHECK_EQ(submit_one(a.client, a.context, a.bo, SGPU_READ, NULL, 0, &fence, &sequence), SGPU_OK);
    CHECK_EQ(gpu_map(a.client, a.context, a.bo, VA + KB(256), 0, KB(4), SGPU_READ), SGPU_LIMIT); /* in flight */
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
}

static void test_cache_transitions(void)
{
    struct fixture f;
    uint64_t mapping, fence, sequence;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);

    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(4), SGPU_TO_GPU), SGPU_LIMIT); /* needs a CPU mapping */
    CHECK_EQ(cpu_map(f.client, f.bo, 0, KB(16), RW, &mapping), SGPU_OK);
    CHECK_EQ(cache_op(f.client, f.bo, KB(16), KB(4), SGPU_TO_GPU), SGPU_BAD_FIELD);

    /* A writable CPU mapping is dirty until cleaned. */
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(F.submit_calls, 0);
    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(4), SGPU_TO_CPU), SGPU_BAD_FIELD); /* conflicts with cpu_dirty */

    /* A failed sync changes nothing. */
    F.fail_cache = 1;
    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(16), SGPU_TO_GPU), SGPU_BACKEND_ERROR);
    F.fail_cache = 0;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);

    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(16), SGPU_TO_GPU), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(16), SGPU_TO_CPU), SGPU_LIMIT); /* in flight */
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);

    /* A GPU write leaves stale CPU caches until invalidated. */
    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(16), SGPU_TO_GPU), SGPU_BAD_FIELD);
    CHECK_EQ(handle_op(f.client, SGPU_CPU_UNMAP, mapping), SGPU_OK);
    CHECK_EQ(cpu_map(f.client, f.bo, 0, KB(16), RW, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(cpu_map(f.client, f.bo, 0, KB(16), SGPU_READ, &mapping), SGPU_OK);
    CHECK_EQ(cache_op(f.client, f.bo, 0, KB(16), SGPU_TO_CPU), SGPU_OK);
    CHECK_EQ(handle_op(f.client, SGPU_CPU_UNMAP, mapping), SGPU_OK);
    CHECK_EQ(cpu_map(f.client, f.bo, 0, KB(16), RW, &mapping), SGPU_OK);
}

static void test_submit_is_atomic(void)
{
    struct fixture f;
    uint64_t unmapped, stale_fence, sequence, fence;
    struct ib ibs[2];
    struct use uses[2];
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &unmapped, NULL), SGPU_OK);

    ibs[0].bo = f.bo; ibs[0].offset = 0; ibs[0].bytes = 16;
    uses[0].bo = f.bo; uses[0].access = RW;
    uses[1].bo = unmapped; uses[1].access = RW;

    /* The second BO is invalid: nothing may happen to the first. */
    CHECK_EQ(submit(f.client, f.context, ibs, 1, uses, 2, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(F.submit_calls, 0);

    /* A failing later IB also rejects the whole submission. */
    ibs[1].bo = f.bo; ibs[1].offset = KB(16); ibs[1].bytes = 16;
    uses[1].bo = f.bo;
    CHECK_EQ(submit(f.client, f.context, ibs, 2, uses, 1, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(F.submit_calls, 0);

    /* A fence from another slot generation is rejected before any effect. */
    stale_fence = UINT64_C(4) << 56 | UINT64_C(7) << 32 | 1;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &stale_fence, 1, NULL, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(F.submit_calls, 0);

    /* Hardware refusal leaves no reference and burns no sequence. */
    F.fail_submit = 1;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, NULL, NULL), SGPU_BACKEND_ERROR);
    F.fail_submit = 0;
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
    CHECK_EQ(gpu_map(f.client, f.context, f.bo, VA, 0, KB(16), RW), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
    CHECK_EQ(sequence, 1);
}

static void test_ib_translation_and_coverage(void)
{
    struct fixture f;
    uint64_t second_context, read_only_map, fence, sequence;
    struct ib ib;
    struct use use;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
    CHECK_EQ(gpu_map(f.client, f.context, f.bo, VA + KB(16), KB(4), KB(8), SGPU_READ), SGPU_OK);

    ib.bo = f.bo; ib.offset = KB(4) + 4; ib.bytes = 8;
    use.bo = f.bo; use.access = SGPU_READ;
    CHECK_EQ(submit(f.client, f.context, &ib, 1, &use, 1, NULL, 0, &fence, &sequence), SGPU_OK);
    CHECK_EQ(F.last_count, 1);
    CHECK_EQ(F.last_ibs[0].va, VA + KB(16) + 4);
    CHECK_EQ(F.last_ibs[0].bytes, 8);
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);

    ib.offset = KB(12) - 4; ib.bytes = 8; /* Crosses the end of the mapping. */
    CHECK_EQ(submit(f.client, f.context, &ib, 1, &use, 1, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);
    ib.offset = 0; ib.bytes = 8; /* Before the mapped range of the BO. */
    CHECK_EQ(submit(f.client, f.context, &ib, 1, &use, 1, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);

    /* A mapping in a different context does not count. */
    CHECK_EQ(create_context(f.client, &second_context), SGPU_OK);
    ib.offset = KB(4); ib.bytes = 8;
    CHECK_EQ(submit(f.client, second_context, &ib, 1, &use, 1, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);

    /* A use cannot exceed the access of its mapping. */
    use.access = RW;
    CHECK_EQ(submit(f.client, f.context, &ib, 1, &use, 1, NULL, 0, NULL, NULL), SGPU_BAD_FIELD);
    (void)read_only_map;
}

static void test_write_hazards(void)
{
    struct fixture f;
    uint64_t w1, r1, r2, w2, s1, s2, s3, deps[2];
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);

    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &w1, &s1), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, NULL, NULL), SGPU_BAD_FIELD); /* write after write */
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, NULL), SGPU_BAD_FIELD); /* read after write */
    CHECK_EQ(F.submit_calls, 1);

    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, &w1, 1, &r1, &s2), SGPU_OK);
    CHECK_EQ(sgpu_backend_retire(BE, s1, 0), 0);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, &r2, &s3), SGPU_OK); /* readers may overlap */

    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, NULL, NULL), SGPU_BAD_FIELD); /* write after reads */
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &r1, 1, NULL, NULL), SGPU_BAD_FIELD);  /* one reader uncovered */
    deps[0] = r1; deps[1] = r2;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, deps, 2, &w2, NULL), SGPU_OK);
    CHECK(w2 != 0);
}

static void test_reader_limit(void)
{
    struct fixture f;
    uint64_t sequence[SGPU_BE_MAX_READERS];
    unsigned i, before;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    for (i = 0; i < SGPU_BE_MAX_READERS; ++i) CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, &sequence[i]), SGPU_OK);
    before = F.submit_calls;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, NULL), SGPU_LIMIT);
    CHECK_EQ(F.submit_calls, before);
    CHECK_EQ(sgpu_backend_retire(BE, sequence[0], 0), 0);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, NULL), SGPU_OK);
}

static void test_two_reader_lifetime(void)
{
    struct fixture f;
    uint64_t s1, s2;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, &s1), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, NULL, &s2), SGPU_OK);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_LIMIT);
    CHECK_EQ(sgpu_backend_retire(BE, s1, 0), 0);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_LIMIT); /* second reader still running */
    CHECK_EQ(sgpu_backend_retire(BE, s2, 0), 0);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_OK);
}

static void test_wait_timeout_does_not_retire(void)
{
    struct fixture f;
    uint64_t fence, sequence;
    uint32_t state, reason;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);

    CHECK_EQ(wait_fence(f.client, fence, 0, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(wait_fence(f.client, fence, 1000, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_LIMIT); /* still in flight */
    CHECK_EQ(wait_fence(f.client, fence, SGPU_MAX_WAIT_NS + 1, NULL, NULL), SGPU_BAD_FIELD);

    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
    CHECK_EQ(wait_fence(f.client, fence, 0, &state, &reason), SGPU_OK);
    CHECK_EQ(state, SGPU_RETIRED);
    CHECK_EQ(reason, 0);
}

static void test_retirement_during_wait_and_errors(void)
{
    struct fixture f;
    uint64_t fence, sequence, errored, error_sequence;
    uint32_t state, reason;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);

    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
    F.retire_on_wait = sequence;
    CHECK_EQ(wait_fence(f.client, fence, 1000, &state, &reason), SGPU_OK);
    CHECK_EQ(state, SGPU_RETIRED);

    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, NULL, 0, &errored, &error_sequence), SGPU_OK);
    CHECK_EQ(sgpu_backend_retire(BE, error_sequence, 77), 0);
    CHECK_EQ(wait_fence(f.client, errored, 0, &state, &reason), SGPU_OK);
    CHECK_EQ(state, SGPU_RETIRED_ERROR);
    CHECK_EQ(reason, 77);

    /* An errored fence cannot order later work. */
    CHECK_EQ(submit_one(f.client, f.context, f.bo, SGPU_READ, &errored, 1, NULL, NULL), SGPU_BAD_FIELD);
}

static void test_spurious_retirement_is_ignored(void)
{
    struct fixture f;
    uint64_t fence, sequence;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);

    CHECK_EQ(sgpu_backend_retire(BE, sequence + 1, 0), -1);
    CHECK_EQ(sgpu_backend_retire(BE, 0, 0), -1);
    CHECK_EQ(wait_fence(f.client, fence, 0, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_LIMIT);

    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), -1); /* double retirement */
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
}

static void test_stop_blocks_new_work_only(void)
{
    struct fixture a, b;
    uint64_t fence, sequence, idle;
    unsigned before;
    setup(4096, KB(256), KB(32));
    a = make_fixture(VA);
    b = make_fixture(VA);
    CHECK_EQ(alloc_bo(a.client, KB(4), RW, &idle, NULL), SGPU_OK);
    CHECK_EQ(submit_one(a.client, a.context, a.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);

    before = F.wake_calls;
    CHECK_EQ(call(a.client, SGPU_STOP, NULL, 0, NULL), SGPU_OK);
    CHECK(F.wake_calls > before);

    CHECK_EQ(alloc_bo(a.client, KB(4), RW, NULL, NULL), SGPU_STOPPED);
    CHECK_EQ(create_context(a.client, NULL), SGPU_STOPPED);
    CHECK_EQ(cpu_map(a.client, idle, 0, KB(4), SGPU_READ, NULL), SGPU_STOPPED);
    CHECK_EQ(gpu_map(a.client, a.context, idle, VA + KB(64), 0, KB(4), SGPU_READ), SGPU_STOPPED);
    CHECK_EQ(submit_one(a.client, a.context, a.bo, RW, &fence, 1, NULL, NULL), SGPU_STOPPED);
    CHECK_EQ(wait_fence(a.client, fence, 1000, NULL, NULL), SGPU_STOPPED);

    /* Teardown stays possible, and in-flight work keeps its references. */
    CHECK_EQ(free_bo(a.client, idle), SGPU_OK);
    CHECK_EQ(free_bo(a.client, a.bo), SGPU_LIMIT);
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
    CHECK_EQ(wait_fence(a.client, fence, 0, NULL, NULL), SGPU_OK);

    /* Another client is unaffected. */
    CHECK_EQ(submit_one(b.client, b.context, b.bo, RW, NULL, 0, NULL, NULL), SGPU_OK);
}

static void test_fault_quarantine_and_quiesce(void)
{
    struct fixture f;
    uint64_t fence1, fence2, s1, s2, deps[1];
    uint32_t client = 0, state, reason;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    CHECK_EQ(sgpu_backend_quiesced(BE), -1); /* requires quarantine */

    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence1, &s1), SGPU_OK);
    deps[0] = fence1;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, deps, 1, &fence2, &s2), SGPU_OK);

    sgpu_backend_fault(BE, 5);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, NULL, NULL), SGPU_STOPPED);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &fence2, 1, NULL, NULL), SGPU_STOPPED);
    CHECK_EQ(sgpu_backend_client_open(BE, &client), SGPU_STOPPED);

    /* Quarantine retains everything; waiting neither retires nor releases. */
    CHECK_EQ(wait_fence(f.client, fence1, 1000, NULL, NULL), SGPU_TIMEOUT);
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_LIMIT);
    CHECK_EQ(F.free_calls, 0);

    /* A genuine retirement still counts while faulted. */
    CHECK_EQ(sgpu_backend_retire(BE, s1, 0), 0);
    CHECK_EQ(wait_fence(f.client, fence1, 0, &state, &reason), SGPU_OK);
    CHECK_EQ(state, SGPU_RETIRED);
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_LIMIT); /* second fence pending */

    CHECK_EQ(sgpu_backend_quiesced(BE), 0);
    CHECK_EQ(wait_fence(f.client, fence2, 0, &state, &reason), SGPU_OK);
    CHECK_EQ(state, SGPU_RETIRED_ERROR);
    CHECK_EQ(reason, SGPU_BE_REASON_QUIESCED);
    CHECK_EQ(sgpu_backend_quiesced(BE), -1); /* only once */

    /* Quiesced references can be released; new work stays refused. */
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_OK);
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_OK);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, NULL, NULL), SGPU_STOPPED);
}

static void test_client_close_with_work_in_flight(void)
{
    struct fixture f;
    uint64_t fence, sequence, mapped, mapping, idle;
    uint32_t other;
    setup(4096, KB(32), KB(16));
    f = make_fixture(VA);
    other = open_client();
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &idle, NULL), SGPU_OK);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &mapped, NULL), SGPU_OK);
    CHECK_EQ(cpu_map(f.client, mapped, 0, KB(4), RW, &mapping), SGPU_OK);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);

    sgpu_backend_client_close(BE, f.client);

    /* The CPU mapping and idle BOs go now; the running BO and its context do not. */
    CHECK_EQ(F.cpu_unmap_calls, 1);
    CHECK_EQ(F.free_calls, 2);
    CHECK_EQ(F.vm_unmap_calls, 0);
    CHECK_EQ(F.context_destroy_calls, 0);
    CHECK_EQ(alloc_bo(other, KB(16), RW, NULL, NULL), SGPU_OK); /* 16K retained, 16K free */
    CHECK_EQ(alloc_bo(other, KB(4), RW, NULL, NULL), SGPU_LIMIT);

    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
    CHECK_EQ(F.vm_unmap_calls, 1);
    CHECK_EQ(F.free_calls, 3);
    CHECK_EQ(F.context_destroy_calls, 1);
    CHECK_EQ(alloc_bo(other, KB(16), RW, NULL, NULL), SGPU_OK);
}

static void test_client_close_during_fault_waits_for_quiesce(void)
{
    struct fixture f;
    setup(4096, KB(32), KB(16));
    f = make_fixture(VA);
    sgpu_backend_fault(BE, 1);
    sgpu_backend_client_close(BE, f.client);
    CHECK_EQ(F.free_calls, 0);
    CHECK_EQ(F.vm_unmap_calls, 0);
    CHECK_EQ(F.context_destroy_calls, 0);
    CHECK_EQ(sgpu_backend_quiesced(BE), 0);
    CHECK_EQ(F.vm_unmap_calls, 1);
    CHECK_EQ(F.free_calls, 1);
    CHECK_EQ(F.context_destroy_calls, 1);
}

static void test_injected_hardware_failures(void)
{
    struct fixture f;
    uint64_t bo;
    uint32_t client;

    setup(4096, KB(256), KB(32));
    client = open_client();
    F.fail_context = 1;
    CHECK_EQ(create_context(client, NULL), SGPU_BACKEND_ERROR);
    F.fail_context = 0;

    f = make_fixture(VA);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &bo, NULL), SGPU_OK);
    F.fail_vm_map = 1;
    CHECK_EQ(gpu_map(f.client, f.context, bo, VA + KB(64), 0, KB(4), RW), SGPU_BACKEND_ERROR);
    F.fail_vm_map = 0;
    CHECK_EQ(free_bo(f.client, bo), SGPU_OK); /* nothing retained */

    /* TLB failure after mapping: PTEs are removed again and nothing is retained. */
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &bo, NULL), SGPU_OK);
    F.fail_tlb = 1;
    {
        unsigned unmaps = F.vm_unmap_calls;
        CHECK_EQ(gpu_map(f.client, f.context, bo, VA + KB(64), 0, KB(4), RW), SGPU_BACKEND_ERROR);
        CHECK_EQ(F.vm_unmap_calls, unmaps + 1);
    }
    F.fail_tlb = 0;
    CHECK_EQ(free_bo(f.client, bo), SGPU_OK);

    /* If the unwind also fails the range stays retained and the device stops. */
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, &bo, NULL), SGPU_OK);
    F.fail_tlb = 1; F.fail_vm_unmap = 1;
    CHECK_EQ(gpu_map(f.client, f.context, bo, VA + KB(64), 0, KB(4), RW), SGPU_BACKEND_ERROR);
    F.fail_tlb = 0; F.fail_vm_unmap = 0;
    CHECK_EQ(free_bo(f.client, bo), SGPU_LIMIT);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, NULL, NULL), SGPU_STOPPED);

    /* A failed unmap retains the mapping and stops new work. */
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    F.fail_vm_unmap = 1;
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_BACKEND_ERROR);
    F.fail_vm_unmap = 0;
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_LIMIT);
    CHECK_EQ(alloc_bo(f.client, KB(4), RW, NULL, NULL), SGPU_STOPPED);

    /* A failed TLB flush on unmap is treated the same way. */
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    F.fail_tlb = 1;
    CHECK_EQ(gpu_unmap(f.client, f.context, VA, KB(16)), SGPU_BACKEND_ERROR);
    F.fail_tlb = 0;
    CHECK_EQ(free_bo(f.client, f.bo), SGPU_LIMIT);
}

static void test_malformed_requests_never_reach_the_backend(void)
{
    uint8_t wire[SGPU_MAX_MESSAGE], p[SGPU_MAX_MESSAGE];
    struct fixture f;
    struct ib ib;
    struct use uses[2];
    uint64_t deps[2];
    unsigned before;
    size_t n;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);
    before = hw_effects();

    header(wire, SGPU_QUERY, 16);
    CHECK_EQ(call_raw(f.client, wire, 16, NULL), SGPU_BAD_SIZE);
    header(wire, SGPU_ALLOC, 56); sgpu_put32(wire, 0x12345678);
    CHECK_EQ(call_raw(f.client, wire, 56, NULL), SGPU_BAD_HEADER);
    header(wire, SGPU_ALLOC, 56); sgpu_put16(wire + 4, 2);
    CHECK_EQ(call_raw(f.client, wire, 56, NULL), SGPU_BAD_VERSION);
    header(wire, SGPU_ALLOC, 56); sgpu_put32(wire + 28, 1);
    CHECK_EQ(call_raw(f.client, wire, 56, NULL), SGPU_BAD_HEADER);
    header(wire, 99, 32);
    CHECK_EQ(call_raw(f.client, wire, 32, NULL), SGPU_UNSUPPORTED);
    header(wire, SGPU_FREE, 36);
    CHECK_EQ(call_raw(f.client, wire, 36, NULL), SGPU_BAD_SIZE);

    /* Alloc: zero size, bad alignment, no access. */
    CHECK_EQ(alloc_bo(f.client, 0, RW, NULL, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(alloc_bo(f.client, KB(4), 0, NULL, NULL), SGPU_BAD_FIELD);

    ib.bo = f.bo; ib.offset = 0; ib.bytes = 16;
    uses[0].bo = f.bo; uses[0].access = SGPU_READ;
    uses[1] = uses[0];

    /* Duplicate BO use and an IB with no read use. */
    n = build_submit(p, f.context, &ib, 1, uses, 2, NULL, 0);
    CHECK_EQ(call(f.client, SGPU_SUBMIT, p, n, NULL), SGPU_BAD_FIELD);
    uses[0].access = SGPU_WRITE;
    n = build_submit(p, f.context, &ib, 1, uses, 1, NULL, 0);
    CHECK_EQ(call(f.client, SGPU_SUBMIT, p, n, NULL), SGPU_BAD_FIELD);
    uses[0].access = SGPU_READ;

    /* Duplicate dependency, zero IBs, trailing bytes, misaligned IB. */
    deps[0] = 5; deps[1] = 5;
    n = build_submit(p, f.context, &ib, 1, uses, 1, deps, 2);
    CHECK_EQ(call(f.client, SGPU_SUBMIT, p, n, NULL), SGPU_BAD_FIELD);
    n = build_submit(p, f.context, &ib, 0, uses, 1, NULL, 0);
    CHECK_EQ(call(f.client, SGPU_SUBMIT, p, n, NULL), SGPU_LIMIT);
    n = build_submit(p, f.context, &ib, 1, uses, 1, NULL, 0);
    CHECK_EQ(call(f.client, SGPU_SUBMIT, p, n + 8, NULL), SGPU_BAD_SIZE);
    ib.offset = 2;
    n = build_submit(p, f.context, &ib, 1, uses, 1, NULL, 0);
    CHECK_EQ(call(f.client, SGPU_SUBMIT, p, n, NULL), SGPU_BAD_FIELD);

    CHECK_EQ(hw_effects(), before);
}

static void test_fence_table_exhaustion_and_eviction(void)
{
    static uint64_t fences[SGPU_BE_MAX_FENCES], sequences[SGPU_BE_MAX_FENCES];
    struct fixture f;
    uint64_t next, evicted_check;
    unsigned i, before;
    setup(4096, KB(256), KB(32));
    f = make_fixture(VA);

    /* Each write orders on the previous one, so all stay pending on one BO. */
    for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) {
        uint64_t *dep = i ? &fences[i - 1] : NULL;
        CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, dep, i ? 1 : 0, &fences[i], &sequences[i]), SGPU_OK);
    }
    before = F.submit_calls;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, &fences[SGPU_BE_MAX_FENCES - 1], 1, NULL, NULL), SGPU_LIMIT);
    CHECK_EQ(F.submit_calls, before);

    for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) CHECK_EQ(sgpu_backend_retire(BE, sequences[i], 0), 0);

    /* A rejected submit must not evict a retired fence. */
    F.fail_submit = 1;
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, NULL, NULL), SGPU_BACKEND_ERROR);
    F.fail_submit = 0;
    CHECK_EQ(wait_fence(f.client, fences[0], 0, NULL, NULL), SGPU_OK);

    /* A real submit evicts only the oldest retired fence. */
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &next, NULL), SGPU_OK);
    CHECK_EQ(wait_fence(f.client, fences[0], 0, NULL, NULL), SGPU_BAD_FIELD);
    CHECK_EQ(wait_fence(f.client, fences[1], 0, NULL, NULL), SGPU_OK);
    evicted_check = next;
    CHECK(evicted_check != fences[0]);
}

static void test_client_limit_and_generation_retirement(void)
{
    uint32_t clients[SGPU_BE_MAX_CLIENTS], extra = 0, first, last = 0;
    unsigned i;
    setup(4096, KB(64), KB(16));
    for (i = 0; i < SGPU_BE_MAX_CLIENTS; ++i) clients[i] = open_client();
    CHECK_EQ(sgpu_backend_client_open(BE, &extra), SGPU_LIMIT);
    first = clients[0];
    sgpu_backend_client_close(BE, first);

    /* Slot zero retires instead of wrapping its generation back to a used identity. */
    for (i = 0; i < 0xFFFEu; ++i) {
        last = open_client();
        CHECK_EQ(last & 0xFFFFu, 1);
        CHECK(last != first);
        sgpu_backend_client_close(BE, last);
    }
    CHECK_EQ(sgpu_backend_client_open(BE, &extra), SGPU_LIMIT);
    (void)last;
}

/* Threaded paths use a real mutex and condition variable; the single-threaded
 * paths above cannot catch a lost wakeup or an unlocked state access. */
struct worker_arg { unsigned delay_ms; uint64_t sequence; uint32_t client; int mode; };
enum { RETIRE, STOP_CLIENT, CLOSE_CLIENT };

static void sleep_ms(unsigned ms)
{
    struct timespec t;
    t.tv_sec = 0; t.tv_nsec = (long)ms * 1000000L;
    nanosleep(&t, NULL);
}

static void *worker(void *opaque)
{
    struct worker_arg *arg = (struct worker_arg *)opaque;
    sleep_ms(arg->delay_ms);
    if (arg->mode == RETIRE) CHECK_EQ(sgpu_backend_retire(BE, arg->sequence, 0), 0);
    else if (arg->mode == STOP_CLIENT) CHECK_EQ(call(arg->client, SGPU_STOP, NULL, 0, NULL), SGPU_OK);
    else sgpu_backend_client_close(BE, arg->client);
    return NULL;
}

static void setup_threaded(void)
{
    pthread_condattr_t attr;
    struct sgpu_be_config c = config_verified(4096, KB(1024), KB(32));
    reset_fake();
    F.threaded = 1;
    pthread_mutex_init(&F.mutex, NULL);
    pthread_condattr_init(&attr);
    pthread_condattr_setclock(&attr, CLOCK_MONOTONIC);
    pthread_cond_init(&F.cond, &attr);
    pthread_condattr_destroy(&attr);
    CHECK_EQ(sgpu_backend_init(BE, &c, &OPS, &F), SGPU_OK);
}

static void teardown_threaded(void)
{
    pthread_cond_destroy(&F.cond);
    pthread_mutex_destroy(&F.mutex);
    F.threaded = 0;
}

static uint64_t monotonic_ns(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

/* Workers act after 5ms. A lost wakeup shows up as sleeping out the whole 100ms. */
#define CHECK_WOKEN(start) CHECK(monotonic_ns() - (start) < SGPU_MAX_WAIT_NS * 3 / 4)

static void test_threaded_wait_wakeups(void)
{
    struct fixture f;
    struct worker_arg arg;
    pthread_t thread;
    uint64_t fence, sequence, start;
    uint32_t state, reason;

    setup_threaded();
    f = make_fixture(VA);
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
    arg.delay_ms = 5; arg.sequence = sequence; arg.client = 0; arg.mode = RETIRE;
    start = monotonic_ns();
    CHECK_EQ(pthread_create(&thread, NULL, worker, &arg), 0);
    CHECK_EQ(wait_fence(f.client, fence, SGPU_MAX_WAIT_NS, &state, &reason), SGPU_OK);
    CHECK_EQ(state, SGPU_RETIRED);
    CHECK_WOKEN(start);
    pthread_join(thread, NULL);

    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
    arg.mode = STOP_CLIENT; arg.client = f.client;
    start = monotonic_ns();
    CHECK_EQ(pthread_create(&thread, NULL, worker, &arg), 0);
    CHECK_EQ(wait_fence(f.client, fence, SGPU_MAX_WAIT_NS, NULL, NULL), SGPU_STOPPED);
    CHECK_WOKEN(start);
    pthread_join(thread, NULL);
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);

    f = make_fixture(VA + (UINT64_C(1) << 24));
    CHECK_EQ(submit_one(f.client, f.context, f.bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
    arg.mode = CLOSE_CLIENT; arg.client = f.client;
    start = monotonic_ns();
    CHECK_EQ(pthread_create(&thread, NULL, worker, &arg), 0);
    {
        uint32_t status = wait_fence(f.client, fence, SGPU_MAX_WAIT_NS, NULL, NULL);
        CHECK(status == SGPU_STOPPED || status == SGPU_BAD_FIELD);
    }
    CHECK_WOKEN(start);
    pthread_join(thread, NULL);
    CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
    teardown_threaded();
}

#define STRESS_THREADS 4
#define STRESS_ROUNDS 150

static void *stress_worker(void *opaque)
{
    struct fixture *f = (struct fixture *)opaque;
    unsigned i;
    for (i = 0; i < STRESS_ROUNDS; ++i) {
        uint64_t fence, sequence;
        uint32_t state, reason;
        CHECK_EQ(submit_one(f->client, f->context, f->bo, RW, NULL, 0, &fence, &sequence), SGPU_OK);
        CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), 0);
        CHECK_EQ(wait_fence(f->client, fence, SGPU_MAX_WAIT_NS, &state, &reason), SGPU_OK);
        CHECK_EQ(state, SGPU_RETIRED);
        CHECK_EQ(sgpu_backend_retire(BE, sequence, 0), -1);
    }
    return NULL;
}

static void test_threaded_concurrent_clients(void)
{
    struct fixture fixtures[STRESS_THREADS];
    pthread_t threads[STRESS_THREADS];
    unsigned i;
    setup_threaded();
    for (i = 0; i < STRESS_THREADS; ++i) fixtures[i] = make_fixture(VA + (uint64_t)i * (UINT64_C(1) << 24));
    for (i = 0; i < STRESS_THREADS; ++i) CHECK_EQ(pthread_create(&threads[i], NULL, stress_worker, &fixtures[i]), 0);
    for (i = 0; i < STRESS_THREADS; ++i) pthread_join(threads[i], NULL);
    for (i = 0; i < STRESS_THREADS; ++i) {
        CHECK_EQ(gpu_unmap(fixtures[i].client, fixtures[i].context, VA + (uint64_t)i * (UINT64_C(1) << 24), KB(16)), SGPU_OK);
        CHECK_EQ(free_bo(fixtures[i].client, fixtures[i].bo), SGPU_OK);
    }
    teardown_threaded();
}

int main(void)
{
    static void (*const tests[])(void) = {
        test_unverified_refuses_all_but_query, test_init_rejects_bad_profiles, test_verified_query_passes_reply_validation,
        test_page_accounting_and_budget, test_foreign_stale_and_confused_handles, test_free_and_destroy_need_no_references,
        test_cpu_map_rules, test_gpu_map_rules, test_cache_transitions, test_submit_is_atomic, test_ib_translation_and_coverage,
        test_write_hazards, test_reader_limit, test_two_reader_lifetime, test_wait_timeout_does_not_retire,
        test_retirement_during_wait_and_errors, test_spurious_retirement_is_ignored, test_stop_blocks_new_work_only,
        test_fault_quarantine_and_quiesce, test_client_close_with_work_in_flight, test_client_close_during_fault_waits_for_quiesce,
        test_injected_hardware_failures, test_malformed_requests_never_reach_the_backend, test_fence_table_exhaustion_and_eviction,
        test_client_limit_and_generation_retirement, test_threaded_wait_wakeups, test_threaded_concurrent_clients
    };
    size_t i, count = sizeof tests / sizeof tests[0];
    for (i = 0; i < count; ++i) tests[i]();
    printf("{\"outcome\":\"pass\",\"tests\":%zu}\n", count);
    return 0;
}
