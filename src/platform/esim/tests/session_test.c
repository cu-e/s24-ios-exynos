#include "session.h"
#include <assert.h>
#include <stdatomic.h>
#include <pthread.h>
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static unsigned groups;
static const uint8_t aid[] = {0x01, 0x02, 0x03, 0x04, 0x05};
static const uint8_t command[] = {0x00, 0xca, 0x00, 0x00, 0x00};

struct peer {
    struct esim_session *session;
    char events[64];
    size_t count;
    int connect_status, open_status, exchange_status, close_status, disconnect_status;
    int32_t open_handle;
    uint8_t seen_handle, close_handle;
    size_t seen_capacity;
    uint8_t seen_command[8];
    size_t reported_length;
    uint8_t answer[8];
    unsigned cancel_at;
    unsigned reenter;
    atomic_uint phase;
    unsigned concurrent_cancel;
};

static void event(struct peer *p, char value)
{
    assert(p->count + 1 < sizeof(p->events));
    p->events[p->count++] = value;
    p->events[p->count] = 0;
}

static int connect_peer(void *context)
{
    struct peer *p = context;
    event(p, 'C');
    if (p->cancel_at == 1) esim_request_cancel(p->session);
    return p->connect_status;
}

static int open_peer(void *context, const uint8_t *a, size_t length, int32_t *handle)
{
    struct peer *p = context;
    event(p, 'O');
    assert(length == sizeof(aid) && memcmp(a, aid, length) == 0);
    *handle = p->open_handle;
    if (p->cancel_at == 2) esim_request_cancel(p->session);
    return p->open_status;
}

static int exchange_peer(void *context, uint8_t handle, const uint8_t *tx,
                         size_t length, uint8_t *rx, size_t capacity, size_t *received)
{
    struct peer *p = context;
    event(p, 'X');
    p->seen_handle = handle;
    p->seen_capacity = capacity;
    assert(length <= sizeof(p->seen_command));
    memcpy(p->seen_command, tx, length);
    if (p->reenter) assert(esim_session_end(p->session) == ESIM_E_BUSY);
    if (p->cancel_at == 3) esim_request_cancel(p->session);
    if (p->concurrent_cancel) {
        unsigned i;
        atomic_store_explicit(&p->phase, 1, memory_order_release);
        for (i = 0; i < 1000000 && atomic_load_explicit(&p->phase, memory_order_acquire) != 2; i++)
            sched_yield();
        assert(atomic_load_explicit(&p->phase, memory_order_acquire) == 2);
    }
    size_t copied = p->reported_length < sizeof(p->answer) ? p->reported_length : sizeof(p->answer);
    if (copied > capacity) copied = capacity;
    memcpy(rx, p->answer, copied);
    *received = p->reported_length;
    return p->exchange_status;
}

static int close_peer(void *context, uint8_t handle)
{
    struct peer *p = context;
    event(p, 'L');
    p->close_handle = handle;
    if (p->cancel_at == 4) esim_request_cancel(p->session);
    return p->close_status;
}

static int disconnect_peer(void *context)
{
    struct peer *p = context;
    event(p, 'D');
    if (p->cancel_at == 5) esim_request_cancel(p->session);
    return p->disconnect_status;
}

static void setup(struct esim_session *s, struct peer *p)
{
    *p = (struct peer){.session = s, .open_handle = 7, .reported_length = 3,
                       .answer = {0xab, 0x90, 0x00}};
    atomic_init(&p->phase, 0);
    struct esim_transport t = {p, connect_peer, open_peer, exchange_peer, close_peer, disconnect_peer};
    struct esim_limits limits = {ESIM_MAX_COMMAND, 32, 3};
    assert(esim_session_init(s, &t, &limits) == ESIM_OK);
}

static enum esim_result exchange(struct esim_session *s, struct esim_reply *reply)
{
    uint8_t guarded[18];
    memset(guarded, 0xa5, sizeof(guarded));
    enum esim_result result = esim_session_exchange(s, command, sizeof(command), guarded + 1, 16, reply);
    assert(guarded[0] == 0xa5 && guarded[17] == 0xa5);
    return result;
}

