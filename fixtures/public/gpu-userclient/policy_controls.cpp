/* HOST TEST ONLY. Synthetic task identities/callbacks; no Apple class shims.
 * Compile/run only after root admits the shared resource budget and lease.
 */
#include "../../../src/platform/gpu/native/userclient/Policy.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

using namespace s24gpu;
static unsigned checks;
#define CHECK(value) do { ++checks; if (!(value)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #value); std::abort(); } } while (0)

struct Probe {
    unsigned calls;
    uint8_t *original;
    bool mutate;
    bool bad_reply;
};

static void fixture_callback(void *raw, const sgpu_request_view *view, sgpu_backend_result *reply)
{
    auto &probe = *static_cast<Probe *>(raw);
    ++probe.calls;
    if (probe.mutate) {
        sgpu_put64(probe.original + 32, 99);
        CHECK(view->payload != probe.original + 32);
        CHECK(sgpu_get64(view->payload) == 4096);
        CHECK(view->request_id == 7);
    }
    reply->status = SGPU_UNSUPPORTED;
    reply->bytes = 0;
    if (probe.bad_reply) { reply->status = SGPU_OK; reply->bytes = 88; }
}

static Shape shape(uint8_t *input, size_t bytes, uint8_t *output)
{
    return {true, 0, 0, 0, 0, 0, false, false, false, false, false, false,
            input, bytes, output, SGPU_MAX_MESSAGE};
}

static void packet(uint8_t *bytes, uint32_t opcode, uint32_t size)
{
    std::memset(bytes, 0, SGPU_MAX_MESSAGE);
    sgpu_put32(bytes, SGPU_MAGIC);
    sgpu_put16(bytes + 4, SGPU_ABI_MAJOR);
    sgpu_put16(bytes + 6, SGPU_ABI_MINOR);
    sgpu_put32(bytes + 8, opcode);
    sgpu_put32(bytes + 12, size);
    sgpu_put64(bytes + 16, 7);
}

