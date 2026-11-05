# Independent KRN-029 typed AES-XTS review

Reviewer `codex-team-review-xts-20261105-bp`, task REV-014.
Frozen implementation 396517f55102a2ded50245b053684dfffb6c2ec8 plus
7b7607b1f907d2e51dbb55766de9cdee772c0842; final metadata
de3c63326c1e89c232bfd018a4c940b13179766e.

## Result — 2026-11-05

**No P0, P1 or P2 finding was identified within the documented descriptor and
synthetic-test boundary.** Independent host/corpus checks and actual ARM payload
replays passed. REV-014 remains in progress pending coordinator inspection,
integration/common checks and acceptance. No implementation, shared source,
artifact, provider registration or original owner was changed.

This result establishes functional full-block XTS behavior against the admitted
vectors and the tested lifecycle/error contract. Software ROM-table AES has no
side-channel assurance here. FIPS, production key/sector policy, private Apple
ABI, a registered provider, XNU, encrypted volumes and native S24 operation remain
unqualified. The selected kernel wrapper still ignores the xts pointer return;
direct descriptor tests cannot repair its error propagation.

## Exact source, primitive and corpus

The authoritative qualified-evidence file points to the actual final-commit2 raw
capsule at implementation 7b7607b. Its report digest, all **125 artifact hashes**,
every owned source hash and actual dependency/tool/runtime hashes match. Exact
adapter, memory helper, checker and synthetic-runtime Git blobs agree with the
frozen candidate. All 14 consumed corecrypto declaration files were independently
read from pinned XNU c54f35ca767986246321eb901baf8f5ff7923f6a Git blobs and matched
to the actual compilation inputs. No SDK descriptor replica or function-pointer
cast was introduced.

Independently opened the retained primary Mbed TLS archive, verified its pinned
SHA256, and compared every vendored file with its exact archive member. All are
identical except the explicitly recorded common.h include-only adaptation; its
preimage/postimage and exact conditional omission of assert.h match. Complete
LICENSE, dual per-file notices, Apache-2.0 choice and XEX/GF attribution remain.
The profile uses actual inline-buffer AES contexts and static ROM tables; ALT,
accelerated/assembly and PadLock profiles are explicitly outside qualification.
Original negative profile and real ASan/UBSan detector controls are hash-bound.

The independent NIST parser reconstructed all **1200 raw-IV complete-block
records** from the untouched primary archive, including 600 records from each
original direction section and both per-key lengths. It independently counted
800 excluded partial-bit/block records and 2000 excluded sequence-number records.
Fresh OpenSSL EVP execution regenerated the complete 1200-record cross-check plus
20 deterministic extra records; JSON/header bytes exactly match the consumed
corpus. The installed libcrypto binary path/hash/version are pinned independently;
a distro-binary rebuild from the cited source is explicitly unproven. A NIST
vector match is not FIPS validation or proof of authenticated encryption.

## Ownership, arithmetic and error assessment

Line references below identify src/platform/crypto/xts/xts.c at the frozen tip.

