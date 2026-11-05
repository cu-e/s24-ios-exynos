# eUICC session and LPA boundary

ESIM-001, owner `codex-team-esim-20261105-ak`. This is host qualification of a
project-owned C11 component using a **synthetic peer**. There is no physical
transport or service selected by default. No phone, profile, slot, account or
carrier service is accessed by this procedure.

## Capability boundaries

| Capability | Established here | Remaining gate |
| --- | --- | --- |
| Use an already active profile | No | Native CP/SIM/network qualification: ESIM-002 and CELL-003 |
| Logical-channel APDU exchange | Bounded injected session interface and host tests | Exact Samsung backend, slot/privilege/channel/CLA/reset and timeout semantics |
| Download/enable/disable/delete profile | No | LPA, HTTP/SM-DP+ trust, authorized test subscription and selected iOS16.5 frontend: ESIM-003/004 |

An APDU primitive can carry arbitrary command bytes once a backend is provided.
It is **not an authorization filter** for provisioning. No Samsung AT/ARI command,
activation, functional iOS frontend or successful provisioning is invented here.

## Source pins and reuse

`src/platform/esim/provenance.json` records immutable revisions and reviewed file
hashes. The checker verifies the actual reference checkout revision, tracked-file
cleanliness and every reviewed file before compiling anything.

