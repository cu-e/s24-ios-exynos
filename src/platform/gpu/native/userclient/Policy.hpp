/* Project-owned ingress policy. No Apple type definitions or GPU emulation. */
#ifndef S24_GPU_USERCLIENT_POLICY_HPP
#define S24_GPU_USERCLIENT_POLICY_HPP

#include "../../abi/sgpu_abi.h"

namespace s24gpu {

enum class Transport { ok, bad_argument, unsupported, not_privileged, not_open, not_ready, busy, no_memory, io_error };
enum class Phase { unopened, open, closed, faulted };
enum class Quiescence { unknown, provider_proven };

struct Session {
    uintptr_t owner;
    Phase phase;
    unsigned active_calls;
    bool provider_hold;
    bool close_notified;
};

/* Facts supplied by the typed kernel adapter, never decoded from SGPU bytes. */
struct Shape {
    bool current_argument_version;
    uint32_t selector, argument_selector;
    uint32_t scalar_inputs, scalar_outputs, async_references;
    bool async_port, async_pointer, input_descriptor, output_descriptor;
    bool variable_output, reserved_nonzero;
    const void *input;
    size_t input_bytes;
    void *output;
    size_t output_capacity;
};

struct Storage {
    uint8_t input[SGPU_MAX_MESSAGE];
    uint8_t output[SGPU_MAX_MESSAGE];
    size_t reply_bytes;
};

struct Completion {
    Transport transport;
    uint32_t protocol_status;
    size_t bytes;
};

Transport admit(Session &, uintptr_t trusted_owner, bool authenticated, bool provider_ready);
Transport begin(Session &, uintptr_t trusted_caller, const Shape &, bool provider_ready);
void finish(Session &, uint32_t protocol_status);
void close(Session &);
bool release_session_hold(Session &, Quiescence);

/* Private kernel-owned storage and a provider-selected trusted callback only.
 * The IOUserClient selector never accepts callback/context pointers. The same
 * production snapshot implementation is exercised by separate host fixtures.
 */
Completion snapshot_dispatch(const Shape &, Storage &, sgpu_backend_fn trusted_provider_callback,
                             void *trusted_provider_context);

} // namespace s24gpu
#endif
