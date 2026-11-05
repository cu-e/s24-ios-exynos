# REV-017 independent KRN-031 review

Status: source review has found no blocking defect. Final acceptance remains
pending the qualified final native/host/guest capsule. Development passes and
failed frozen replays do not satisfy the task.

Frozen implementation: `1bd64b4265cccf866bd1a3e1e1bcb3dde66d2877`.
Named followups reviewed:

- `b87957bfd89d8ab82162e546d9c9eee3c018078f` changes exactly two builder
  expressions to avoid requiring mapped caller/table/TTBR symbols from the
  intentionally pre-mapping spin image. Production glue and fixtures are unchanged.
- `e3b6b7da1217a716b0a2b152207b61ab73c749cf` promotes the actual selected
  compiler's separate strict function-pointer diagnostic and permits guest image
  lookup through a retained component manifest. It adds a targeted qualification
  procedure. Production glue, caller/provider patches and fixture bytes are unchanged.

The selected compiler emitted the wrong-return signature diagnostic as
`-Wincompatible-function-pointer-types-strict`, with exit 0, despite the original
`-Werror=incompatible-function-pointer-types`. This was a verification-policy
defect; frozen-native2 is correctly preserved as failed. The targeted correction
must demonstrate both an actual wrong-signature error and an unchanged real
helper positive under the strengthened policy, with source/command/object bindings.

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

Native compilation/relocation proof concerns the full real selected provider
object. ARM CPU execution concerns an owned two-slot table plus genuine selected
caller and register_crypto_functions, real accepted XTS/AES and synthetic runtime.
It does not execute full mc_provider startup, PRNG/digests, XNU MMU/startup or an
Exynos board. No full crypto/private Apple/FIPS/side-channel/encrypted-volume/native
device claim is made. The 19 unsupported fields and 37 missing native export
implementations remain explicit gates; no full kernel build/link is performed.