static void parser_cases(void)
{
    struct { uint8_t b[14]; size_t n; uint32_t lc, le, offset; unsigned ext, has_le; } cases[] = {
        {{0,0x84,0,0},4,0,0,0,0,0},
        {{0,0xca,0,0,0},5,0,256,0,0,1},
        {{0,0xca,0,0,0x7f},5,0,127,0,0,1},
        {{0,0xda,0,0,3,1,2,3},8,3,0,5,0,0},
        {{0,0xda,0,0,3,1,2,3,0},9,3,256,5,0,1},
        {{0,0xca,0,0,0,0,0},7,0,65536,0,1,1},
        {{0,0xca,0,0,0,1,0},7,0,256,0,1,1},
        {{0,0xda,0,0,0,0,3,1,2,3},10,3,0,7,1,0},
        {{0,0xda,0,0,0,0,3,1,2,3,0,0},12,3,65536,7,1,1}
    };
    for (size_t i = 0; i < sizeof(cases)/sizeof(cases[0]); i++) {
        struct esim_apdu a;
        assert(esim_parse_command(cases[i].b, cases[i].n, &a) == ESIM_OK);
        assert(a.data_length == cases[i].lc && a.expected_length == cases[i].le &&
               a.data_offset == cases[i].offset && a.extended == cases[i].ext &&
               a.has_expected_length == cases[i].has_le);
    }
    groups++;
}

static void parser_invalid_and_boundaries(void)
{
    struct esim_apdu out;
    const uint8_t full[] = {0,0xda,0,0,3,1,2,3,0};
    for (size_t n = 0; n <= sizeof(full); n++) {
        int expected = n == 4 || n == 5 || n == 8 || n == 9;
        assert((esim_parse_command(full, n, &out) == ESIM_OK) == expected);
    }
    const uint8_t bad_ext[] = {0,0xda,0,0,0,0,0,0};
    assert(esim_parse_command(bad_ext, sizeof(bad_ext), &out) == ESIM_E_PROTOCOL);
    assert(out.data_length == 0 && out.extended == 0 && out.expected_length == 0);
    assert(esim_parse_command(NULL, 4, &out) == ESIM_E_ARGUMENT);
    assert(esim_parse_command(full, SIZE_MAX, &out) == ESIM_E_ARGUMENT);
    assert(esim_parse_command(full, 4, NULL) == ESIM_E_ARGUMENT);
    uint8_t maximum[ESIM_MAX_COMMAND] = {0,0xda,0,0,0,0xff,0xff};
    assert(esim_parse_command(maximum, sizeof(maximum), &out) == ESIM_OK);
    assert(out.data_length == 65535 && out.data_offset == 7 && out.expected_length == 65536);
    assert(esim_parse_command(maximum, sizeof(maximum) + 1u, &out) == ESIM_E_ARGUMENT);
    /* Every short Lc has two exact valid lengths; adjacent lengths are rejected. */
    uint8_t short_command[262] = {0,0xda,0,0};
    for (unsigned lc = 1; lc <= 255; lc++) {
        short_command[4] = (uint8_t)lc;
        assert(esim_parse_command(short_command, 5u + lc, &out) == ESIM_OK);
        assert(out.data_length == lc && !out.has_expected_length);
        assert(esim_parse_command(short_command, 6u + lc, &out) == ESIM_OK);
        assert(out.has_expected_length);
        assert(esim_parse_command(short_command, 7u + lc, &out) == ESIM_E_PROTOCOL);
    }
    groups++;
}