int main()
{
    constexpr uintptr_t original_task = 0x101, other_task = 0x202;
    uint8_t input[SGPU_MAX_MESSAGE], output[SGPU_MAX_MESSAGE];
    Storage storage = {};
    packet(input, SGPU_STOP, 32);
    auto call = shape(input, 32, output);
    Session refused = {};
    CHECK(admit(refused, original_task, false, true) == Transport::not_privileged);
    CHECK(admit(refused, 0, true, true) == Transport::not_privileged);
    CHECK(admit(refused, original_task, true, false) == Transport::not_ready);
    CHECK(!refused.provider_hold && refused.phase == Phase::unopened);

    Session session = {};
    CHECK(admit(session, original_task, true, true) == Transport::ok);
    CHECK(admit(session, original_task, true, true) == Transport::busy);
    CHECK(begin(session, other_task, call, true) == Transport::not_privileged);
    CHECK(begin(session, original_task, call, false) == Transport::not_ready);

    for (unsigned mode = 0; mode < 23; ++mode) {
        Shape bad = call;
        switch (mode) {
        case 0: bad.current_argument_version = false; break;
        case 1: bad.selector = bad.argument_selector = 1; break;
        case 2: bad.argument_selector = 1; break;
        case 3: bad.scalar_inputs = 1; break;
        case 4: bad.scalar_outputs = 1; break;
        case 5: bad.async_references = 1; break;
        case 6: bad.async_port = true; break;
        case 7: bad.async_pointer = true; break;
        case 8: bad.input_descriptor = true; break;
        case 9: bad.output_descriptor = true; break;
        case 10: bad.variable_output = true; break;
        case 11: bad.reserved_nonzero = true; break;
        case 12: bad.input = nullptr; break;
        case 13: bad.input_bytes = 31; break;
        case 14: bad.input_bytes = SGPU_MAX_MESSAGE + 1; break;
        case 15: bad.output = nullptr; break;
        case 16: bad.output_capacity = 119; break;
        case 17: bad.output_capacity = SGPU_MAX_MESSAGE + 1; break;
        case 18: bad.output = input; break;
        case 19: bad.output = input + 16; bad.output_capacity = 120; break;
        case 20: bad.input = reinterpret_cast<void *>(UINTPTR_MAX - 3); break;
        case 21: bad.output = reinterpret_cast<void *>(UINTPTR_MAX - 3); break;
        case 22: bad.input_bytes = 0; break;
        }
        CHECK(begin(session, original_task, bad, true) != Transport::ok);
        CHECK(session.active_calls == 0 && session.provider_hold);
    }

    Probe probe = {};
    std::memset(output, 0xa5, sizeof(output));
    CHECK(begin(session, original_task, call, true) == Transport::ok);
    CHECK(begin(session, original_task, call, true) == Transport::busy);
    auto result = snapshot_dispatch(call, storage, fixture_callback, &probe);
    CHECK(result.transport == Transport::ok && result.protocol_status == SGPU_UNSUPPORTED && result.bytes == 32);
    CHECK(sgpu_get32(output + 24) == SGPU_UNSUPPORTED && sgpu_get32(output + 12) == 32);
    CHECK(output[32] == 0xa5); // Caller publishes exactly result.bytes.
    CHECK(probe.calls == 1);
    finish(session, result.protocol_status);

    // The actual existing wire validator rejects malformed input before callback.
    input[0] ^= 1;
    CHECK(begin(session, original_task, call, true) == Transport::ok);
    result = snapshot_dispatch(call, storage, fixture_callback, &probe);
    CHECK(result.transport == Transport::ok && result.protocol_status == SGPU_BAD_HEADER && result.bytes == 32);
    CHECK(probe.calls == 1);
    finish(session, result.protocol_status);

    packet(input, SGPU_ALLOC, 56);
    sgpu_put64(input + 32, 4096);
    sgpu_put64(input + 40, SGPU_GPU_PAGE);
    sgpu_put32(input + 48, SGPU_READ);
    call = shape(input, 56, output);
    probe.original = input;
    probe.mutate = true;
    CHECK(begin(session, original_task, call, true) == Transport::ok);
    result = snapshot_dispatch(call, storage, fixture_callback, &probe);
    CHECK(result.transport == Transport::ok && result.protocol_status == SGPU_UNSUPPORTED);
    CHECK(sgpu_get64(input + 32) == 99 && sgpu_get64(storage.input + 32) == 4096);
    finish(session, result.protocol_status);

    Shape overlap = call;
    overlap.input = storage.input;
    CHECK(snapshot_dispatch(overlap, storage, fixture_callback, &probe).transport == Transport::bad_argument);
    overlap = call;
    overlap.output = storage.output;
    CHECK(snapshot_dispatch(overlap, storage, fixture_callback, &probe).transport == Transport::bad_argument);
    CHECK(snapshot_dispatch(call, storage, nullptr, nullptr).transport == Transport::bad_argument);

    // Malformed backend reply faults admission; errors do not release a session.
    packet(input, SGPU_QUERY, 48);
    sgpu_put16(input + 32, 1); sgpu_put16(input + 34, 1);
    probe.mutate = false; probe.bad_reply = true;
    call = shape(input, 48, output);
    CHECK(begin(session, original_task, call, true) == Transport::ok);
    result = snapshot_dispatch(call, storage, fixture_callback, &probe);
    CHECK(result.transport == Transport::ok && result.protocol_status == SGPU_BAD_REPLY);
    finish(session, result.protocol_status);
    CHECK(session.phase == Phase::faulted && session.provider_hold);
    CHECK(begin(session, original_task, call, true) == Transport::not_open);
    CHECK(!release_session_hold(session, Quiescence::unknown));

    Session racing = {};
    CHECK(admit(racing, original_task, true, true) == Transport::ok);
    CHECK(begin(racing, original_task, call, true) == Transport::ok);
    close(racing);
    CHECK(racing.active_calls == 1 && racing.provider_hold);
    CHECK(!release_session_hold(racing, Quiescence::provider_proven));
    finish(racing, SGPU_BACKEND_ERROR);
    CHECK(racing.phase == Phase::closed && racing.active_calls == 0 && racing.provider_hold);
    CHECK(!release_session_hold(racing, Quiescence::unknown));
    CHECK(begin(racing, original_task, call, true) == Transport::not_open);
    CHECK(release_session_hold(racing, Quiescence::provider_proven));
    CHECK(!release_session_hold(racing, Quiescence::provider_proven));
    std::printf("PASS %u host-only ingress/snapshot/lifecycle checks; no GPU or XNU runtime\n", checks);
    return 0;
}
