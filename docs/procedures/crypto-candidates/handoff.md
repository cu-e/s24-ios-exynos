# KRN-028 handoff

Owner `codex-team-crypto-candidates-20261105-be`, 2026-11-05.
Branch/worktree `team/krn-028-20261105` / `worktrees/krn-028-20261105`.
Own only tools/research/crypto-candidates, fixtures/public/crypto-candidates,
docs/procedures/crypto-candidates. No shared views or registry snapshots are
committed. Prior KRN-023 was completed under its original accepted owner.

Frozen implementation/source-audit commit
`37c74737cc760602e9c392dccd1d67da13c48db8`. CRYCAND-002 was planned before the final
commit-bound verifier. `python3 tools/research/crypto-candidates/verify.py
--run final-candidates-session1` exited0; all356 controls, including57 negatives, pass.
The timestamps, immutable evidence path/digest and
actual tested commit are in fixtures/public/crypto-candidates/qualified-audit.json.

Two genuine primary candidates: Mbed TLS3.6.7
`068ff080b369adfac81509f9b57b2afabaf82dc5` with reviewed Apache-2.0 OR
GPL-2.0-or-later notices (proposed Apache choice); official BearSSL
`7bea48e5e850ab4cafbe68d3765cdaba13a86d6f` with MIT/per-file notices.
67 named files and44 actual API declarations/algorithm bodies are bound.
All21 selected missing callbacks have candidate assessments, exact selected
declarations/typedefs, actual demand references and explicit ownership/API gaps.
No restricted Apple implementation or provider code is maintained here.

One and only one tiny genuine selected-header compile exited0, peak child
RSS130620KiB. Actual selected fixed storage: XTS1072 bytes per direction,
16-byte mode alignment; ChaCha256 bytes/alignment8; RSA1584/alignment8,
maximum4096 bits. No candidate context was compiled or proven to fit.
The final source verifier reuses that immutable measured object and dependency
hashes, with no additional compiler call. Verifier child peak is about26MiB.

KRN-029 should follow bridge-plan.md: use real Mbed AES block primitives and
properly attributed XTS/GF128 mode glue. Exact selected init/key_sched/set_tweak/
xts signatures, per-separate-key lengths, always-encrypt tweak key, raw16-byte
IV, split-call tweak progression and pointer return are described. Whole-unit
mbedtls_aes_crypt_xts is not that callback. A real owned wrapper must fit1072
and alignment16 using genuine headers; no foreign/const cast or retained key
pointer. Selected kernel wrapper ignores the xts pointer return, so callback
error tests do not qualify native error propagation. KRN-028 implements none
of that adapter and obtains no new XTS vectors; KRN-029 owns actual host/ARM
CPU adapter/vector qualification under its separate claim.

Other important gates: Mbed GCM has distinct inline/generic/PSA ownership
paths; BearSSL GCM borrows an AES context. Selected managed nonce is12 bytes
(salt4 + big-endian counter8). Mbed RSA import and public verification allocate,
while selected RSA has no free callback. BearSSL RSA borrows big-endian N/E
and returns recovered hash/validity; genuine XNU representation/endian/limits,
OID conversion, digest comparison, lifetime and stack remain bridge work.
BearSSL public ChaCha API is whole-message, not the selected ten-method stream.
Generic CBC-CS3 is not provided by the reviewed APIs and is not XTS stealing.

Primary NIST DES/TDES KAT/MMT source artifacts provide1000 parsed ordinary
ECB/CBC records in14 files;7 CBCI files are excluded. These are independent
vector inputs for a later DES/TDES implementation, not executed KATs, XTS
vectors or FIPS validation. Initial failed license-path and outdated-vector
URL acquisitions are retained; correct pinned bytes were subsequently verified.

Both Git guards are set; only isolated owned bare Git/source caches were
fetched. No main-reference hydration, phone/ADB/root/MMIO/flash/emulator,
global installation or heavy build was performed. No algorithm/backend or
provider executed. Full crypto, FIPS, private Apple ABI and native flags remain
false. Next: coordinator review/integration/common checks, then KRN-029.
Retain in_progress until coordinator acceptance.