static void parser_guard_page(void)
{
    long page = sysconf(_SC_PAGESIZE);
    assert(page > 0);
    size_t extent = (size_t)page * 2;
    uint8_t *mapping = mmap(NULL,extent,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(mapping != MAP_FAILED);
    assert(mprotect(mapping + page,(size_t)page,PROT_NONE) == 0);
    const uint8_t packet[] = {0,0xda,0,0,3,1,2,3,0};
    for (size_t n = 0; n <= sizeof(packet); n++) {
        uint8_t *end = mapping + page - n;
        memcpy(end,packet,n);
        struct esim_apdu parsed;
        int expected = n == 4 || n == 5 || n == 8 || n == 9;
        assert((esim_parse_command(end,n,&parsed) == ESIM_OK) == expected);
    }
    struct esim_apdu parsed;
    /* Even an inaccessible non-null pointer must not be read for bad sizes. */
    assert(esim_parse_command(mapping+page,ESIM_MAX_COMMAND+1u,&parsed) == ESIM_E_ARGUMENT);
    assert(esim_parse_command(mapping+page,SIZE_MAX,&parsed) == ESIM_E_ARGUMENT);
    assert(munmap(mapping,extent) == 0);
    groups++;
}

static void normal_and_card_status(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply;
    setup(&s,&p);
    assert(esim_session_begin(&s, aid, sizeof(aid)) == ESIM_OK);
    assert(exchange(&s,&reply) == ESIM_OK);
    assert(reply.data_length == 1 && reply.sw1 == 0x90 && reply.sw2 == 0);
    assert(p.seen_handle == 7 && memcmp(p.seen_command,command,sizeof(command)) == 0);
    p.answer[1] = 0x69; p.answer[2] = 0x85;
    assert(exchange(&s,&reply) == ESIM_OK);
    assert(reply.sw1 == 0x69 && reply.sw2 == 0x85 && s.state == ESIM_OPEN);
    assert(esim_session_end(&s) == ESIM_OK);
    assert(strcmp(p.events,"COXXLD") == 0 && p.close_handle == 7);
    assert(esim_session_end(&s) == ESIM_OK && strcmp(p.events,"COXXLD") == 0);
    assert(esim_session_begin(&s, aid, sizeof(aid)) == ESIM_OK && s.exchanges == 0);
    assert(esim_session_end(&s) == ESIM_OK);
    groups++;
}

static void validation_never_issues_io(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply; uint8_t rx[8];
    setup(&s,&p);
    assert(esim_session_begin(&s, NULL, sizeof(aid)) == ESIM_E_ARGUMENT);
    assert(esim_session_begin(&s, aid, 0) == ESIM_E_ARGUMENT);
    assert(esim_session_begin(&s, aid, ESIM_MAX_AID + 1u) == ESIM_E_ARGUMENT);
    assert(esim_session_exchange(&s,command,sizeof(command),rx,sizeof(rx),&reply) == ESIM_E_STATE);
    assert(p.count == 0);
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_STATE);
    assert(esim_session_exchange(&s,command,3,rx,sizeof(rx),&reply) == ESIM_E_ARGUMENT);
    assert(esim_session_exchange(&s,command,sizeof(command),rx,1,&reply) == ESIM_E_ARGUMENT);
    assert(strcmp(p.events,"CO") == 0 && s.exchanges == 0);
    assert(esim_session_end(&s) == ESIM_OK);
    groups++;
}

static void begin_failures(void)
{
    struct esim_session s; struct peer p;
    setup(&s,&p); p.connect_status = -10;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_TRANSPORT);
    assert(strcmp(p.events,"CD") == 0 && s.state == ESIM_IDLE && s.backend_status == -10);
    setup(&s,&p); p.open_status = -20; p.open_handle = -1;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_TRANSPORT);
    assert(strcmp(p.events,"COD") == 0 && s.state == ESIM_IDLE);
    setup(&s,&p); p.open_status = -20; p.open_handle = 17;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_TRANSPORT);
    assert(strcmp(p.events,"COLD") == 0 && p.close_handle == 17);
    for (int32_t handle = 0; handle <= 256; handle += 256) {
        setup(&s,&p); p.open_handle = handle;
        assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_PROTOCOL);
        assert(strcmp(p.events,"COD") == 0 && s.state == ESIM_POISONED && s.cleanup_uncertain);
    }
    for (int32_t handle = 0; handle <= 256; handle += 256) {
        setup(&s,&p); p.open_status = -20; p.open_handle = handle;
        assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_TRANSPORT);
        assert(strcmp(p.events,"COD") == 0 && s.state == ESIM_POISONED && s.cleanup_uncertain);
    }
    setup(&s,&p); p.open_handle = 255;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    assert(esim_session_end(&s) == ESIM_OK && p.close_handle == 255);
    groups++;
}

static void exchange_failures_and_budget(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply;
    setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    p.exchange_status = -42;
    assert(exchange(&s,&reply) == ESIM_E_TRANSPORT && reply.length == 0 && reply.sw1 == 0);
    assert(strcmp(p.events,"COXLD") == 0 && s.backend_status == -42);
    for (size_t n = 0; n < 3; n++) {
        setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
        p.reported_length = n == 2 ? 17 : n;
        assert(exchange(&s,&reply) == ESIM_E_PROTOCOL && reply.length == 0);
        assert(strcmp(p.events,"COXLD") == 0);
    }
    setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    for (unsigned i = 0; i < 3; i++) assert(exchange(&s,&reply) == ESIM_OK);
    assert(exchange(&s,&reply) == ESIM_E_BUDGET);
    assert(strcmp(p.events,"COXXXLD") == 0 && s.state == ESIM_IDLE);
    groups++;
}

