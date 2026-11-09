/* See sgpu_backend.h. Freestanding C: no allocator, no libc, single core lock. */
#include "sgpu_backend.h"

enum { TYPE_BO = 1, TYPE_CONTEXT = 2, TYPE_CPU_MAP = 3, TYPE_FENCE = 4 };
enum { FENCE_PENDING = 0, FENCE_RETIRED = 1, FENCE_ERROR = 2 };
#define GENERATION_MAX 0xFFFFFFu

/* What one client identity holds. Reset as a unit when a slot gets a new identity. */
struct be_charges {
    uint64_t budget_used;
    uint32_t bos, contexts, cpu_maps, gpu_maps, fences, reserved;
};

struct be_client {
    uint32_t live, generation, stopped, reserved;
    struct be_charges charged;
};

struct be_bo {
    uint32_t live, generation, client, zombie;
    uint64_t bytes, backing, token;
    uint32_t access, cpu_maps, gpu_maps, pending;
    uint32_t cpu_dirty, gpu_dirty, cpu_writable, writer, reader_count;
    uint32_t readers[SGPU_BE_MAX_READERS];
};

struct be_context {
    uint32_t live, generation, client, zombie;
    uint32_t engine, hw_context, pending, gpu_maps;
};

struct be_cpu_map {
    uint32_t live, generation, client, bo;
    uint64_t offset, bytes;
};

struct be_gpu_map {
    uint32_t live, context, bo, access;
    uint64_t va, offset, bytes;
};

struct be_use { uint32_t bo, access; };

struct be_fence {
    uint32_t live, generation, client, context;
    uint32_t state, reason, waiters, use_count;
    uint32_t wait_count, inherited;
    uint64_t sequence;
    uint64_t waits[SGPU_MAX_DEPS];
    struct be_use uses[SGPU_MAX_USES];
};

struct sgpu_backend {
    struct sgpu_be_config config;
    struct sgpu_be_ops ops;
    void *hw;
    uint64_t budget_used, next_sequence, spurious_retirements;
    uint32_t faulted, fault_reason, quiesced, zombies;
    struct be_client clients[SGPU_BE_MAX_CLIENTS];
    struct be_bo bos[SGPU_BE_MAX_BOS];
    struct be_context contexts[SGPU_BE_MAX_CONTEXTS];
    struct be_cpu_map cpu_maps[SGPU_BE_MAX_CPU_MAPS];
    struct be_gpu_map gpu_maps[SGPU_BE_MAX_GPU_MAPS];
    struct be_fence fences[SGPU_BE_MAX_FENCES];
};

static uint64_t make_handle(uint32_t type, uint32_t generation, uint32_t slot)
{
    return ((uint64_t)type << 56) | ((uint64_t)generation << 32) | (uint64_t)(slot + 1);
}

/* Returns 1 and the zero-based slot only for a well-formed handle of this type. */
static int parse_handle(uint64_t handle, uint32_t type, uint32_t limit, uint32_t *slot, uint32_t *generation)
{
    uint32_t low = (uint32_t)handle;
    if ((uint32_t)(handle >> 56) != type || low == 0 || low > limit) return 0;
    *slot = low - 1;
    *generation = (uint32_t)(handle >> 32) & GENERATION_MAX;
    return 1;
}

/* A slot whose generation is exhausted stays dead so a handle is never reissued. */
static void release_slot(uint32_t *live, uint32_t *generation)
{
    *live = 0;
    if (*generation < GENERATION_MAX) ++*generation;
}

static int slot_free(uint32_t live, uint32_t generation)
{
    return !live && generation < GENERATION_MAX;
}

static void zero_bytes(void *target, size_t bytes)
{
    volatile uint8_t *p = (volatile uint8_t *)target;
    while (bytes--) *p++ = 0;
}

static int round_up(uint64_t value, uint64_t alignment, uint64_t *result)
{
    uint64_t rounded;
    if (value > UINT64_MAX - (alignment - 1)) return 0;
    rounded = (value + alignment - 1) & ~(alignment - 1);
    *result = rounded;
    return 1;
}

static int range_within(uint64_t offset, uint64_t bytes, uint64_t limit)
{
    return bytes <= limit && offset <= limit - bytes;
}

static struct be_client *client_at(struct sgpu_backend *be, uint32_t id)
{
    uint32_t slot = (id & 0xFFFFu) - 1;
    if ((id & 0xFFFFu) == 0 || slot >= SGPU_BE_MAX_CLIENTS) return 0;
    if (!be->clients[slot].live || be->clients[slot].generation != (id >> 16)) return 0;
    return &be->clients[slot];
}

static struct be_bo *find_bo(struct sgpu_backend *be, uint32_t client, uint64_t handle)
{
    uint32_t slot, generation;
    struct be_bo *b;
    if (!parse_handle(handle, TYPE_BO, SGPU_BE_MAX_BOS, &slot, &generation)) return 0;
    b = &be->bos[slot];
    return (b->live && !b->zombie && b->generation == generation && b->client == client) ? b : 0;
}

