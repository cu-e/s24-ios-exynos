# REV-021 independent generic CBC-CS3 review

Recommendation: accept the bounded KRN-036 component. No actionable P0/P1/P2
finding was identified within this scope. Coordinator integration/common checks
and explicit acceptance remain required; REV-021 stays in progress.

Reviewed series: 09111a9,89ff8f2,8a4233a,55ea7b7,80ee7fd,b9fa5ca. Frozen
final tip b9fa5ca8ecae38d42474bd02dfa5324aac937238 adds only metadata after
qualifier 80ee7fde7b7a67310a8eecdb1a015aa6aa8081ad. The compiled C/H,
fixture, oracle and suite bytes remain those of 89ff8f2. The independent audit
binds their exact Git bytes, current sources, native objects, consumed headers,
continuation artifacts and actual CPU payloads. Original failures remain intact.

The genuine selected ccpad.h requires at least one block plus one byte, and the
size_t callback signatures/opaque CBC context and IV declarations are genuine.
The NFS consumer routes shorter inputs elsewhere, uses ordinary CBC prefix plus
CTS tail, and discards the padding callback return. That ignored return is an
explicit future native-integration gate. No private Apple return/error behavior
is inferred from the local nbytes-success/zero-error convention.

Source admission establishes block size in 1..CCMODE_MAX_BLOCK_SIZE and n>b
before computing prefix_blocks=(n-1)/b-1 and d=n-prefix-b. Thus 1<=d<=b and
the saved tail is at most two selected maximum blocks, 32 bytes. Quotient-based
arithmetic avoids rounding-add overflow. Extent checks precede overlap arithmetic;
partial data overlap and context/descriptor/IV/data aliasing are rejected before
writing. Exact in-place and disjoint buffers are supported. Accessible allocations,
truthful immutable descriptor metadata, initialized matching-direction context,
and the backend's const/error behavior remain caller preconditions.

Encryption performs ordinary CBC and emits Y followed by the exposed prefix of
X. Decryption uses D(Y) to recover the missing suffix of X, decrypts reconstructed
X against the preceding CBC IV, and emits the recovered final plaintext tail.
The d==b case still swaps the last complete ciphertext blocks. Both directions
carry Y as next IV, independently checked against every corpus record. The caller
IV is committed only after every CBC call succeeds. An admitted CBC error clears
all advertised output while preserving the original caller IV; exact in-place
input is consequently erased, not restored. Fixed temporary plaintext/cipher/IV
buffers are cleared through the accepted single zeroizer.

Primary evidence is correctly labeled: six published RFC3962 CTS records; three
published NIST CBC records used to qualify CBC16; three explicitly derived
full-block CS3 permutations of those CBC records; and 372 independent OpenSSL
extras. The total is 381 CS3 and 18 CBC16 records. The independent parser checks
all six RFC byte offsets/values, three NIST CBC/permutation records, all six
key/block families and every planned length/zero/nonzero-IV combination. The
AES oracle uses genuine installed public OpenSSL C headers and opaque EVP
contexts with CS3 selected; DES/TDES answers are whole-CBC normative derivatives,
not published CTS vectors or a native DES-CS3 OpenSSL mode. Actual libcrypto and
provider modules are hash-bound; rebuilding that installed binary from source
is explicitly unverified. Failed original SP800-38A retrieval remains preserved.

The normative NIST addendum explicitly says the blocks are unconditionally
swapped, including a complete penultimate block. RFC3962's additional short-input
behavior does not override the selected stricter public contract. Sources:
[NIST addendum](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38a-add.pdf),
[RFC3962](https://www.rfc-editor.org/rfc/rfc3962),
[official NIST CBC examples](https://csrc.nist.gov/CSRC/media/Projects/Cryptographic-Standards-and-Guidelines/documents/examples/AES_CBC.pdf).
Exact local source hashes are preserved in the original and review evidence.

All 15 consumed canonical Mbed members match the complete pinned archive,
including the complete check_config.h and exact accepted common.h pre/postimage.
No old truncated raw catalog member is reused. The CBC16 bridge invokes the
unchanged real Mbed CBC implementation and is test-only. Independent Mach-O
decoding establishes genuine layout (CBC 40/context 16/IV 16 bytes, alignment 16,
fixture 304 bytes containing a genuine 288-byte AES schedule), typed relocation targets,
one CBC-enabled AES object and one accepted XTS zeroizer. Fixture/oracle/type/
suite sources are excluded from production.json.

Production native imports are exactly ___memcpy_chk, memcpy and the zeroizer.
The genuine selected string.h actually fortifies memcpy; the fixture supplies
the unchanged real trapping helper from accepted XTS memory.o. Production native
provider closure remains false. No shared ObjectData guard was weakened: the
actual qualified cctools nm handles the guest's legitimate 64 KiB zerofill stack,
while the original strict reader handles cipher/type objects. The independent
reader confirms the metadata/imports without treating zerofill as file bytes.

The existing actual host ASan+UBSan and ARM CPU each report 28794 checks. Six
profile rejection logs, actual ASan heap and UBSan overflow failures, and a real
selected wrong-return typedef compile error are verified. All four actual XNUP
payloads are checked against their original Mach-O bytes/cookies; corruption
flips exactly the first published RFC expected-ciphertext byte at image offset
70813. The actual linked entry/boot-args addresses match the positive console.
The corrupt payload fails at suite line 30; wrong cookie rejects before algorithm
success; spin reaches its 3 s timeout. All actual owned process lists are empty.
Synthetic runtime XTS labels and loader XNU wording do not establish XNU execution.

Independent focused host evidence adds 7722 ASan+UBSan checks over 12 selected
records, with both directions, full-block/tail/IV-Y, exact in-place, split prefix,
short/alias/overflow admission and errors AFTER a genuine CBC has already written
output/local IV. Every invocation is exercised as the failure point; complete
output erase, original-IV rollback, unmodified key/context and out-of-range
canaries hold. This differs from the original before-invocation fault injection.
A deliberately wrong expected byte exits 1 at record 0/direction 0; the positive
probe exits 0. Exactly one small compiler command plus two probe commands ran,
peak 76206080 bytes, under stable >=4 GiB admission, with no surviving owned child.
There is no reviewer guest or whole-matrix replay.

Reviewer-only failures are preserved: NIST192 ciphertext crossed a PDF form feed;
the first parser wrongly ended the field there. A normative wording assertion
expected “swaps” where the preserved text says “are unconditionally swapped”.
The subsequent source-hash guard correctly rejected a changed reader path;
the corrected continuation binds the immutable tested reader snapshot. One 45 s
resource deferral spawned no child. Successful extraction was retained rather
than repeated. These are tooling/resource outcomes, not production findings.

This review does not qualify a provider registration, native __memcpy_chk closure,
NFS error propagation, private Apple ABI/failure equivalence, FIPS, side channels,
full crypto, full XNU/iOS, Exynos hardware or a working native image. MAIN common
checks are deferred to coordinator scheduling after integration because they
invoke additional compilers outside this focused review.
