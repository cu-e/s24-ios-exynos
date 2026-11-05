/* Independently authored review controls; synthetic callbacks, no device I/O. */
#include "session.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static unsigned long parser_checks, sessions;
static uint8_t bytes[ESIM_MAX_COMMAND + 1u];

static void check(size_t length, int valid, unsigned lc, unsigned le,
                  unsigned offset, unsigned extended, unsigned has_le)
{
    struct esim_apdu a = {.data_length = UINT32_MAX};
    enum esim_result result = esim_parse_command(bytes, length, &a);
    assert((result == ESIM_OK) == valid);
    if (valid) {
        assert(a.data_length == lc && a.expected_length == le);
        assert(a.data_offset == offset && a.extended == extended);
        assert(a.has_expected_length == has_le);
    } else {
        assert(a.data_length == 0 && a.expected_length == 0 && a.data_offset == 0);
        assert(a.extended == 0 && a.has_expected_length == 0);
    }
    parser_checks++;
}

static void parser(void)
{
    memset(bytes, 0, sizeof(bytes));
    check(4,1,0,0,0,0,0);
    for (unsigned le = 0; le < 256; le++) {
        bytes[4] = (uint8_t)le;
        check(5,1,0,le ? le : 256u,0,0,1);
    }
    for (unsigned lc = 1; lc < 256; lc++) {
        memset(bytes, 0, sizeof(bytes)); bytes[4] = (uint8_t)lc;
        check(5u+lc,1,lc,0,5,0,0);
        bytes[5u+lc] = 0x80;
        check(6u+lc,1,lc,128,5,0,1);
        check(7u+lc,0,0,0,0,0,0);
    }
    for (unsigned le = 0; le < 65536; le++) {
        bytes[4] = 0; bytes[5] = (uint8_t)(le >> 8); bytes[6] = (uint8_t)le;
        check(7,1,0,le ? le : 65536u,0,1,1);
    }
    for (unsigned lc = 1; lc < 65536; lc++) {
        bytes[4] = 0; bytes[5] = (uint8_t)(lc >> 8); bytes[6] = (uint8_t)lc;
        check(7u+lc,1,lc,0,7,1,0);
        bytes[7u+lc] = 0x12; bytes[8u+lc] = 0x34;
        check(9u+lc,1,lc,0x1234,7,1,1);
        check(8u+lc,0,0,0,0,0,0);
    }
    check(sizeof(bytes),0,0,0,0,0,0);
    check(SIZE_MAX,0,0,0,0,0,0);
}

struct peer {
    struct esim_session *s;
    int32_t handle;
    int open_status, close_status, disconnect_status, exchange_status;
    unsigned connect_calls, open_calls, exchange_calls, close_calls, disconnect_calls;
    unsigned cancel_at;
    uint8_t cla;
};
static const uint8_t aid[] = {1};

