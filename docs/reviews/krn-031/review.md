# REV-017 independent KRN-031 review

Recommendation: accept the bounded KRN-031 provider/caller component integration.
No blocking production finding remains. The independent final audit passes
6198 checks across 4545 bound inputs and 30 actual pinned Git commands. REV-017
remains in progress for coordinator acceptance. Development passes were not used
to replace the final qualification.

Frozen implementation: `1bd64b4265cccf866bd1a3e1e1bcb3dde66d2877`.
Named followups reviewed:

- `b87957bfd89d8ab82162e546d9c9eee3c018078f` changes exactly two builder
  expressions to avoid requiring mapped caller/table/TTBR symbols from the
  intentionally pre-mapping spin image. Production glue and fixtures are unchanged.
- `e3b6b7da1217a716b0a2b152207b61ab73c749cf` promotes the actual selected
  compiler's separate strict function-pointer diagnostic and permits guest image
  lookup through a retained component manifest. It adds a targeted qualification
  procedure. Production glue, caller/provider patches and fixture bytes are unchanged.
- `0551ab0279adbc7e1f0bae3e698f4857865c4888` binds the complete measured
  publication, mismatch and caller check counts to acceptance.
- `376a2f3f639d88ab954d9807220854779e995dc8` adds bounded stable memory
  admission without lowering the 4GiB floor. Each launch requires three passing
  samples and an immediate passing sample, with 45s per-command and 180s total
  wait budgets. Only test/build qualification code changes.
- `9dc0c9f92c26373263ed17439eb44d0f2ea2268d` binds the observed shifted-mapping
  exception to the real pinned shim shutdown path, strengthens specific negative
  case counts/lines and permits only explicitly named continuation cases. A 300s
  whole-batch deadline includes memory admission and child-cleanup margin.
  Source/fixture/production patches are unchanged.
- `a84ac4ec571fd36b1d435036d453fa68982d88b3` adds only final documentation,
  capsule and source/license metadata. Final-binding.json independently binds its
  capsule SHA256 `b5f772163a286e2586d1a76f38640ca8e3b75d38a681d3b1b09198e91e6e2a47`,
  all five report identities, exact 985-object coherent manifest, runtime/export
  gates and primary source/license hashes to the independent audit.

The selected compiler emitted the wrong-return signature diagnostic as
`-Wincompatible-function-pointer-types-strict`, with exit 0, despite the original
`-Werror=incompatible-function-pointer-types`. This was a verification-policy
defect; frozen-native2 is correctly preserved as failed. The targeted correction
must demonstrate both an actual wrong-signature error and an unchanged real
helper positive under the strengthened policy, with source/command/object bindings.
Strict-native3 now establishes both through exactly two selected compiler commands:
wrong-return callback exit 1 with the actual strict type error, genuine unchanged
helper exit 0 under the same strengthened policy. All earlier passed native/image/
host measurements are individually rehashed and retained; the failed aggregate
record is not rewritten or relabeled. The independent native audit passes 6016
checks and binds 4500 inputs, including the actual graph/dependencies/recipes,
relocations, instructions, layouts, imports, runtime and export inputs.

The helper's public descriptors are const objects with static lifetime. Their
callbacks forward to private genuine accepted factories, which never escape.
Release publication of state 2 follows both factory calls and metadata validation.
All accessors/callbacks acquire-check readiness before reading private descriptors.
The atomic compare/exchange makes ready preparation idempotent, preparing
contenders fail, and factory/metadata failure sticky. The supported startup is
the actual serialized EARLY_BOOT boundary; this does not promise a waiting API
for arbitrary concurrent preparation.

Metadata checks cover key/tweak storage sizes, AES block size, all four callback
pointers, null customization fields and the selected implementation tag. Init
and legacy key scheduling enforce public descriptor identity. Rejected init/schedule
clear admitted key storage; unavailable tweak/block operations fail. Admitted
storage, alignment, lifetime and caller serialization remain the accepted adapter's
contracts. Const C declarations do not establish hardware page write protection.