static struct be_context *find_context(struct sgpu_backend *be, uint32_t client, uint64_t handle)
{
    uint32_t slot, generation;
    struct be_context *c;
    if (!parse_handle(handle, TYPE_CONTEXT, SGPU_BE_MAX_CONTEXTS, &slot, &generation)) return 0;
    c = &be->contexts[slot];
    return (c->live && !c->zombie && c->generation == generation && c->client == client) ? c : 0;
}

static struct be_fence *find_fence(struct sgpu_backend *be, uint32_t client, uint64_t handle)
{
    uint32_t slot, generation;
    struct be_fence *f;
    if (!parse_handle(handle, TYPE_FENCE, SGPU_BE_MAX_FENCES, &slot, &generation)) return 0;
    f = &be->fences[slot];
    return (f->live && f->generation == generation && f->client == client) ? f : 0;
}

/* Faulted and not yet proven idle: hardware may still reference anything mapped. */
static int quarantined(const struct sgpu_backend *be)
{
    return be->faulted && !be->quiesced;
}

static void hardware_failed(struct sgpu_backend *be)
{
    be->faulted = 1;
    be->fault_reason = SGPU_BE_REASON_FAULT;
}

/* A closed client's identity no longer resolves, so its zombies charge nobody. */
static void destroy_bo(struct sgpu_backend *be, struct be_bo *b)
{
    struct be_client *owner = client_at(be, b->client);
    be->ops.backing_free(be->hw, b->token, b->backing);
    be->budget_used -= b->backing;
    if (owner) owner->charged.budget_used -= b->backing;
    if (owner) --owner->charged.bos;
    if (b->zombie) { b->zombie = 0; --be->zombies; }
    release_slot(&b->live, &b->generation);
}

static void destroy_context(struct sgpu_backend *be, struct be_context *c)
{
    struct be_client *owner = client_at(be, c->client);
    be->ops.context_destroy(be->hw, c->hw_context);
    if (owner) --owner->charged.contexts;
    if (c->zombie) { c->zombie = 0; --be->zombies; }
    release_slot(&c->live, &c->generation);
}

/* Removes the mapping only after the hardware confirms PTE and TLB removal. */
static int remove_gpu_map(struct sgpu_backend *be, struct be_gpu_map *m)
{
    struct be_context *c = &be->contexts[m->context];
    struct be_client *owner = client_at(be, c->client);
    if (be->ops.vm_unmap(be->hw, c->hw_context, m->va, m->bytes) || be->ops.tlb_flush(be->hw, c->hw_context, m->va, m->bytes)) {
        hardware_failed(be);
        return 0;
    }
    --be->bos[m->bo].gpu_maps;
    --c->gpu_maps;
    if (owner) --owner->charged.gpu_maps;
    m->live = 0;
    return 1;
}

static void reap_zombies(struct sgpu_backend *be)
{
    uint32_t i;
    if (!be->zombies || quarantined(be)) return;
    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {
        struct be_gpu_map *m = &be->gpu_maps[i];
        if (m->live && be->bos[m->bo].zombie && !be->bos[m->bo].pending) {
            (void)remove_gpu_map(be, m);
            if (quarantined(be)) return; /* That removal failed: release nothing further. */
        }
    }
    for (i = 0; i < SGPU_BE_MAX_BOS; ++i) {
        struct be_bo *b = &be->bos[i];
        if (b->live && b->zombie && !b->pending && !b->gpu_maps && !b->cpu_maps) destroy_bo(be, b);
    }
    for (i = 0; i < SGPU_BE_MAX_CONTEXTS; ++i) {
        struct be_context *c = &be->contexts[i];
        if (c->live && c->zombie && !c->pending && !c->gpu_maps) destroy_context(be, c);
    }
}

/* Work ordered after a failure ran on bad input, whatever the hardware reports for
 * it. This is the in-flight form of SUBMIT refusing an errored dependency. Each
 * dependent passes the failure on when it retires in turn. */
static void taint_dependents(struct sgpu_backend *be, uint64_t sequence, uint32_t reason)
{
    uint32_t i, w;
    for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) {
        struct be_fence *d = &be->fences[i];
        if (!d->live || d->state != FENCE_PENDING || d->inherited) continue;
        for (w = 0; w < d->wait_count; ++w) if (d->waits[w] == sequence) d->inherited = reason;
    }
}

static void retire_fence(struct sgpu_backend *be, struct be_fence *f, uint32_t reason)
{
    uint32_t i;
    if (!reason) reason = f->inherited;
    if (reason) taint_dependents(be, f->sequence, reason);
    for (i = 0; i < f->use_count; ++i) {
        struct be_bo *b = &be->bos[f->uses[i].bo];
        uint32_t self = (uint32_t)(f - be->fences) + 1, r;
        --b->pending;
        if (f->uses[i].access & SGPU_WRITE) b->gpu_dirty = 1;
        if (b->writer == self) b->writer = 0;
        for (r = 0; r < b->reader_count;) {
            if (b->readers[r] == self) b->readers[r] = b->readers[--b->reader_count];
            else ++r;
        }
    }
    --be->contexts[f->context].pending;
    f->state = reason ? FENCE_ERROR : FENCE_RETIRED;
    f->reason = reason;
    reap_zombies(be);
    be->ops.wake(be->hw);
}

