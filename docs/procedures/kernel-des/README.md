# Selected native DES/TDES integration

KRN-039 adds eight immutable selected ECB/CBC descriptors and two exact8-byte
helpers over the accepted Mbed TLS software DES bridge. The selected public key
policy is DES8/TDES24 bytes; backend-local16-byte EDE2 remains unpublished.
Private schedules are144/400 bytes, alignment16, within genuine caller256/768
capacities. Descriptors48/40 bytes and allocator alignment16 are measured against
actual selected declarations and private factory output before publication.

The helper publishes once with acquire/release ordering. Getters returnNULL before
ready; init requires exact public descriptor identity. Preparing/repeated/failed
states are explicit; failed preparation is sticky. No context overlay, callback
cast, allocation, entropy, empty schedule or provider registration is introduced.
RoundkeyNULL and CC_IMPL_UNKNOWN are retained. Caller owns buffers, stable
contexts and serialization; clearing/reusing schedules follows accepted DES rules.

Fresh copies of the accepted XTS provider and pinned XNU caller sources preserve
original34+XTS2 static callbacks and deferred SHA256. Actual object decoding gives
46 static relocations and9 unsupported slots. A988-object manifest replaces only
provider/coreDES/ESP and adds publication/DES/primitive objects.37 private exports,
native flags/features, source pins, original dependencies and runtime stay unchanged.
There is no full kernel link or full mc_provider startup execution.

The selected corecrypto_des wrappers already return init/ECB errors. Active ESP
CBC walkers use those ECB callbacks, not shared CBC schedules; they previously
ignored errors. Scoped ESP guards return EINVAL before publishing destination
chains, consume both still-disjoint chains exactly once, and reach common cleanup.
Scratch allocation failure also consumes the original packet, matching real outer
caller ownership. Six populated-IV validation exits join cleanup. Initial
unsupported-IV and conditional DIAGNOSTIC block-length exits precede IV population
and remain direct returns. Successful packet/ciphertext/IV-stir behavior requires
comparison against the original actual caller.

Unobserved production codegen exposed bzero elision on scratch-NULL IV cleanup.
The patch uses genuine cc_clear(length,pointer). Actual unobserved ESP object calls
it on IV-only and IV+scratch paths; unchanged strong selected providers are
cc_clear -> memset_s -> secure_memset. Runtime observers separately check bytes and
ownership; they do not prove optimizer behavior. Original failing objects/reports
remain in artifacts/kernel-des, along with compilation/resource failures.

The owned CPU fixture uses genuine selected mbuf/secasvar/algorithm records and
actual DES/ESP caller code. Its packet pool supports only<=40-byte packets and
8-byte output buffers. It exercises contiguous, fragmented and unaligned inputs,
head/prefix/tail aliases, schedule faults at each block, allocation failures and
malformed metadata paths. Logging, clusters and unsupported services fail-stop;
logging redirection exists only in the instrumented fixture. A deterministic
fixture IV-update service counts success calls and makes no entropy claim.
The original-caller image retains original status/ownership behavior and serves
as an actual negative after proving12 successful packet cases.

The synthetic table has only these ten slots. Full real native provider/table
proof is separate. The unchanged qualified AVF helper retains its legacy
xts_entry symbol/cookie, although the entry runs this DES fixture. High mapping,
callback references, accepted shim/QEMU and every image are bound by hashes.
A fresh explicit coordinator lease is mandatory before execute_caller.py.

Evidence workflow: xnu_kernel_des.py compiles actual native inputs; --reuse-native
rebinds unchanged witnesses and recompiles only ESP. verify_native.py checks strict
typing, const descriptors, source/graph closure and unobserved codegen. The retained
native-controls4 failure concerns a missing fixture header only;
finish_publication.py completes just that fixture and preserves all earlier
measurements. prepare_caller.py prepares images without QEMU; --reuse-esp rebinds
identical ESP/fortify objects. execute_caller.py is the finite guest supervisor.
Experiment.md contains the prospective resource/ownership plan.

The current source candidate is awaiting actual CPU controls and independent
REV022 acceptance. Inactive NFS/GSS/CTS integration, optional/general mode APIs,
full crypto, side channels, FIPS, private Apple ABI, XNU MMU/board and native device
compatibility remain unqualified. No phone operation is part of this work.