| Boundary | Inspection and independent challenge |
| --- | --- |
| Genuine callbacks/factory, lines 175–185 | Actual selected ccmode_xts fields are assigned with their true init, void key_sched, set_tweak and pointer-returning xts signatures. The descriptor must be initialized before publication, retained and immutable; this is a caller lifetime/serialization precondition. Target object decoding independently gives descriptor 80 bytes, owned key 608/alignment16, tweak 48/alignment16 and AES context 288. The key fits the selected symmetric_xts opaque allocation. Invalid factory direction leaves the real descriptor unchanged. |
| Init/key_sched, lines 67–106 | Two 16/32-byte keys are interpreted per key, compared for equality, and expanded into owned schedules. Data direction changes the data schedule; tweak schedule always encrypts. The void key_sched takes the same actual expansion/error-clearing path. Working schedules and failed destination state are cleared; no caller key pointer is retained. Separate-key vectors, both directions, input-key changes after init and invalid sizes/equal keys are exercised by the original and independent suites. |
| Rekey/identity, lines 89–95 and 146–148 | A nonzero relaxed atomic generation identifies a serialized key instance; UINT64_MAX rejects rather than wraps. Tweak owner address and generation reject wrong/copy-relocated keys and stale tweaks after identical rekey. Relaxed atomic uniqueness is not a substitute for caller synchronization. Copying or modifying contexts outside the stated lifetime rules does not become authenticated state. |
| Tweak/const handling, lines 107–126 | IV is read into owned temporary storage, AES-encrypted with the copied tweak key and bound to the original key address/generation. Original callback const is preserved by byte-copying into a genuine mutable temporary rather than casting it away. An IV alias into immutable key storage succeeds without changing the key. An IV alias into tweak storage is rejected with the documented tweak clearing. Volatile zeroization clears working records/IV/block temporaries; public clear APIs clear owned persistent extents. |
| XEX/endian progression, lines 128–166 | Bytewise little-endian GF multiplication avoids unaligned host integer loads. Full-block XEX and updated tweak state produce the pinned ciphertext/decryption across both key lengths, in-place calls and continuation splits. No ciphertext stealing is exposed; the genuine ccmode header itself separates that operation. Matching ARM/host actual algorithm results substantiate this functional boundary. |
| Limits/admission preservation, lines 143–154 | Valid key/direction/owner/generation and cumulative limit are checked before output. The 2^20-block budget and size multiplication are bounded. Zero blocks preserve state and admit NULL data pointers. Numeric input/output extents and partial overlap checks precede writes. Independent tests cover every byte-offset alias into owned key/tweak extents, partial overlaps in both directions, touching disjoint ranges, zero/huge counts, wrong direction/address and stale generations; rejected crypt admissions preserve output/key/tweak bytes. Original host execution also reaches the actual maximum cumulative unit. |
| Initializer failure effects | The crypt preservation promise does not apply universally to initializer destinations. Admitted invalid init clears key storage, including bytes used as an overlapping rejected raw key. set_tweak clears admitted tweak storage on invalid IV, including an IV alias into that tweak. Independent tests verify these actual documented clearing effects. The line74 comment must be read with the actual clearing at line78 and README's overlapping-input/writable-storage preconditions; no promise that rejected aliased source bytes remain unchanged is inferred. |
| Primitive-failure scope, lines 159–169 | The explicit unexpected ECB-failure branch clears output and invalidates tweak. Normal admitted schedules under the fixed profile cannot be made to return such an error by the public suite; this branch was inspected, not claimed as a fault-injected production recovery proof. Accessible capacity/mapping, serialized lifetime and unmodified caller storage remain prerequisites. |
| Synthetic memory/runtime | The exact memory.c byte routines are limited to the synthetic guest. Numeric memmove address ordering is present at 7b7607b; the original cross-object pointer relational comparison is gone. Independently compiled renamed copies of the real routines pass 132,096 overlap/compare cases plus byte/fortify bounds. An excessive fortified copy actually traps with SIGILL. QEMU UART/PSCI/bootarg/DT code is explicitly an owned virtual-board runtime, not an SDK record or phone MMIO implementation. |

The actual selected corecrypto_aesxts.c wrapper propagates set_tweak errors but
ignores the later xts return and returns zero. This known integration boundary is
preserved. The selected symmetric_xts uses genuine opaque declarations and its
native allocation-size expression; no private Apple implementation/layout was
reconstructed for this review. Kernel stack use, provider wiring, caller policy
and production concurrency/error propagation need their own qualified work.

## Actual independent reproduction

