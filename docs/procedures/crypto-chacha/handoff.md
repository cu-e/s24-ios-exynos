# KRN-034 work in progress

Owner: codex-team-crypto-chacha-20261105-bu. Branch team/krn-034-20261105.
The genuine explicit-nonce streaming subset is being implemented and tested.
No provider registration, kernel relink, phone operation or all-ten-method
qualification is claimed. QEMU requires a separate exclusive root lease.

Selected API: XNU c54f35ca767986246321eb901baf8f5ff7923f6a,
EXTERNAL_HEADERS/corecrypto/ccchacha20poly1305.h and genuine register_crypto.h.
Nine real methods use permissively licensed Mbed ChaCha20/Poly1305 primitives
and independently authored RFC8439 AEAD glue in self-contained owned storage.
Import accepted XTS mbedtls_platform_zeroize and unchanged CPU runtime only.
Actual core storage fit now measured256 bytes/alignment8 against genuine
selected256/alignment8; primitive sizes136+80 and actual native table80/alignment8.
Supported streaming runtime tests remain in progress.

The all-ten acceptance gate is explicit. Selected headers/forwarders declare
incnonce but do not specify encoding; actual ESP callers set explicit nonces.
Official current Apple corecrypto9612a959abb6eac0aac3ee6a7245c46365c9d81b,
blob96e59142ea805fc98b297b83dbd9c20dd502486e, line946, contains a guard macro and only explicit return1; guard semantics are
unclaimed and there are no direct nonce/context references. That unrelated current failure does not define a
selected16.5 increment rule. Only limited API availability facts were recorded;
no restricted implementation body is saved, compiled, copied or translated.
Independent KRN-037 source audit owns further historical primary investigation.
The experimental table's incnonce fails closed without mutation; this does not
satisfy the all-ten acceptance criterion. Overall evidence must stay inconclusive
unless applicable increment semantics are genuinely qualified.

Current artifacts: artifacts/crypto-chacha/source-session1 contains vendor
acquisition, exact limited primary facts and failed public-source leads. Root
resource policy requires MemAvailable>=4GiB before every run, one compiler
<=256MiB, aggregate<=2GiB; no shared workload/cache/swap manipulation. Source
preparation continued during the root memory pause; no compilers ran then.

Supported stage completed:59 RFC/OpenSSL vectors,123999 sanitized host checks;
real ASanheap/UBSanoverflow detector negatives and3 forbidden-profile rejections.
Actual typed ARM methods compile with ten exact relocations and one imported
zeroizer, storage256/8 and table80/8. Normal/spin images linked.
Evidence: worktrees/krn-034-20261105/artifacts/crypto-chacha/host-arm-session5/evidence.json.
Overall inconclusive; this does not meet all-ten acceptance. Failed sessions1/2
were resource-deferred before children, session3 host passed then orchestration
shadowing error, session4 native link caught immutable runtime entry requirement.
Session5 resolves those checks; no algorithm correctness defect found.

Independent KRN037 commit34b9637 confirms8 contract fields unknown. Its manifest
is linked/hash-pinned in nonce-contract.json. Do not infer a nonce rule from
GCM, RFC explicit nonces, current guard/return1 or nonauthoritative mirrors.

CHACHA003 canonical planned entry exists created2026-11-05T18:21:47Z. No guest
lease yet. Coordinator authorized CPU-runner-only admission:3 consecutive
>=4GiB samples1s apart,45s/command,180s total wait budget; resource-deferred
means no child starts below floor. Actual waits/samples are retained. Compiled
inputs remain byte-identical to session5; only the uncompiled CPU runner delta
is separately hashed/snapshotted rather than falsely called a compiler change.
Request fresh finite exclusive256MiB QEMU lease, then execute already built
images with positive/wrong-cookie/corrupted-vector/3s spin cases. Do not rerun
passed host/ARM compilation to handle resource admission.

CHACHA004 ran under an explicit finite lease, then immediately released after
the positive case failed (no other cases started). Handoff verified; instruction
abort ELR0xfffffff007003b3c equals actual linked_s24_chacha_info; LRphysical
0x43005b94 is the first suite indirect call. QEMU exit0 was shutdown, not a
vector pass. Immutable CPU report/console retained under cpu-session1; honest
cpu-failure-envelope1 recorded through MAIN (initial direct record was rejected
for missing summary, preserving that failure too). Address diagnosis is under
table-address-diagnosis1. Shared runtime/MMU and phone remain untouched.

Approved fix adds exact typed volatile runtime stores using the owned accepted
XTS pattern and a shared ten-binding macro. Native static table relocation
proof remains separate. CHACHA_CPU_FIXTURE prepares its bounded single-thread
table before the completely unchanged suite; no production mutable provider
singleton. Core/primitives/profile/corpus AND suite.c remain byte-identical to
the123999-check host pass. selective bindings.py verifies this chain, reuses
those exact objects and recompiles only native/runtime bindings+guest. Actual
assembly must prove ten PC-relative callback addresses and ten volatile stores.
CHACHA005 is genuinely planned; first selective run deferred before any child
due host MemAvailable below4GiB. Resume when floor permits, commit the fix, then
request a fresh finite CPU lease/new prospective experiment. No guest is active.

Selective requalification now PASS in bindings-session3/evidence.json: native
constant ten relocations remain exact80/8; actual linked A64 instructions in
BOTH prepare/fill produce ten direct callback addresses at the correct fields.
Compiler initially emitted GOTPAGE; proof did not assume relaxation. Real final
bytes resolve direct addresses, including physical load-bias projection. Own
linked STR-field mutation is rejected by the address proof. New symbols come
from independent llvm-nm. Crypto/primitives/profile/corpus/suite bytes remain
exactly unchanged and reuse59vector/123999sanitized host proof. No guest has
executed the corrected binding yet. Plan fresh CHACHA006(timeout300), commit,
then wait explicit finite exclusive QEMU lease. Existing unused003 unchanged.