The provider patch adds only the two XTS references and preparation/getter checks
before the existing deferred SHA256 assignment and registration. The review must
confirm actual native 448-byte table bytes, all 34 original relocated targets,
exactly two new references at 144/152, one deferred SHA256 field at 48, 19 zero
unsupported fields and actual native BL order. Existing feature/header/export
profiles, runtime archive and unrelated graph identities must remain bound.

Both actual selected caller block operations now translate a null callback result
to `CCERR_PARAMETER`. Original set_tweak propagation and non-block-size panic
remain. The wrapper retains its original ignored tweaklen/options/IV behavior;
this change does not qualify broader caller policy or ciphertext stealing.

The independent auditor reads pinned Git objects with lazy fetch and optional
locks disabled, rehashes accepted inputs and uses its own Mach-O reader for
symbols, relocations, instructions, metadata and linked callback addresses. It
does not import the producer's parser/builder or execute a compiler/guest. Its
failed-capsule admission control rejects frozen-native2 before any acceptance.

The final guest evidence comprises the immutable three-case prefix in
final-guest1, mapping-reinspection1 and the five-case final-pending-guest1
continuation. The original prefix aggregate remains failed because its old
classifier wrongly required a timeout for bad mapping. Each accepted prefix case
is rehashed and qualified individually; no successful case is rerun or relabeled
without its original outcome. Both batches bind the same strict-native3 component
capsule and exact genuine fixture/accepted inputs. The continuation is cleanly
bound to 9dc0c9f and names exactly the five remaining controls.

| Case | Independently verified result |
| --- | --- |
| Positive | 1220 vectors / 7350 checks; actual mapped caller and registration, natural PSCI exit 0 |
| Wrong cookie | Admission rejection before mapped caller execution, exit 0 |
| Bad mapping | Exact linked entry redirected outside loaded image; pinned shim exception and natural exit 0 |
| Corrupt expected ciphertext | Exactly one payload byte differs; real caller fails at check 18 / source line 44 |
| Original unpatched caller | Genuine original object fails at check 7338 / source line 53, demonstrating lost error propagation |
| Factory size mismatch | Real size-only factory variant rejected; 0 vectors / 11 checks |
| Non-block size | Original genuine caller panic reaches stopping runtime |
| Spin | No mapped caller execution; bounded 3s timeout and owned-process cleanup |

The bad-mapping image uses L2 first index 33 rather than 32. Independent Mach-O
decoding maps linked entry `0xfffffff007004d38` normally to `0x43004d38`, but the
shift targets `0x42e04d38`, outside every loaded segment. The raw console records
slot 4, ESR `0x02000000`, the exact linked ELR and FAR 0. The independently read,
shim-build-bound avfboot_exception source calls die, whose path invokes
PSCI_SYSTEM_OFF. This is a precise natural-shutdown negative, not a timeout or
mapped-caller pass. A generic crash/exit marker would not satisfy these checks.

The reviewer verifies exact XNUP contents against each original Mach-O, including
the cookie and sole corrupted-vector byte; actual console addresses against
linked descriptors/callbacks/TTBR roots; actual TCR; exact negative source lines;
all guest admission records, process bounds and cleanup. Every command leaves no
owned process. No compiler or QEMU was launched by the reviewer.

Reviewer tooling failures are retained: the initial frozen-reference admission
correctly rejected a newly unreviewed followup, and the first branch scan counted
later functions in the same section. Explicitly reviewing the followups and
bounding the initializer by the next function corrected those reader checks.
These failures do not establish a production defect.

The last binding reader initially compared the nested export entries to the
manifest's complete path/hash/entries record; that schema mismatch is retained.
The corrected check compares the complete preserved record and passes.
Coordinator common checks are scheduled after implementation/review integration;
the reviewer has not run make check, which invokes compilers.

Native compilation/relocation proof concerns the full real selected provider
object. ARM CPU execution concerns an owned two-slot table plus genuine selected
caller and register_crypto_functions, real accepted XTS/AES and synthetic runtime.
It does not execute full mc_provider startup, PRNG/digests, XNU MMU/startup or an
Exynos board. No full crypto/private Apple/FIPS/side-channel/encrypted-volume/native
device claim is made. The 19 unsupported fields and 37 missing native export
implementations remain explicit gates; no full kernel build/link is performed.