/* Chooses a slot without changing state; a retired fence is evicted only at commit.
 * A client evicts its own fences or a closed client's, never another live client's,
 * and at its quota it can only replace one of its own. */
static int choose_fence_slot(struct sgpu_backend *be, uint32_t client, uint32_t *slot)
{
    uint32_t i, best = SGPU_BE_MAX_FENCES;
    int may_grow = client_at(be, client)->charged.fences < SGPU_BE_CLIENT_MAX_FENCES;
    for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) {
        const struct be_fence *f = &be->fences[i];
        if (may_grow && slot_free(f->live, f->generation)) { *slot = i; return 1; }
        if (f->live && f->state != FENCE_PENDING && !f->waiters && f->generation < GENERATION_MAX
            && (f->client == client || (may_grow && !client_at(be, f->client)))
            && (best == SGPU_BE_MAX_FENCES || f->sequence < be->fences[best].sequence)) best = i;
    }
    if (best == SGPU_BE_MAX_FENCES) return 0;
    *slot = best;
    return 1;
}

static uint32_t accepting(const struct sgpu_backend *be, const struct be_client *c)
{
    return (c->stopped || be->faulted) ? SGPU_STOPPED : SGPU_OK;
}

/* Explicit teardown waits for quiescence, as client close does. */
static uint32_t releasing(const struct sgpu_backend *be)
{
    return quarantined(be) ? SGPU_STOPPED : SGPU_OK;
}

static void reply_object(struct sgpu_backend_result *r, uint64_t handle, uint64_t value)
{
    r->status = SGPU_OK;
    r->bytes = 16;
    sgpu_put64(r->payload, handle);
    sgpu_put64(r->payload + 8, value);
}

static void do_query(struct sgpu_backend *be, const uint8_t *p, struct sgpu_backend_result *r)
{
    const uint64_t features = SGPU_FEATURE_VALIDATION;
    if (sgpu_get64(p + 8) & ~features) { r->status = SGPU_UNSUPPORTED; return; }
    r->bytes = 88;
    sgpu_put64(r->payload, features);
    if (be->config.profile_verified) {
        sgpu_put64(r->payload + 8, be->config.epoch);
        sgpu_put64(r->payload + 16, be->config.client_budget_bytes);
        sgpu_put64(r->payload + 24, be->config.max_alloc_bytes);
        sgpu_put64(r->payload + 32, be->config.va_start);
        sgpu_put64(r->payload + 40, be->config.va_bytes);
        sgpu_put32(r->payload + 48, be->config.cpu_hardware_page);
        sgpu_put32(r->payload + 52, be->config.cpu_vm_page);
        sgpu_put32(r->payload + 56, (uint32_t)SGPU_GPU_PAGE);
        sgpu_put32(r->payload + 80, 1);
    }
    sgpu_put32(r->payload + 60, SGPU_MAX_MESSAGE);
    sgpu_put32(r->payload + 64, SGPU_MAX_IBS);
    sgpu_put32(r->payload + 68, SGPU_MAX_USES);
    sgpu_put32(r->payload + 72, SGPU_MAX_DEPS);
    sgpu_put32(r->payload + 76, (uint32_t)(SGPU_MAX_WAIT_NS / 1000000));
}

static uint32_t do_alloc(struct sgpu_backend *be, uint32_t client, const uint8_t *p, struct sgpu_backend_result *r)
{
    uint64_t size = sgpu_get64(p), alignment = sgpu_get64(p + 8), gpu_bytes, backing, token = 0;
    uint32_t access = sgpu_get32(p + 16), slot;
    struct be_client *owner = client_at(be, client);
    struct be_bo *b;
    if (size > be->config.max_alloc_bytes) return SGPU_LIMIT;
    if (!round_up(size, SGPU_GPU_PAGE, &gpu_bytes) || !round_up(gpu_bytes, be->config.cpu_vm_page, &backing)) return SGPU_BAD_FIELD;
    if (backing > be->config.budget_bytes - be->budget_used) return SGPU_LIMIT;
    if (backing > be->config.client_budget_bytes - owner->charged.budget_used) return SGPU_LIMIT;
    if (owner->charged.bos == SGPU_BE_CLIENT_MAX_BOS) return SGPU_LIMIT;
    if (alignment < be->config.cpu_vm_page) alignment = be->config.cpu_vm_page;
    for (slot = 0; slot < SGPU_BE_MAX_BOS && !slot_free(be->bos[slot].live, be->bos[slot].generation); ++slot) { }
    if (slot == SGPU_BE_MAX_BOS) return SGPU_LIMIT;
    if (be->ops.backing_alloc(be->hw, backing, alignment, &token)) return SGPU_BACKEND_ERROR;
    b = &be->bos[slot];
    b->live = 1; b->client = client; b->zombie = 0; b->bytes = gpu_bytes; b->backing = backing; b->token = token;
    b->access = access; b->cpu_maps = 0; b->gpu_maps = 0; b->pending = 0; b->cpu_dirty = 0; b->gpu_dirty = 0;
    b->cpu_writable = 0; b->writer = 0; b->reader_count = 0;
    be->budget_used += backing;
    owner->charged.budget_used += backing;
    ++owner->charged.bos;
    reply_object(r, make_handle(TYPE_BO, b->generation, slot), backing);
    return SGPU_OK;
}

