/* Owned host negative/mutation harness, not a native kernel entrypoint. */
#include "sgpu_fake.h"
#include <stdio.h>
#include <string.h>

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "check failed at line %d: %s\n", __LINE__, #c); return 1; } } while (0)

static size_t packet(uint8_t *b, uint32_t op, uint32_t payload)
{
    memset(b, 0, SGPU_MAX_MESSAGE);
    sgpu_put32(b, SGPU_MAGIC); sgpu_put16(b + 4, 1);
    sgpu_put32(b + 8, op); sgpu_put32(b + 12, 32 + payload); sgpu_put64(b + 16, 123);
    return 32 + payload;
}

static size_t query(uint8_t *b)
{
    size_t n = packet(b, SGPU_QUERY, 16);
    sgpu_put16(b + 32, 1); sgpu_put16(b + 34, 1);
    return n;
}

static void broken_backend(void *context, const struct sgpu_request_view *v, struct sgpu_backend_result *r)
{
    uint32_t mode = *(const uint32_t *)context;
    (void)v;
    r->bytes = 88;
    sgpu_put64(r->payload, SGPU_FEATURE_SYNTHETIC | SGPU_FEATURE_VALIDATION);
    sgpu_put32(r->payload + 60, SGPU_MAX_MESSAGE);
    switch (mode) {
    case 1: r->bytes = 89; break;
    case 2: r->status = UINT32_MAX; break;
    case 3: r->status = SGPU_TIMEOUT; break; /* error must not carry payload */
    case 4: sgpu_put32(r->payload + 84, 1); break;
    case 5: sgpu_put32(r->payload + 60, SGPU_MAX_MESSAGE + 1); break;
    case 6: sgpu_put32(r->payload + 80, 1); break; /* fake cannot claim native */
    case 7: sgpu_put32(r->payload + 52, 4096); break; /* unknown profile has no page claim */
    default: r->bytes = 0; r->status = SGPU_UNSUPPORTED; break;
    }
}

static uint32_t next_random(uint32_t *state)
{
    *state ^= *state << 13; *state ^= *state >> 17; *state ^= *state << 5;
    return *state;
}

/* Trusted callback fixtures test reply validation, not a client completion API.
 * They do not allocate backing or assert a physical GPU result. */
static void reply_fixture(void *context, const struct sgpu_request_view *v, struct sgpu_backend_result *r)
{
    uint32_t mode = *(const uint32_t *)context;
    if (v->opcode == SGPU_ALLOC || v->opcode == SGPU_CPU_MAP) {
        r->bytes = 16;
        sgpu_put64(r->payload, mode == 0 ? 0 : 1234);
        sgpu_put64(r->payload + 8, mode == 2 ? 0 : mode == 3 ? 1 : 4096);
    } else if (v->opcode == SGPU_WAIT) {
        if (mode == 4) { r->status = SGPU_TIMEOUT; return; }
        r->bytes = 8;
        sgpu_put32(r->payload, mode == 0 ? 0 : mode == 3 ? SGPU_RETIRED_ERROR : SGPU_RETIRED);
        sgpu_put32(r->payload + 4, mode == 2 || mode == 3 ? 42 : 0);
    } else {
        r->bytes = 8; /* unexpected payload on an empty-response operation */
    }
}