- [lpac interface](https://github.com/estkme-group/lpac/blob/a43e46aef6f8b5b1d144bf3b3fc5999d8fcefacc/euicc/interface.h),
  revision `a43e46aef6f8b5b1d144bf3b3fc5999d8fcefacc`, separates APDU
  connect/channel/transmit from HTTP. Its
  [stdio backend](https://github.com/estkme-group/lpac/blob/a43e46aef6f8b5b1d144bf3b3fc5999d8fcefacc/docs/backends/stdio.md)
  is a possible process boundary. Android Radio HIDL 1.0 in its gbinder backend
  does not establish an available S24 or native XNU transport.
- [Qualcomm donor](https://github.com/UniXNU/QcomBaseband/blob/dd0199cf3300764ed52b23f4a47761f91fab21a2/baseband/coachz_bb_esim.h),
  revision `dd0199cf3300764ed52b23f4a47761f91fab21a2`, supplies session/cleanup
  design evidence for Qualcomm and iOS17. Its slot/transport operations do not
  establish Samsung compatibility or the selected iOS16.5 private frontend.

No implementation code was copied. lpac has different licensing boundaries:
its euicc library is LGPL-2.1-only or commercial, drivers/CLI/tests are AGPL-3.0,
and documentation is MIT. The Qualcomm donor is BSD-2-Clause. Preserve the
applicable file license and attribution before later reuse.

## API and ownership

`session.h` exposes synchronous, allocation-free connect/open/exchange/close/
disconnect callbacks. The owner initializes one session with explicit nonzero
limits, begins with an AID, exchanges framed commands, then ends. There is no
implicit backend, default AID, CLA rewrite, retry, GET RESPONSE, reconnect,
profile download or slot change. Handles 1..255 are opaque local handles matching
lpac's uint8 close width; this does not assert a physical channel count.

Command parsing accepts complete short and extended ISO-style APDU shapes,
including zero Le meaning 256 or 65536. Limits are 65,544 command bytes, 65,538
response bytes including SW1/SW2, at most 4,096 exchanges and local AID policy
1..16 bytes; callers may choose lower bounds. A prefix of length 4, 5 or 7 can
itself be another valid APDU. The API needs complete caller framing and cannot
detect a truncated stream that is also a valid shorter command. It does not
validate command-specific eUICC semantics. Failed parsing clears metadata.

A card status such as 6985 is returned as a successful transport exchange with
its status word; it is not translated into fake provisioning success. Failed
exchange or cancellation clears reply metadata. Caller response storage may
contain partial backend bytes and must only be consumed after ESIM_OK.

Only `esim_request_cancel()` may run from another thread. C11 `_Atomic(unsigned)`
uses actual GCC/Clang acquire/release intrinsics without Android libc headers.
All other calls, state inspection and callbacks belong to one owner thread.
Initialization, session lifetime, transport context and caller buffers must stay
stable until requesters have joined and callbacks returned. Never reinitialize
an active or poisoned session: that would discard ownership. Reentrant owner
calls during a callback return BUSY.

Callbacks must have their own bounded timeout and transport quiescence. This
wrapper bounds bytes, exchanges and cleanup attempts; it cannot preempt a blocked
callback or recover a disconnected modem. Cancellation is observed before work
and after each callback; idle cancellation is serviced by `esim_service_cancel()`.
A late reply is rejected after cancellation. Cancellation closes the session;
there is no automatic reopen or user-visible recovery claim.

Cleanup closes an acquired valid channel and disconnects acquired transport at
most once, in that order. Even a failed connect disconnects partial resources.
A failed open must return -1 only when it guarantees no acquired channel; valid
partial handles are closed. An invalid successful or ambiguous failed open handle
poisons ownership. Cleanup failure likewise leaves sticky POISONED, retaining
primary backend error and separate cleanup status. Repeated end never retries
uncertain cleanup; external reconciliation is required before new initialization.
Backend callbacks must respect response capacity: a C interface cannot contain
a malicious or memory-corrupting backend.

## Host procedure and evidence

Register each experiment in the **main** ledger before execution, with this
procedure and a fresh run name. From this worktree:

```sh
python3 src/platform/esim/check.py --run FRESH_NAME --lab-root /home/egor/dev/pet/s24-ios-exynos
```

The checker performs sequential small builds (no heavy build lease required):

1. Exact primary checkout/reviewed-file pin verification.
2. GCC strict warnings and 11 actual parser/session scenarios.
3. NDK28 Clang UBSan trap execution, plus deliberately overflowing signed integer
   binary with inspected `llvm.ubsantrap` IR and actual SIGILL.
4. Existing `/home/egor/.local/bin/clang` (NDK27) native Linux ASan+UBSan execution
   with leak detection; a separate intentional heap overflow must terminate with
   an actual AddressSanitizer heap-buffer-overflow report. Native archives and
   compiler bytes are hashed; Android runtimes are not substituted into glibc.
5. Actual freestanding ARM64 ELF and iOS16.5-targeted Mach-O module/probe objects.
   Independent ELF section dump and bounded Mach-O reader compare layout values.
   These are compile/data-layout controls, not a kernel link or device execution.

The 11 scenario groups cover complete APDU forms, all short Lc lengths, maximum
extended command, invalid sizes and guard pages, normal/card-error responses,
validation without I/O, partial connect/open failures, invalid handle poisoning,
transport/disconnect errors, short/oversized replies, exchange budget, close and
disconnect failures, cancellation before/during callbacks, a real concurrent
atomic cancellation requester, reentrancy and effective-capacity clamping.
The synthetic peer reports oversized lengths without writing out of bounds;
response canaries and actual PROT_NONE pages test the wrapper's read boundaries.

Every run retains exact commands, stdout/stderr, exits, timeout flags, tool/source/
artifact hashes, date and Git commit in `artifacts/esim-001/RUN`. Test-only negative
binaries are never linked into the transport module. All hardware, active-profile,
provisioning, native-device and iOS frontend qualification flags remain false.
Failures are retained; ESIMHOST-001 records broken GCC shared sanitizer references,
ESIMHOST-002 absent NDK28 native ASan archives, ESIMHOST-003 Android stdatomic header
dependency, and ESIMHOST-004 a target signed-comparison warning after actual native
sanitizer success. No system libraries were repaired or packages installed.

The coordinator reviews/integrates the owned commit and runs the main `make check`.
Keep ESIM-001 in progress until that review; host success does not complete the
physical transport, profile-use, provisioning or selected frontend gates.