static uint32_t do_free(struct sgpu_backend *be, uint32_t client, const uint8_t *p)
{
    struct be_bo *b = find_bo(be, client, sgpu_get64(p));
    if (!b) return SGPU_BAD_FIELD;
    if (b->pending || b->cpu_maps || b->gpu_maps) return SGPU_LIMIT;
    destroy_bo(be, b);
    return SGPU_OK;
}

static uint32_t do_context_create(struct sgpu_backend *be, uint32_t client, const uint8_t *p, struct sgpu_backend_result *r)
{
    uint32_t engine = sgpu_get32(p), slot, hw_context = 0;
    struct be_client *owner = client_at(be, client);
    struct be_context *c;
    if (owner->charged.contexts == SGPU_BE_CLIENT_MAX_CONTEXTS) return SGPU_LIMIT;
    for (slot = 0; slot < SGPU_BE_MAX_CONTEXTS && !slot_free(be->contexts[slot].live, be->contexts[slot].generation); ++slot) { }
    if (slot == SGPU_BE_MAX_CONTEXTS) return SGPU_LIMIT;
    if (be->ops.context_create(be->hw, engine, &hw_context)) return SGPU_BACKEND_ERROR;
    c = &be->contexts[slot];
    c->live = 1; c->client = client; c->zombie = 0; c->engine = engine; c->hw_context = hw_context; c->pending = 0; c->gpu_maps = 0;
    ++owner->charged.contexts;
    reply_object(r, make_handle(TYPE_CONTEXT, c->generation, slot), be->config.epoch);
    return SGPU_OK;
}

static uint32_t do_context_destroy(struct sgpu_backend *be, uint32_t client, const uint8_t *p)
{
    struct be_context *c = find_context(be, client, sgpu_get64(p));
    if (!c) return SGPU_BAD_FIELD;
    if (c->pending || c->gpu_maps) return SGPU_LIMIT;
    destroy_context(be, c);
    return SGPU_OK;
}

static uint32_t do_cpu_map(struct sgpu_backend *be, uint32_t client, const uint8_t *p, struct sgpu_backend_result *r)
{
    uint64_t handle = sgpu_get64(p), offset = sgpu_get64(p + 8), bytes = sgpu_get64(p + 16);
    uint32_t access = sgpu_get32(p + 24), slot, page = be->config.cpu_vm_page;
    struct be_bo *b = find_bo(be, client, handle);
    struct be_client *owner = client_at(be, client);
    struct be_cpu_map *m;
    if (!b || (access & ~b->access) || (access & SGPU_EXEC) || ((offset | bytes) & (page - 1u)) || !bytes || !range_within(offset, bytes, b->backing)) return SGPU_BAD_FIELD;
    if (b->pending || b->cpu_maps) return SGPU_LIMIT;
    if ((access & SGPU_WRITE) && b->gpu_dirty) return SGPU_BAD_FIELD;
    if (owner->charged.cpu_maps == SGPU_BE_CLIENT_MAX_CPU_MAPS) return SGPU_LIMIT;
    for (slot = 0; slot < SGPU_BE_MAX_CPU_MAPS && !slot_free(be->cpu_maps[slot].live, be->cpu_maps[slot].generation); ++slot) { }
    if (slot == SGPU_BE_MAX_CPU_MAPS) return SGPU_LIMIT;
    if (be->ops.cpu_map(be->hw, b->token, offset, bytes, access)) return SGPU_BACKEND_ERROR;
    m = &be->cpu_maps[slot];
    m->live = 1; m->client = client; m->bo = (uint32_t)(b - be->bos); m->offset = offset; m->bytes = bytes;
    ++b->cpu_maps;
    ++owner->charged.cpu_maps;
    if (access & SGPU_WRITE) b->cpu_dirty = 1;
    if (access & SGPU_WRITE) b->cpu_writable = 1;
    reply_object(r, make_handle(TYPE_CPU_MAP, m->generation, slot), bytes);
    return SGPU_OK;
}

static uint32_t do_cpu_unmap(struct sgpu_backend *be, uint32_t client, const uint8_t *p)
{
    uint32_t slot, generation;
    struct be_client *owner = client_at(be, client);
    struct be_cpu_map *m;
    if (!parse_handle(sgpu_get64(p), TYPE_CPU_MAP, SGPU_BE_MAX_CPU_MAPS, &slot, &generation)) return SGPU_BAD_FIELD;
    m = &be->cpu_maps[slot];
    if (!m->live || m->generation != generation || m->client != client) return SGPU_BAD_FIELD;
    if (be->bos[m->bo].pending) return SGPU_LIMIT;
    be->ops.cpu_unmap(be->hw, be->bos[m->bo].token, m->offset, m->bytes);
    --be->bos[m->bo].cpu_maps;
    be->bos[m->bo].cpu_writable = 0;
    --owner->charged.cpu_maps;
    release_slot(&m->live, &m->generation);
    return SGPU_OK;
}