XTSREV-001 was registered before verification. Actual reviewer invocation:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-029/reproduce.py review1
```

Exit 0; UTC `2026-11-05T17:22:04.570009+00:00`. Six check groups / **31 commands**.
The original sanitizer host suite again passed 1220 records / 40,708 checks. The
separately authored [boundary_probe.c](boundary_probe.c) tested every record both
directions plus independent lifecycle/alias matrices, totaling **12,349 checks**.
It compiles with genuine declarations and links the exact hash-verified actual
sanitized adapter/AES objects. The actual memory source was separately compiled
under full ASan+UBSan with reviewer-only symbol renames to avoid interposing host
libc. Its normal cases pass and the isolated fortify excess exits -4 as expected.

Four immutable existing ARM payloads were replayed sequentially through the
unchanged hash-qualified AVF shim/QEMU bytes, each with 256 MiB guest RAM:

- Positive: actual entry/bootargs addresses and handoff verified; **40,703 checks**,
  failure_line zero and natural PSCI_SYSTEM_OFF/exit 0. Its console hash exactly
  matches the original positive execution.
- Wrong cookie: reject before algorithm PASS, natural bounded exit; original
  console hash reproduced.
- Corrupted expected ciphertext: actual ARM FAIL with natural PSCI exit and no
  PASS; original console hash reproduced.
- Spin payload: actual spin marker, no PASS, two-second owned-session deadline
  and verified cleanup. QEMU handled TERM and exited 0 after the recorded timeout;
  it is classified as a timeout control, not a successful algorithm run.

The five host-only maximum-unit assertions account for the host/ARM count
difference. The same real adapter/vector suite supplies both executions; a printed
PASS alone is not the acceptance condition. No provider or XNU kernel executes.

Maximum measured total owned RSS was **114,576 KiB**; actual reviewer process
VmHWM **27,728 KiB**. Compiler/test commands had 256 MiB budgets; guests had
512 MiB total-owned budgets, one at a time. All owned sessions were quiescent
after completion. The isolated fortify SIGILL and expected spin timeout are the
only exceptional outcomes. No broad backend/kernel build, global install, source
hydration, device action or later repeat run occurred. After testing completed,
the coordinator supplied a 4 GiB MemAvailable floor; a read-only completion-time
check observed 8,347,492 KiB. No further runtime command was started.

[reproduce.py](reproduce.py), [memory_probe.c](memory_probe.c) and
[object_reader.py](object_reader.py) retain actual commands/exits/stdout/stderr,
source/tool/input hashes, independently parsed corpus counts, lifecycle results,
guest acceptance/console hashes and process/resource observations. All generated
outputs remain local and untracked.

Evidence:
`worktrees/rev-xts-20261105/artifacts/rev-krn-029/review1/evidence.json`

SHA256: `44af27b7a56a81298f2195a76b5c199619c03758e333c0562da511e43d2e08c6`.

Adjacent report SHA256:
`88c8002e5a9b3e63f31a0d90458038927e4830a55d22bb343f1be5c54605e92e`.

Coordinator: inspect and accept this scoped review plus the upcoming primary
common check. This review closes no side-channel/FIPS/private-input/provider/
XNU/native gate and proposes no implementation revision or repeated tests.

## Reproduction procedure

Register XTSREV-001 before verification. Audit exact source, selected genuine
ccmode declarations/opaque sizes, primitive pin/license/profile/portability patch,
NIST and OpenSSL corpora, final raw capsule and original host/ARM controls. Review
init/key_sched/rekey, direction/generation/key/tweak ownership, const copies and
zeroization, count/extent/overlap/error effects, factory lifetime and synthetic
memory/runtime helpers. Preserve documented inaccessible-buffer/lifetime limits.

Independently reproduce host vectors and separately authored lifecycle/alias
negative controls using small sequential sanitizer compiles. If no competing
guest is active, replay actual immutable ARM payloads with reviewer-local logs
and finite process cleanup. No broad kernel/backend rebuild, provider registration,
fake SDK/descriptor records, phone actions or shared input mutations. Git guards
stay enabled; one compiler <=256 MiB and one 256 MiB guest at a time <=512 MiB RSS.
Record exact commands/exits/hashes, source/target identity, actual VmHWM and owned
cleanup. Commit only docs/reviews/krn-029, retaining in-progress for acceptance.
Distinguish functional host/synthetic-CPU results from side-channel/FIPS/private
Apple/provider/XNU/native qualification and the ignored kernel-wrapper return.
