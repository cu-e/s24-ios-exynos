# SGPU transport proposal 1.0

This project-owned experimental protocol makes the [GPU-006 operation contract](../../../graphics/contracts/README.md) concrete as bounded request/reply bytes. `sgpu_abi.c` is a reusable freestanding C validator/dispatcher; `sgpu_fake.c` is a separate **host-only synthetic peer**. Neither is a Linux SGPU driver, Apple IOUserClient implementation, RADV winsys or GPU emulator. There is no device I/O.

## Wire format and limits

All wire integers are unsigned little endian, with explicit reserved fields and no pointers, native `size_t`, C enums, kernel addresses or C flexible-array layouts. `sgpu_abi.h` declares fixed layouts and compile-time size/offset assertions; the decoder reads individual bytes, including unaligned input. It never casts caller bytes to a structure. Numeric handles are opaque references, not addresses; a syntactically valid handle still requires authenticated backend lookup.

Both headers are 32 bytes. Request offsets are magic `u32` at 0 (bytes `SGX1`), major/minor `u16` at 4/6, opcode `u32` at 8, total message bytes `u32` at 12, correlation ID `u64` at 16, flags/reserved `u32` at 24/28. Flags/reserved must be zero and ID nonzero. Replies use status at 24 and zero reserved at 28; version and total length are explicit. The ID is correlation data, not client identity, replay protection or an idempotency guarantee. Do not automatically retry a submit/allocation after a lost reply.

The bootstrap header is version 1.0. QUERY additionally supplies an inclusive major/minor range and required-feature mask; no common version is an error, and mandatory features cannot silently disappear. Current messages require exact 1.0 headers. Unknown opcodes, extra bytes, mismatched sizes, flags and reserved fields fail before backend invocation. Future extensions need explicit negotiation/versioning; no selector or wire compatibility with Apple/Linux is implied.

| Item | Current experimental protocol ceiling |
|---|---|
| Request or caller-provided output capacity | 4096 bytes; output capacity at least 120 before any callback |
| Submit array counts | 8 IBs, 64 unique BO uses, 32 unique fence dependencies |
| Each IB / allocation | 64 KiB of commands / 128 MiB logical BO |
| GPU map offset, address and size | 4 KiB alignment, nonempty, checked overflow |
| Wait | 0 through 100,000,000 ns; this validator does not sleep |

These are initial host/protocol policies, not measured firmware limits. A real backend must also enforce its negotiated lower limits, per-client/device budgets, exact VA window, BO length, actual CPU page alignment, rights and current epoch. The validator alone does not establish that any resource exists. The GPU-006 oracle separately exercises 4/16 KiB allocation ownership; it is not called by this C peer.

## Core messages

Payload layouts are defined in the header. Sizes below exclude the 32-byte envelope. All unspecified/reserved values are zero.

| Opcode | Request payload bytes and purpose | Successful reply payload |
|---|---|---|
| QUERY (1) | 16: version range and required features | 88-byte capabilities, epoch, budget/VA/page profile and protocol limits |
| ALLOC (2) | 24: size, power-of-two alignment, R/W/X access | 16: opaque BO handle and charged backing bytes |
| FREE (3) | 8: BO handle | Empty |
| CONTEXT_CREATE (4) | 16: graphics=0/compute=1 class; priority=0 | 16: opaque context and epoch |
| CONTEXT_DESTROY (5) | 8: context handle | Empty |
| CPU_MAP (6) | 32: BO, offset, size, CPU R/W access | 16: connection-local map token and mapped size |
| CPU_UNMAP (7) | 8: map token | Empty |
| GPU_MAP (8) | 48: context, BO, VA, offset, size, access | Empty |
| GPU_UNMAP (9) | 24: context, VA, size | Empty |
| CACHE (10) | 32: BO range and CPU→GPU=1/GPU→CPU=2 direction | Empty |
| SUBMIT (11) | 24-byte context/count header; canonical IB/use/dependency arrays | 16: opaque fence handle and sequence |
| WAIT (12) | 16: fence and finite timeout | 8: retired=1/retired-with-error=2 and reason |
| STOP (13) | Empty | Empty |

Map tokens must be resolved through a future authenticated IOKit mapping path, not converted directly into an address. Access flags are requested rights, not proof a given chip/OS supports every combination. Native policy must validate executable memory and sharing before granting rights. Context class is a logical request, not a guessed hardware ring number.