static uint32_t do_gpu_map(struct sgpu_backend *be, uint32_t client, const uint8_t *p)
{
    uint64_t address = sgpu_get64(p + 16), offset = sgpu_get64(p + 24), bytes = sgpu_get64(p + 32);
    uint32_t access = sgpu_get32(p + 40), i, slot = SGPU_BE_MAX_GPU_MAPS;
    struct be_context *c = find_context(be, client, sgpu_get64(p));
    struct be_bo *b = find_bo(be, client, sgpu_get64(p + 8));
    uint64_t window_end, end;
    struct be_client *owner = client_at(be, client);
    struct be_gpu_map *m;
    if (!c || !b || (access & ~b->access) || !bytes) return SGPU_BAD_FIELD;
    if (address > UINT64_MAX - bytes) return SGPU_BAD_FIELD;
    end = address + bytes;
    window_end = be->config.va_start + be->config.va_bytes;
    if (address < be->config.va_start || end > window_end || !range_within(offset, bytes, b->bytes)) return SGPU_BAD_FIELD;
    if (b->pending) return SGPU_LIMIT;
    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {
        const struct be_gpu_map *other = &be->gpu_maps[i];
        if (!other->live) { if (slot == SGPU_BE_MAX_GPU_MAPS) slot = i; continue; }
        if (be->contexts[other->context].client == client && address < other->va + other->bytes && other->va < end) return SGPU_BAD_FIELD;
    }
    if (slot == SGPU_BE_MAX_GPU_MAPS || owner->charged.gpu_maps == SGPU_BE_CLIENT_MAX_GPU_MAPS) return SGPU_LIMIT;
    if (be->ops.vm_map(be->hw, c->hw_context, address, b->token, offset, bytes, access)) return SGPU_BACKEND_ERROR;
    /* The PTEs exist from here on. If the flush fails a running job may hold the
     * translation, so the range is retained and only quiescence can release it. */
    m = &be->gpu_maps[slot];
    m->live = 1; m->context = (uint32_t)(c - be->contexts); m->bo = (uint32_t)(b - be->bos); m->access = access; m->va = address; m->offset = offset; m->bytes = bytes;
    ++b->gpu_maps; ++c->gpu_maps;
    ++owner->charged.gpu_maps;
    if (be->ops.tlb_flush(be->hw, c->hw_context, address, bytes)) {
        hardware_failed(be);
        return SGPU_BACKEND_ERROR;
    }
    return SGPU_OK;
}

static uint32_t do_gpu_unmap(struct sgpu_backend *be, uint32_t client, const uint8_t *p)
{
    uint64_t address = sgpu_get64(p + 8), bytes = sgpu_get64(p + 16);
    struct be_context *c = find_context(be, client, sgpu_get64(p));
    uint32_t i;
    if (!c) return SGPU_BAD_FIELD;
    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {
        struct be_gpu_map *m = &be->gpu_maps[i];
        if (m->live && m->context == (uint32_t)(c - be->contexts) && m->va == address && m->bytes == bytes) {
            if (be->bos[m->bo].pending) return SGPU_LIMIT;
            return remove_gpu_map(be, m) ? SGPU_OK : SGPU_BACKEND_ERROR;
        }
    }
    return SGPU_BAD_FIELD;
}

static uint32_t do_cache(struct sgpu_backend *be, uint32_t client, const uint8_t *p)
{
    uint64_t offset = sgpu_get64(p + 8), bytes = sgpu_get64(p + 16);
    uint32_t direction = sgpu_get32(p + 24);
    struct be_bo *b = find_bo(be, client, sgpu_get64(p));
    if (!b || !bytes || !range_within(offset, bytes, b->bytes)) return SGPU_BAD_FIELD;
    if (b->pending || !b->cpu_maps) return SGPU_LIMIT;
    if (direction == SGPU_TO_GPU ? b->gpu_dirty : b->cpu_dirty) return SGPU_BAD_FIELD;
    if (be->ops.cache_sync(be->hw, b->token, offset, bytes, direction)) return SGPU_BACKEND_ERROR;
    /* The dirty state is per BO, so only a whole-buffer sync may clear it. The range
     * was bounded above, which makes bytes == b->bytes the whole buffer. */
    if (bytes == b->bytes) {
        if (direction == SGPU_TO_GPU) b->cpu_dirty = 0;
        else b->gpu_dirty = 0;
    }
    return SGPU_OK;
}

static const struct be_gpu_map *covering_map(const struct sgpu_backend *be, uint32_t context, uint32_t bo, uint64_t offset, uint64_t bytes, uint32_t access)
{
    uint32_t i;
    for (i = 0; i < SGPU_BE_MAX_GPU_MAPS; ++i) {
        const struct be_gpu_map *m = &be->gpu_maps[i];
        if (m->live && m->context == context && m->bo == bo && (m->access & access) == access && offset >= m->offset
            && bytes <= m->bytes && offset - m->offset <= m->bytes - bytes) return m;
    }
    return 0;
}

static int dependency_covers(const uint32_t *deps, uint32_t count, uint32_t fence_slot_plus_one)
{
    uint32_t i;
    for (i = 0; i < count; ++i) if (deps[i] == fence_slot_plus_one) return 1;
    return 0;
}