int main(void)
{
    uint8_t input[SGPU_MAX_MESSAGE], original[SGPU_MAX_MESSAGE];
    uint8_t output[136];
    size_t n, used, i, iterations = 50000, rejected = 0, dispatched = 0;
    uint32_t mode, status, random_state = UINT32_C(0x2400940);
    struct sgpu_fake state = {0, 0, 0};
    n = query(input);
    memset(output, 0xA5, sizeof(output));
    CHECK(sgpu_fake_exchange(&state, input, n, output + 8, 120, &used) == SGPU_OK);
    CHECK(used == 120 && state.calls == 1);
    CHECK(sgpu_get64(output + 40) == (SGPU_FEATURE_VALIDATION | SGPU_FEATURE_SYNTHETIC));
    for (mode = 1; mode <= 7; ++mode) {
        memset(output, 0xA5, sizeof(output));
        CHECK(sgpu_dispatch(input, n, output + 8, 120, &used, broken_backend, &mode) == SGPU_BAD_REPLY);
        CHECK(used == 32);
        for (i = 40; i < 128; ++i) CHECK(output[i] == 0);
    }
    /* Query an unsupported mandatory feature: no silent weaker success. */
    sgpu_put64(input + 40, 2);
    CHECK(sgpu_fake_exchange(&state, input, n, output + 8, 120, &used) == SGPU_UNSUPPORTED);
    CHECK(used == 32);
    n = packet(input, SGPU_ALLOC, 24);
    sgpu_put64(input + 32, 4096); sgpu_put64(input + 40, 4096); sgpu_put32(input + 48, 3);
    for (mode = 0; mode <= 3; ++mode) {
        status = sgpu_dispatch(input, n, output + 8, 120, &used, reply_fixture, &mode);
        CHECK(status == (mode == 1 ? SGPU_OK : SGPU_BAD_REPLY));
        CHECK(used == (mode == 1 ? 48 : 32));
    }
    n = packet(input, SGPU_CPU_MAP, 32);
    sgpu_put64(input + 32, 7); sgpu_put64(input + 48, 4096); sgpu_put32(input + 56, 3);
    for (mode = 1; mode <= 3; mode += 2) {
        status = sgpu_dispatch(input, n, output + 8, 120, &used, reply_fixture, &mode);
        CHECK(status == (mode == 1 ? SGPU_OK : SGPU_BAD_REPLY));
        CHECK(used == (mode == 1 ? 48 : 32));
    }
    n = packet(input, SGPU_WAIT, 16); sgpu_put64(input + 32, 99);
    for (mode = 0; mode <= 4; ++mode) {
        status = sgpu_dispatch(input, n, output + 8, 120, &used, reply_fixture, &mode);
        CHECK(status == (mode == 0 || mode == 2 ? SGPU_BAD_REPLY : mode == 4 ? SGPU_TIMEOUT : SGPU_OK));
        CHECK(used == (mode == 1 || mode == 3 ? 40 : 32));
    }
    n = packet(input, SGPU_STOP, 0);
    CHECK(sgpu_dispatch(input, n, output + 8, 120, &used, reply_fixture, &mode) == SGPU_BAD_REPLY);
    CHECK(used == 32);
    /* Canonical submit fixture for targeted count/array mutations. */
    n = packet(original, SGPU_SUBMIT, 80);
    sgpu_put64(original + 32, 1); sgpu_put32(original + 40, 1);
    sgpu_put32(original + 44, 1); sgpu_put32(original + 48, 1);
    sgpu_put64(original + 56, 7); sgpu_put64(original + 72, 16);
    sgpu_put64(original + 88, 7); sgpu_put32(original + 96, SGPU_READ);
    sgpu_put64(original + 104, 99);
    CHECK(sgpu_fake_exchange(&state, original, n, output + 8, 120, &used) == SGPU_UNSUPPORTED);
    for (i = 0; i < iterations; ++i) {
        uint64_t before = state.calls;
        size_t j, length = n;
        memcpy(input, original, sizeof(input));
        /* Mix prefix truncations, header-consistent payload truncations,
         * bit flips, giant array counts and valid canonical requests. */
        switch (i % 5) {
        case 0: length = next_random(&random_state) % (SGPU_MAX_MESSAGE + 1); break;
        case 1: length = 32 + next_random(&random_state) % 81; sgpu_put32(input + 12, (uint32_t)length); break;
        case 2: input[next_random(&random_state) % n] ^= (uint8_t)(1u << (next_random(&random_state) % 8)); break;
        case 3: sgpu_put32(input + 40 + 4 * (next_random(&random_state) % 3), next_random(&random_state)); break;
        default: break;
        }
        memset(output, 0xA5, sizeof(output));
        status = sgpu_fake_exchange(&state, input, length, output + 8, 120, &used);
        CHECK(used == 32); /* fake never manufactures submit/fence success */
        CHECK(status != SGPU_OK);
        if (state.calls == before) ++rejected;
        else { CHECK(state.calls == before + 1); ++dispatched; }
        for (j = 0; j < 8; ++j) CHECK(output[j] == 0xA5 && output[128 + j] == 0xA5);
        for (j = 40; j < 128; ++j) CHECK(output[j] == 0);
    }
    CHECK(rejected > 30000 && dispatched >= 10000);
    printf("{\"environment\":\"synthetic-host-transport\",\"outcome\":\"pass\",\"mutation_attempts\":%zu,\"rejected_before_backend\":%zu,\"dispatched_unsupported\":%zu,\"bad_reply_cases\":14,\"additional_reply_controls\":5,\"device_io\":false}\n", iterations, rejected, dispatched);
    return 0;
}