static void cleanup_uncertainty(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply;
    setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    p.close_status = -31;
    assert(esim_session_end(&s) == ESIM_E_CLEANUP);
    assert(s.state == ESIM_POISONED && s.cleanup_status == -31 && strcmp(p.events,"COLD") == 0);
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_CLEANUP);
    assert(esim_session_end(&s) == ESIM_E_CLEANUP && strcmp(p.events,"COLD") == 0);
    setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    p.exchange_status = -42; p.disconnect_status = -32;
    assert(exchange(&s,&reply) == ESIM_E_TRANSPORT);
    assert(s.last_error == ESIM_E_TRANSPORT && s.backend_status == -42 && s.cleanup_status == -32 && s.cleanup_uncertain);
    assert(s.state == ESIM_POISONED && strcmp(p.events,"COXLD") == 0);
    groups++;
}

static void cancellation_and_reentrancy(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply;
    setup(&s,&p); esim_request_cancel(&s);
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_CANCELLED && p.count == 0);
    for (unsigned phase = 1; phase <= 3; phase++) {
        setup(&s,&p); p.cancel_at = phase;
        if (phase < 3) assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_CANCELLED);
        else {
            assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
            assert(exchange(&s,&reply) == ESIM_E_CANCELLED && reply.length == 0);
        }
        assert(strcmp(p.events, phase == 1 ? "CD" : phase == 2 ? "COLD" : "COXLD") == 0);
        assert(s.state == ESIM_CLOSED && !s.channel_owned && !s.transport_owned);
        size_t old = p.count;
        assert(esim_service_cancel(&s) == ESIM_E_CANCELLED && p.count == old);
        assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_CANCELLED);
    }
    setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    esim_request_cancel(&s);
    assert(exchange(&s,&reply) == ESIM_E_CANCELLED && strcmp(p.events,"COLD") == 0);
    setup(&s,&p); p.reenter = 1; assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    assert(exchange(&s,&reply) == ESIM_OK && strcmp(p.events,"COX") == 0);
    assert(esim_session_end(&s) == ESIM_OK);
    setup(&s,&p); p.cancel_at = 3; p.close_status = -31;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    assert(exchange(&s,&reply) == ESIM_E_CANCELLED && s.state == ESIM_POISONED && s.cleanup_status == -31);
    groups++;
}

static void *cancel_thread(void *context)
{
    struct peer *p = context;
    unsigned i;
    for (i = 0; i < 1000000 && atomic_load_explicit(&p->phase,memory_order_acquire) != 1; i++)
        sched_yield();
    assert(atomic_load_explicit(&p->phase,memory_order_acquire) == 1);
    esim_request_cancel(p->session);
    atomic_store_explicit(&p->phase,2,memory_order_release);
    return NULL;
}

static void concurrent_cancellation(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply; pthread_t worker;
    setup(&s,&p); p.concurrent_cancel = 1;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    assert(pthread_create(&worker,NULL,cancel_thread,&p) == 0);
    assert(exchange(&s,&reply) == ESIM_E_CANCELLED);
    assert(pthread_join(worker,NULL) == 0);
    assert(strcmp(p.events,"COXLD") == 0 && s.state == ESIM_CLOSED && reply.length == 0);
    groups++;
}

static void init_and_capacity(void)
{
    struct esim_session s; struct peer p; struct esim_reply reply;
    struct esim_limits limits = {4,2,1};
    assert(esim_session_init(&s,NULL,&limits) == ESIM_E_ARGUMENT);
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_E_ARGUMENT);
    setup(&s,&p);
    struct esim_transport t = s.transport;
    limits.max_exchanges = 0;
    assert(esim_session_init(&s,&t,&limits) == ESIM_E_ARGUMENT);
    setup(&s,&p); s.limits.max_response = 2; p.reported_length = 2; p.answer[0] = 0x90; p.answer[1] = 0;
    assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
    assert(exchange(&s,&reply) == ESIM_OK && p.seen_capacity == 2 && reply.data_length == 0);
    assert(esim_session_end(&s) == ESIM_OK);
    groups++;
}

int main(void)
{
    parser_cases(); parser_invalid_and_boundaries(); parser_guard_page(); normal_and_card_status();
    validation_never_issues_io(); begin_failures(); exchange_failures_and_budget();
    cleanup_uncertainty(); cancellation_and_reentrancy(); concurrent_cancellation();
    init_and_capacity();
    printf("PASS %u scenario groups; synthetic backend only; no device or provisioning\n",groups);
    return 0;
}