static uint32_t do_submit(struct sgpu_backend *be, uint32_t client, const uint8_t *p, struct sgpu_backend_result *r)
{
    struct be_context *c = find_context(be, client, sgpu_get64(p));
    uint32_t ib_count = sgpu_get32(p + 8), use_count = sgpu_get32(p + 12), dep_count = sgpu_get32(p + 16);
    const uint8_t *ibs = p + 24, *uses = ibs + 32u * ib_count, *deps = uses + 16u * use_count;
    struct sgpu_be_ib hw_ibs[SGPU_MAX_IBS];
    uint32_t dep_slots[SGPU_MAX_DEPS], bo_slots[SGPU_MAX_USES];
    uint64_t wait_sequences[SGPU_MAX_DEPS];
    uint32_t i, slot, context_slot, wait_count = 0;
    uint64_t sequence;
    struct be_client *owner = client_at(be, client);
    struct be_fence *f;
    if (!c) return SGPU_BAD_FIELD;
    context_slot = (uint32_t)(c - be->contexts);

    /* Everything is validated before any state or hardware changes. */
    for (i = 0; i < dep_count; ++i) {
        const struct be_fence *d = find_fence(be, client, sgpu_get64(deps + 8u * i));
        if (!d || d->state == FENCE_ERROR) return SGPU_BAD_FIELD;
        dep_slots[i] = (uint32_t)(d - be->fences) + 1;
        if (d->state == FENCE_PENDING) wait_sequences[wait_count++] = d->sequence;
    }
    for (i = 0; i < use_count; ++i) {
        const uint8_t *u = uses + 16u * i;
        struct be_bo *b = find_bo(be, client, sgpu_get64(u));
        uint32_t access = sgpu_get32(u + 8), reader, map, earlier;
        int mapped = 0;
        if (!b || (access & ~b->access) || b->cpu_dirty) return SGPU_BAD_FIELD;
        for (map = 0; map < SGPU_BE_MAX_GPU_MAPS && !mapped; ++map) {
            const struct be_gpu_map *m = &be->gpu_maps[map];
            mapped = m->live && m->context == context_slot && m->bo == (uint32_t)(b - be->bos) && (m->access & access) == access;
        }
        if (!mapped) return SGPU_BAD_FIELD;
        bo_slots[i] = (uint32_t)(b - be->bos);
        /* The transport already rejects duplicates; the reader array relies on it. */
        for (earlier = 0; earlier < i; ++earlier) if (bo_slots[earlier] == bo_slots[i]) return SGPU_BAD_FIELD;
        if (b->writer && be->fences[b->writer - 1].state == FENCE_PENDING && !dependency_covers(dep_slots, dep_count, b->writer)) return SGPU_BAD_FIELD;
        if (access & SGPU_WRITE) {
            for (reader = 0; reader < b->reader_count; ++reader)
                if (!dependency_covers(dep_slots, dep_count, b->readers[reader])) return SGPU_BAD_FIELD;
        } else if (b->reader_count == SGPU_BE_MAX_READERS) {
            return SGPU_LIMIT;
        }
    }
    for (i = 0; i < ib_count; ++i) {
        const uint8_t *ib = ibs + 32u * i;
        uint64_t handle = sgpu_get64(ib), offset = sgpu_get64(ib + 8), bytes = sgpu_get64(ib + 16);
        struct be_bo *b = find_bo(be, client, handle);
        const struct be_gpu_map *map;
        if (!b || b->cpu_writable || !range_within(offset, bytes, b->bytes)) return SGPU_BAD_FIELD;
        map = covering_map(be, context_slot, (uint32_t)(b - be->bos), offset, bytes, SGPU_READ);
        if (!map) return SGPU_BAD_FIELD;
        hw_ibs[i].va = map->va + (offset - map->offset);
        hw_ibs[i].bytes = (uint32_t)bytes;
        hw_ibs[i].flags = sgpu_get32(ib + 24);
    }
    if (!choose_fence_slot(be, client, &slot)) return SGPU_LIMIT;
    sequence = be->next_sequence + 1;
    if (be->ops.submit(be->hw, c->hw_context, hw_ibs, ib_count, wait_sequences, wait_count, sequence)) return SGPU_BACKEND_ERROR;

    be->next_sequence = sequence;
    f = &be->fences[slot];
    if (f->live) {
        struct be_client *previous = client_at(be, f->client);
        if (previous) --previous->charged.fences;
        release_slot(&f->live, &f->generation);
    }
    ++owner->charged.fences;
    f->live = 1; f->client = client; f->context = context_slot; f->state = FENCE_PENDING; f->reason = 0;
    f->waiters = 0; f->use_count = use_count; f->sequence = sequence;
    f->inherited = 0;
    f->wait_count = wait_count;
    for (i = 0; i < wait_count; ++i) f->waits[i] = wait_sequences[i];
    ++c->pending;
    for (i = 0; i < use_count; ++i) {
        struct be_bo *b = &be->bos[bo_slots[i]];
        uint32_t access = sgpu_get32(uses + 16u * i + 8);
        f->uses[i].bo = bo_slots[i];
        f->uses[i].access = access;
        ++b->pending;
        if (access & SGPU_WRITE) {
            b->writer = slot + 1;
            b->reader_count = 0;
        } else {
            b->readers[b->reader_count++] = slot + 1;
        }
    }
    reply_object(r, make_handle(TYPE_FENCE, f->generation, slot), sequence);
    return SGPU_OK;
}

