# KRN-034 supported-subset handoff

Owner codex-team-crypto-chacha-20261105-bu, branch team/krn-034-20261105.
Implementation commits 9133fedcd5f18a01973facca98384fa182d0e259 and
7f45596efa2ad27a3b64c771d7602aae10bc6bda; final documentation commit follows.
Scope only src/platform/crypto/chacha and docs/procedures/crypto-chacha.
No phone/ADB/root/flash/MMIO-device/reboot, kernel relink or provider registration.

Supported explicit-nonce subset is ready for independent review/integration.
Do NOT complete KRN-034: applicable selected-version incnonce encoding/range/
order,overflow/error/mutation,allowed-state/state-after/success contract remains
unknown. Independent KRN-037 evidence is hash-pinned in nonce-contract.json.
The experimental ten-slot type includes an unsupported CCERR_NOT_SUPPORTED
incnonce without mutation. No guessed rule, successful stub, or all-ten claim.
After review the original owner may block the broad acceptance on this precise
external contract. Preserve the reservation; no takeover or false completion.

Measured selected/owned storage: 256 bytes, alignment 8, actual native table: 80 bytes, alignment 8.
Genuine licensed Mbed TLS ChaCha20+Poly1305 primitive pair at full pin 068ff080b369adfac81509f9b57b2afabaf82dc5
with independent RFC8439 AEAD glue; Full pin, license, file and Git blob hashes in
vendor/provenance.json. Shared accepted zeroizer imported exactly once; no heap,
foreign-state pointer, fake SDK records or function-pointer casts. Complete
check_config.h was verified from canonical fullarchive before the first compile;
the earlier truncated research input and correction remain in source-session1.
No restricted Apple implementation body is retained, copied or translated.
Current primary limited facts are guard macro+only explicit return1; guard
semantics unclaimed, not selected-version compatibility evidence.

Actual results:
- 2 untouched primary RFC8439 vectors plus 57 independent EVP vectors= 59.
- 123999 actual streaming/phase/reset/inplace/disjoint/tag/alias/overflow/clear
 host checks pass native ASan+UBSan. Real heap/signed-overflow negatives trigger;
 3 forbidden profiles fail compilation. Bad-tag plaintext remains unverified
 and is explicitly discarded by caller/fixture. Counter injections prove guards,
 not 256 GiB operation or nonce exhaustion.
- Actual genuine typed ARM methods/native 10-pointer relocations qualified. Native
 constant table's virtual addresses are distinct from MMUoff fixture startup.
 Shared ten-binding list fills a genuine table with volatile typed stores;
 actual linked A64 bytes in BOTH prepare/fill prove direct callback addresses
 and correct offsets, independent llvm-nm targets and physical load bias. A
 real linked STR-offset mutation is rejected. Mutable initialization is confined
 to single-thread CHACHA_CPU_FIXTURE startup; unchanged suite runs actual calls.
- CHACHA-006 under explicit finite coordinator lease: 123999 ARM checks, positive
 marker, wrong-cookie reject, corrupted expected vector FAIL/shutdown, deliberate
 3 s spin timeout and verified owned-child cleanup all pass. Lease RELEASED.
 Runtime/cookie/entry retain accepted XTS naming; unique CHACHA markers identify
 this suite. No Exynos model, XNU execution, native/FIPS/wholecrypto/side-channel
 or private context-field compatibility qualification.

MAIN-relative actual evidence:
worktrees/krn-034-20261105/artifacts/crypto-chacha/host-arm-session5/evidence.json
worktrees/krn-034-20261105/artifacts/crypto-chacha/bindings-session3/evidence.json
worktrees/krn-034-20261105/artifacts/crypto-chacha/cpu-session2/evidence.json
worktrees/krn-034-20261105/artifacts/crypto-chacha/tag-compare-review1/review.json

Reused unchanged crypto/core/profile/corpus AND suite sources/ARM objects retain
exact hashes to host-arm-session5; changed binding/guest inputs have their own
source snapshots/compiler commands. No passing crypto tests repeated for the
address fix. CPU execution at clean 7f45596 includes exact source bindings.
Reports remain overall inconclusive with supported-host/ARM/CPU pass fields.

Failures/protocol facts retained:
Initial independent corpus acquisition genuinely preceded corrected plan after
failed MAIN procedure-path submission; all adapter runs check canonical plans.
Layout host genuine SDK limitations led to portable core/real native table split,
without fake headers. Memory deferrals start no child below 4 GiB. Host orchestration
shadowing failure and native runtime-entry link failure retained. CPU-session1
verified handoff then instruction abort ELR 0xfffffff007003b3c matching actual
first callback info linked VA; process exit0 was shim shutdown, not vector pass.
Immutable cpu-failure-envelope1 records this honestly. Prelink GOT source was
not assumed safe: actual final instructions prove linker relaxation. CHACHA003
remains unused, not retrospectively changed. Plans/records 001/002/004/005/006
are through sole MAIN ledger under original owner.

Resource policy: one compiler <=256 MiB; guest exclusive 256 MiB, <=512 MiB owned RSS;
MemAvailable >=4 GiB. CPU uses 3 stable samples 1 s apart, 45 s per command, 180 s total wait
inside a 300 s finite lease, exact samples/cleanup retained. No foreign processes,
swap or cache touched. No further tests or guest lease needed now. Coordinator
reviews/integrates and runs MAIN common make check; isolated WT lacks private
inventory, so do not repeat known-inapplicable whole-repository checks here.

Next: independent review of bounded subset, integration/common checks, then
original owner records explicit external nonce blocker if acceptance remains
incomplete. All hardware/GPU/network/modem/Apple-native claims remain outside
this component outcome.