static void reentrant(struct peer *p, unsigned phase)
{
    uint8_t cmd[] = {0,0,0,0}, response[2]; struct esim_reply reply;
    assert(esim_session_begin(p->s,aid,sizeof(aid)) == ESIM_E_BUSY);
    assert(esim_session_exchange(p->s,cmd,sizeof(cmd),response,sizeof(response),&reply) == ESIM_E_BUSY);
    assert(esim_session_end(p->s) == ESIM_E_BUSY);
    assert(esim_service_cancel(p->s) == ESIM_E_BUSY);
    if (p->cancel_at == phase) esim_request_cancel(p->s);
}
static int connect_peer(void *context)
{
    struct peer *p = context; p->connect_calls++; reentrant(p,1); return 0;
}
static int open_peer(void *context, const uint8_t *a, size_t n, int32_t *h)
{
    struct peer *p = context; assert(a && n == 1); p->open_calls++;
    *h = p->handle; reentrant(p,2); return p->open_status;
}
static int exchange_peer(void *context, uint8_t h, const uint8_t *tx, size_t n,
                         uint8_t *rx, size_t capacity, size_t *length)
{
    struct peer *p = context; p->exchange_calls++;
    assert(h == (uint8_t)p->handle && n == 4 && tx[0] == p->cla && capacity == 2);
    rx[0] = 0x69; rx[1] = 0x85; *length = 2; reentrant(p,3);
    return p->exchange_status;
}
static int close_peer(void *context, uint8_t h)
{
    struct peer *p = context; assert(h == (uint8_t)p->handle);
    p->close_calls++; assert(p->close_calls == 1); reentrant(p,4);
    return p->close_status;
}
static int disconnect_peer(void *context)
{
    struct peer *p = context; p->disconnect_calls++;
    assert(p->disconnect_calls == 1); reentrant(p,5); return p->disconnect_status;
}
static void setup(struct esim_session *s, struct peer *p)
{
    p->s = s;
    struct esim_transport t = {p,connect_peer,open_peer,exchange_peer,close_peer,disconnect_peer};
    struct esim_limits limits = {ESIM_MAX_COMMAND,2,4096};
    assert(esim_session_init(s,&t,&limits) == ESIM_OK);
    sessions++;
}
static void handle_matrix(void)
{
    const int32_t handles[] = {INT32_MIN,-2,-1,0,1,19,20,255,256,INT32_MAX};
    for (unsigned i = 0; i < sizeof(handles)/sizeof(handles[0]); i++) {
        for (unsigned failed = 0; failed < 2; failed++) {
            struct esim_session s; struct peer p = {.handle = handles[i],.open_status = failed ? -17 : 0};
            setup(&s,&p);
            int valid = handles[i] >= 1 && handles[i] <= 255;
            int poisoned = !valid && !(failed && handles[i] == -1);
            enum esim_result expected = failed ? ESIM_E_TRANSPORT : valid ? ESIM_OK : ESIM_E_PROTOCOL;
            assert(esim_session_begin(&s,aid,sizeof(aid)) == expected);
            if (expected == ESIM_OK) assert(esim_session_end(&s) == ESIM_OK);
            assert(s.state == (poisoned ? ESIM_POISONED : ESIM_IDLE));
            assert(p.close_calls == (unsigned)valid && p.disconnect_calls == 1);
            assert(esim_session_end(&s) == (poisoned ? ESIM_E_CLEANUP : ESIM_OK));
            assert(p.disconnect_calls == 1 && p.close_calls == (unsigned)valid);
        }
    }
}
static void cla_and_cleanup(void)
{
    for (unsigned cla = 0; cla < 256; cla++) {
        struct esim_session s; struct peer p = {.handle = 255,.cla = (uint8_t)cla};
        uint8_t cmd[] = {(uint8_t)cla,0,0,0}, response[4]; struct esim_reply reply;
        setup(&s,&p); assert(esim_session_begin(&s,aid,sizeof(aid)) == ESIM_OK);
        assert(esim_session_exchange(&s,cmd,sizeof(cmd),response,sizeof(response),&reply) == ESIM_OK);
        assert(reply.sw1 == 0x69 && reply.sw2 == 0x85 && !reply.data_length);
        assert(esim_session_end(&s) == ESIM_OK);
    }
    for (unsigned cancel = 0; cancel <= 5; cancel++) {
        for (unsigned errors = 0; errors < 8; errors++) {
            struct esim_session s; struct peer p = {.handle = 1,.cancel_at = cancel,
                .close_status = (errors & 1u) ? -31 : 0,
                .disconnect_status = (errors & 2u) ? -32 : 0,
                .exchange_status = (errors & 4u) ? -33 : 0};
            uint8_t cmd[] = {0,0,0,0}, response[2]; struct esim_reply reply;
            setup(&s,&p);
            enum esim_result result = esim_session_begin(&s,aid,sizeof(aid));
            if (cancel == 1 || cancel == 2) assert(result == ESIM_E_CANCELLED);
            else {
                assert(result == ESIM_OK);
                result = esim_session_exchange(&s,cmd,sizeof(cmd),response,sizeof(response),&reply);
                if (cancel == 3) assert(result == ESIM_E_CANCELLED && !reply.length);
                else if (p.exchange_status) assert(result == ESIM_E_TRANSPORT && s.backend_status == -33 && !reply.length);
                else assert(result == ESIM_OK);
                (void)esim_session_end(&s);
            }
            assert(!s.channel_owned && !s.transport_owned && !s.busy);
            assert(p.close_calls == (cancel == 1 ? 0u : 1u) && p.disconnect_calls == 1);
            int uncertain = p.disconnect_status || (cancel != 1 && p.close_status);
            assert(s.state == (uncertain ? ESIM_POISONED : cancel ? ESIM_CLOSED : ESIM_IDLE));
            (void)esim_session_end(&s); (void)esim_service_cancel(&s);
            assert(p.disconnect_calls == 1 && p.close_calls <= 1);
        }
    }
}
int main(void)
{
    parser(); handle_matrix(); cla_and_cleanup();
    printf("PASS independent boundary controls: %lu parser cases, %lu synthetic sessions; no hardware\n",parser_checks,sessions);
    return 0;
}