static uint32_t do_wait(struct sgpu_backend *be, uint32_t client, const uint8_t *p, struct sgpu_backend_result *r)
{
    struct be_fence *f = find_fence(be, client, sgpu_get64(p));
    uint64_t timeout = sgpu_get64(p + 8), deadline, now;
    uint32_t status = SGPU_OK;
    if (!f) return SGPU_BAD_FIELD;
    now = be->ops.now_ns(be->hw);
    deadline = (timeout > UINT64_MAX - now) ? UINT64_MAX : now + timeout;
    ++f->waiters;
    while (f->state == FENCE_PENDING) {
        const struct be_client *owner = client_at(be, client);
        if (!owner || owner->stopped) { status = SGPU_STOPPED; break; }
        now = be->ops.now_ns(be->hw);
        if (now >= deadline) { status = SGPU_TIMEOUT; break; }
        be->ops.wait_locked(be->hw, deadline - now);
    }
    --f->waiters;
    if (status != SGPU_OK) return status;
    r->bytes = 8;
    sgpu_put32(r->payload, f->state == FENCE_RETIRED ? SGPU_RETIRED : SGPU_RETIRED_ERROR);
    sgpu_put32(r->payload + 4, f->reason);
    return SGPU_OK;
}

size_t sgpu_backend_storage_size(void)
{
    return sizeof(struct sgpu_backend);
}

uint32_t sgpu_backend_init(struct sgpu_backend *be, const struct sgpu_be_config *config, const struct sgpu_be_ops *ops, void *hw)
{
    if (!be || !config || !ops || !ops->lock || !ops->unlock || !ops->now_ns || !ops->wait_locked || !ops->wake || !ops->backing_alloc || !ops->backing_free
        || !ops->cpu_map || !ops->cpu_unmap || !ops->context_create || !ops->context_destroy || !ops->vm_map || !ops->vm_unmap || !ops->tlb_flush || !ops->cache_sync || !ops->submit) return SGPU_BAD_FIELD;
    if (config->profile_verified > 1 || config->reserved) return SGPU_BAD_FIELD;
    if (config->profile_verified) {
        if ((config->cpu_vm_page != 4096u && config->cpu_vm_page != 16384u) || (config->cpu_hardware_page != 4096u && config->cpu_hardware_page != 16384u)) return SGPU_BAD_FIELD;
        if (!config->epoch || !config->max_alloc_bytes || config->max_alloc_bytes > config->client_budget_bytes || config->client_budget_bytes > config->budget_bytes || config->max_alloc_bytes > SGPU_MAX_ALLOC_BYTES) return SGPU_BAD_FIELD;
        if (((config->va_start | config->va_bytes) & (SGPU_GPU_PAGE - 1)) || !config->va_start || !config->va_bytes || config->va_start > UINT64_MAX - config->va_bytes) return SGPU_BAD_FIELD;
    } else if (config->budget_bytes || config->client_budget_bytes || config->max_alloc_bytes || config->va_start || config->va_bytes || config->epoch || config->cpu_hardware_page || config->cpu_vm_page) {
        /* Unverified configurations may not advertise any profile values. */
        return SGPU_BAD_FIELD;
    }
    zero_bytes(be, sizeof(*be));
    be->config = *config;
    be->ops = *ops;
    be->hw = hw;
    return SGPU_OK;
}

uint32_t sgpu_backend_client_open(struct sgpu_backend *be, uint32_t *client)
{
    uint32_t slot;
    if (!be || !client) return SGPU_BAD_FIELD;
    be->ops.lock(be->hw);
    if (be->faulted) { be->ops.unlock(be->hw); return SGPU_STOPPED; }
    for (slot = 0; slot < SGPU_BE_MAX_CLIENTS; ++slot) {
        if (slot_free(be->clients[slot].live, be->clients[slot].generation) && be->clients[slot].generation < 0xFFFFu) break;
    }
    if (slot == SGPU_BE_MAX_CLIENTS) { be->ops.unlock(be->hw); return SGPU_LIMIT; }
    be->clients[slot].live = 1;
    be->clients[slot].stopped = 0;
    zero_bytes(&be->clients[slot].charged, sizeof be->clients[slot].charged);
    *client = (be->clients[slot].generation << 16) | (slot + 1);
    be->ops.unlock(be->hw);
    return SGPU_OK;
}

/* Releases what the hardware no longer references. Anything else stays retained
 * until a trusted retirement or quiescence observation reaps it. */