SUBMIT arrays follow immediately in order: 32 bytes per IB, 16 per BO use, 8 per dependency. Bounded counts are checked before size arithmetic, then exact total length, reserved fields, nonempty aligned IB ranges, duplicate BO uses/dependencies and an explicit READ use for every IB BO. There are no caller-provided table offsets or aliases. Handle ownership, bounds against the actual BO, command syntax, dependency cycles and write hazards remain native-backend checks. Do not let userspace mutate an executable IB after validation: the backend needs a stable submission snapshot or equivalent enforced ownership.

All errors are header-only. TIMEOUT does not retire a fence. WAIT success is reserved for trusted backend retirement evidence; pending success is rejected. Object replies require nonzero handles and size/epoch/sequence; allocation/map sizes cannot understate the requested size. Error text, pointers and arbitrary backend buffers are not serialized. Callback replies are bounded and checked for size/status/reserved fields, query limits/profile shape and required-feature compliance. Malformed replies become BAD_REPLY with no payload. Query shape checks cannot prove that a backend's hardware claims are true; native qualification evidence is still required.

There are deliberately no client operations for completion injection, raw register reads, reset, physical memory access or quiescence assertions. IOSurface export/import, scanout release and presentation need a later reviewed extension; their absence remains an explicit gap in GPU-009/010, not a claimed feature of this transport.

## Host peer and trusted C boundary

The fake peer supports QUERY and idempotent STOP only. It sets `SGPU_FEATURE_SYNTHETIC`, advertises protocol-validation limits and leaves native profile, page sizes, epoch, physical VA and budgets **zero/unknown**. Other well-formed requests return UNSUPPORTED, or STOPPED after Stop. It allocates no BO, runs no job, manufactures no completed fence and performs no reset. An unknown operation never reaches the callback.

`sgpu_dispatch` expects valid, non-overlapping trusted storage: one immutable kernel-owned input snapshot, separate output storage and a separate `reply_bytes` object. They must remain valid for the entire call. The C function is not `copyin`, a capability boundary or a pointer-validity checker. Callbacks borrow the validated view only during the call and must not retain its pointer. A native adapter must resolve ownership and prepare work atomically before enqueueing; parsing success is insufficient.

The dispatcher clears output capacity before encoding a reply and rejects insufficient capacity or input/output overlap before invoking a backend. It cannot cancel a blocking callback or undo a callback's side effects after BAD_REPLY. A native callback must implement bounded waits, stable resources and recovery/error handling itself. Output failure never authorizes freeing in-flight backing. No thread safety, process teardown, request replay or actual watchdog is delivered here.

## XNU integration still required

At pinned [XNU IOUserClient.h](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/iokit/IOKit/IOUserClient.h), external-method arguments have separate scalar/structured input counts, output sizes and optional memory descriptors; dispatch size checks do not validate an embedded protocol. GPU-007 must implement a real authenticated IOUserClient, review selector/async/scalar/descriptor handling, copy a bounded immutable message and call this validator. A variable-size selector alone is insufficient. No actual selector/class is registered by this code. These source observations are not an SDK compile or IOConnect runtime test.

The C return value is a protocol status, not an IOReturn. The adapter must define outer transport errors separately and publish the exact structured-output byte count; directly casting this function's return value to an IOKit result is not an integration.

The core and layout assertions compile without an SDK because they include only compiler-provided integer/size types in freestanding mode. An arm64 Mach-O object with an iOS16.5 target is **not** an XNU driver build: it links no kernel interfaces, runs no constructors or userland, and establishes neither the kernel nor selected iOS ABI. [Clang's cross-compilation guide](https://clang.llvm.org/docs/CrossCompilation.html) explains why target selection and a complete target toolchain/sysroot are different requirements.

## Reproduction and retained results

```sh
python3 src/platform/gpu/abi/check.py --run unique-transport-run
python3 -m unittest discover -s tests -p test_gpu_abi.py -v
```

The [procedure/results handoff](../../../../docs/procedures/gpu-011/README.md) preserves two initial failures and corrected runs. Seven Python scenario groups execute the compiled host shared library, including all 13 core request shapes, every truncated prefix, extra bytes, bad versions/features, count/offset overflow, aliases, reserved fields, duplicate references and Stop. The C sanitizer harness adds 14 malformed backend replies, five valid/timeout reply controls and 50,000 deterministic mutation/control attempts on submit packets, including unchanged valid controls. Array counts, marker IDs and GPU VAs in these tests are owned synthetic values, never hardware measurements. Compile-only ELF/Mach-O objects are never executed on ARM.