void sgpu_backend_client_close(struct sgpu_backend *be, uint32_t id)
{
    struct be_client *owner;
    uint32_t i;
    if (!be) return;
    be->ops.lock(be->hw);
    owner = client_at(be, id);
    if (!owner) { be->ops.unlock(be->hw); return; }
    owner->stopped = 1;
    for (i = 0; i < SGPU_BE_MAX_CPU_MAPS; ++i) {
        struct be_cpu_map *m = &be->cpu_maps[i];
        if (m->live && m->client == id) {
            be->ops.cpu_unmap(be->hw, be->bos[m->bo].token, m->offset, m->bytes);
            --be->bos[m->bo].cpu_maps;
            release_slot(&m->live, &m->generation);
        }
    }
    for (i = 0; i < SGPU_BE_MAX_BOS; ++i) {
        struct be_bo *b = &be->bos[i];
        if (b->live && b->client == id) { b->zombie = 1; ++be->zombies; }
    }
    for (i = 0; i < SGPU_BE_MAX_CONTEXTS; ++i) {
        struct be_context *c = &be->contexts[i];
        if (c->live && c->client == id) { c->zombie = 1; ++be->zombies; }
    }
    /* Pending fences keep their references; retired ones become unreachable handles. */
    for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) {
        struct be_fence *f = &be->fences[i];
        if (f->live && f->client == id && f->state != FENCE_PENDING && !f->waiters) release_slot(&f->live, &f->generation);
    }
    reap_zombies(be);
    owner->live = 0;
    owner->generation = (owner->generation + 1) & 0xFFFFu;
    be->ops.wake(be->hw);
    be->ops.unlock(be->hw);
}

void sgpu_backend_dispatch(void *opaque, const struct sgpu_request_view *v, struct sgpu_backend_result *r)
{
    const struct sgpu_be_binding *binding = (const struct sgpu_be_binding *)opaque;
    struct sgpu_backend *be;
    struct be_client *owner;
    uint32_t status = SGPU_UNSUPPORTED, client;
    if (!binding || !binding->backend) { r->status = SGPU_BAD_FIELD; return; }
    be = binding->backend;
    client = binding->client;
    be->ops.lock(be->hw);
    owner = client_at(be, client);
    if (!owner) {
        status = SGPU_BAD_FIELD;
    } else if (v->opcode == SGPU_QUERY) {
        do_query(be, v->payload, r);
        status = r->status;
    } else if (be->config.profile_verified) {
        switch (v->opcode) {
        case SGPU_STOP: owner->stopped = 1; be->ops.wake(be->hw); status = SGPU_OK; break;
        case SGPU_ALLOC: status = accepting(be, owner); if (!status) status = do_alloc(be, client, v->payload, r); break;
        case SGPU_FREE: status = releasing(be); if (!status) status = do_free(be, client, v->payload); break;
        case SGPU_CONTEXT_CREATE: status = accepting(be, owner); if (!status) status = do_context_create(be, client, v->payload, r); break;
        case SGPU_CONTEXT_DESTROY: status = releasing(be); if (!status) status = do_context_destroy(be, client, v->payload); break;
        case SGPU_CPU_MAP: status = accepting(be, owner); if (!status) status = do_cpu_map(be, client, v->payload, r); break;
        case SGPU_CPU_UNMAP: status = do_cpu_unmap(be, client, v->payload); break;
        case SGPU_GPU_MAP: status = accepting(be, owner); if (!status) status = do_gpu_map(be, client, v->payload); break;
        case SGPU_GPU_UNMAP: status = releasing(be); if (!status) status = do_gpu_unmap(be, client, v->payload); break;
        case SGPU_CACHE: status = do_cache(be, client, v->payload); break;
        case SGPU_SUBMIT: status = accepting(be, owner); if (!status) status = do_submit(be, client, v->payload, r); break;
        case SGPU_WAIT: status = do_wait(be, client, v->payload, r); break;
        default: status = SGPU_UNSUPPORTED; break;
        }
    }
    be->ops.unlock(be->hw);
    r->status = status;
    if (status != SGPU_OK) r->bytes = 0;
}

int sgpu_backend_retire(struct sgpu_backend *be, uint64_t sequence, uint32_t reason)
{
    uint32_t i;
    int result = -1;
    if (!be) return -1;
    be->ops.lock(be->hw);
    for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) {
        struct be_fence *f = &be->fences[i];
        if (f->live && f->state == FENCE_PENDING && f->sequence == sequence) {
            retire_fence(be, f, reason);
            result = 0;
            break;
        }
    }
    if (result) ++be->spurious_retirements;
    be->ops.unlock(be->hw);
    return result;
}

void sgpu_backend_fault(struct sgpu_backend *be, uint32_t reason)
{
    if (!be) return;
    be->ops.lock(be->hw);
    be->faulted = 1;
    be->fault_reason = reason ? reason : SGPU_BE_REASON_FAULT;
    be->ops.wake(be->hw);
    be->ops.unlock(be->hw);
}

int sgpu_backend_quiesced(struct sgpu_backend *be)
{
    uint32_t i;
    int accepted;
    if (!be) return -1;
    be->ops.lock(be->hw);
    accepted = be->faulted && !be->quiesced;
    if (accepted) {
        be->quiesced = 1;
        for (i = 0; i < SGPU_BE_MAX_FENCES; ++i) {
            struct be_fence *f = &be->fences[i];
            if (f->live && f->state == FENCE_PENDING) retire_fence(be, f, SGPU_BE_REASON_QUIESCED);
        }
        reap_zombies(be);
    }
    be->ops.unlock(be->hw);
    return accepted ? 0 : -1;
}
