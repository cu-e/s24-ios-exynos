# Concrete next bridge interfaces

This is a plan for subsequent implementation claims. KRN-028 implements no
algorithm adapter, publishes no descriptor and registers no provider. The
exact21 declarations/offsets, function typedefs, ten ChaCha methods and demand
references are in `fixtures/public/crypto-candidates/requirements.json`.
All bindings refer to actual selected headers, not replacement SDK types.

## First implementation: AES-XTS in KRN-029

Use actual public Mbed TLS AES primitives at
`068ff080b369adfac81509f9b57b2afabaf82dc5`, with the Apache-2.0 license choice
and original per-file notices. Source is `library/aes.c`, declarations are
`include/mbedtls/aes.h`. The proposed descriptor bridge covers only
`ccaes_xts_encrypt` and `ccaes_xts_decrypt`. BearSSL remains an alternative
primitive source, not an already exposed public XTS API in this review.

The authoritative selected `struct ccmode_xts` is in
`EXTERNAL_HEADERS/corecrypto/ccmode_impl.h` at XNU
`c54f35ca767986246321eb901baf8f5ff7923f6a`:

| Member | Exact parameter roles and return |
|---|---|
| `init` | `int`: const descriptor, mutable `ccxts_ctx`, `size_t key_nbytes`, const data-key pointer, const tweak-key pointer |
| `key_sched` | `void`: same five parameters; it must perform real key expansion, not an empty compatibility callback |
| `set_tweak` | `int`: const key context, mutable `ccxts_tweak`, const16-byte IV pointer |
| `xts` | `void *`: const key context, mutable tweak, `size_t nblocks`, const input, output; success returns the actual tweak-buffer pointer |

`key_nbytes` describes each of two separate keys. The pinned Mbed XTS API
supports total256/512-bit combined keys, so a proposed primitive bridge should
explicitly admit16/32 bytes per key; other-key-size/error compatibility remains
an explicit gate. Never reinterpret the selected per-key count as total bits.
For encrypt, expand the data key for AES encryption; for decrypt, expand it
for AES decryption. The tweak key always uses AES encryption in both cases.
`mbedtls_aes_setkey_enc`, `mbedtls_aes_setkey_dec` and
`mbedtls_aes_crypt_ecb` are real named APIs with verified bodies/declarations.

The existing whole-data-unit `mbedtls_aes_crypt_xts` cannot be assigned to
this callback. It takes a data-unit IV and byte length, creates a local tweak,
restarts it on every call, and returns an integer. The selected API takes a
caller-owned mutable tweak and block count and returns its pointer. Calling
the whole-unit routine separately for chunks would restart progression.

Primitive glue is demonstrated by the actual licensed XTS source:

1. `set_tweak` computes AES encryption of the raw16 IV bytes under the tweak
   key. Do not reinterpret IV bytes as a host integer or increment a sector
   number implicitly. Initialize an owned per-sector block-progress record.
2. For each complete block, XOR input with current tweak, run the real AES
   ECB primitive under the data key/direction, XOR the result with the tweak,
   then advance tweak with the pinned `mbedtls_gf128mul_x_ble` convention.
   This helper is internal source, so adapting it needs source attribution;
   do not pretend it is an existing public exported API.
3. Keep the advanced tweak in the caller's tweak buffer across split calls.
   Test one call against several chunk calls, repeated resets, both key sizes
   and both directions. Admit block-count multiplication and cumulative sector
   bounds before writes; the pinned whole-unit code limits units to2^20 blocks.
4. Define zero-block behavior and invalid-state/error behavior explicitly,
   preserving output/tweak on rejected admission. `key_sched` cannot return
   an error: if retained, it must compute schedules and leave explicit invalid
   state on failure for the later checked operations. Use genuine selected
   error constants/interfaces rather than invented SDK declarations.

There is no partial-byte length in this callback. The selected wrapper admits
only multiples of16; its path does not ask the descriptor to perform final
partial-block stealing. Generic CBC-CS3 is a separate missing API and cannot
be filled by calling AES-XTS's ciphertext-stealing branch.

Storage and lifetime gates are concrete. The measured selected ABI gives
each `symmetric_xts.enc/dec` a fixed1072-byte buffer and16-byte alignment.
An owned wrapper must contain genuine backend context types and prove its
size/alignment fit using actual target compilation before use. `.size` and
`.tweak_size` must be actual owned-wrapper sizes, with immutable descriptors
outliving all contexts. Copy/expand input keys during initialization; retain
no borrowed key pointers and no heap pointer requiring a missing free hook.
All temporary schedules and working blocks need genuine zeroization.

The selected `xts` callback takes a const key context, while Mbed's ECB API
takes a mutable context. Avoid a foreign-context/const cast: in the regular
non-ALT profile the pinned AES context is self-contained (`nr`, `rk_offset`,
key buffer), so a bounded temporary context copy is a possible interface plan.
Qualify that profile and target copy/alignment semantics, disable unqualified
hardware/ALT paths, measure stack cost and clear temporary copies. No foreign
context size or safe-copy property is claimed measured here.

`libkern/crypto/corecrypto_aesxts.c` calls `set_tweak` and then `xts`, but ignores
the latter's pointer return and returns0. Therefore direct descriptor error
tests alone cannot qualify that kernel wrapper's error propagation. KRN-029
must preserve this integration limitation or separately scope a genuine caller
fix; it must not imply native safety from a host adapter test.

Use independent primary AES-XTS vectors and an independently selected peer
for KRN-029, then run the same real adapter on its host and authorized ARM CPU
harness. Obtain/pin those vectors in that claim; KRN-028's downloaded vectors
are DES/TDES data, not XTS vectors. Correct output, ARM execution and compiled
typed descriptors still do not establish Apple private ABI, kernel execution,
side-channel assurance, encrypted-volume compatibility or FIPS validation.

## Following interfaces and their unresolved ownership

**DES/TDES ECB/CBC and helpers.** Mbed's low-level DES APIs have concrete
caller-owned schedules and parity/weak-key routines; choose them rather than
generic cipher wrappers that allocate. BearSSL `des_ct` has real static CBC
APIs, while ECB needs a qualified internal primitive interface. Bind8/16/24
byte key policy, convert block counts safely, adapt distinct input/output and
mutating IV contracts, handle const-key-context versus mutable backend API,
and do real helper semantics tests. Neither ordinary CBC API provides CBC-CS3.
Independent NIST KAT/MMT sources already available here contain1000 parsed
ordinary ECB/CBC records; CBCI records are explicitly excluded. `KEYs` means
the8-byte key repeated for K1=K2=K3; MMT2/3 files exercise other key forms.
No vector has been run against any candidate in this research task.

**GCM.** A bridge must own AES key state, authentication state, phase and nonce
state, with stable internal pointers and appropriate alignment. BearSSL's GCM
context borrows its AES-CTR context; keep both in one correctly owned lifetime.
Mbed has an inline legacy block-cipher configuration and a distinct allocating
generic-cipher path; PSA may own key handles. Do not claim either default is
kernel-ready. Mbed's API permits buffered output variants, so prove immediate
output for arbitrary selected `nbytes` or port an actual compatible primitive.
The selected header defines managed GCM IVs as12 bytes:4-byte salt followed by
an8-byte big-endian counter, with reset/inc-IV lifecycle and no set-IV mixing.
Uniqueness/exhaustion, partial data, tag errors and phase rejection need tests.

**ChaCha20-Poly1305.** The fixed selected context is256 bytes/alignment8.
Mbed has streaming calls; its actual target context plus owned nonce/phase
bookkeeping must be proven to fit. BearSSL's reviewed public API is whole-message
in-place; it needs an actual licensed incremental source port, not unlimited
message buffering. Implement and verify every one of the ten selected methods.
The selected header does not specify enough here to qualify nonce increment
encoding by analogy with GCM. Tag verification must compare in constant time,
and callers must not treat streamed plaintext as authenticated before success.

**RSA.** The selected public container is1584 bytes/alignment8, maximum4096 bits,
and uses genuine `ccrsa` number/representation macros. It has no backend-free
callback, and the consumer prewrites the genuine `n` field. Mbed import and
public PKCS1v1.5 verification allocate; a persistent foreign MPI context is
not a valid drop-in object. Any transient import/verify path must release all
allocations, map allocation failure and qualify whether the actual caller may
sleep/allocate. BearSSL public keys borrow big-endian modulus/exponent arrays;
store owned bytes in the genuine selected representation and construct bounded
transient views, with endianness, exponent/modulus limits and stack analysis.
Its verifier returns a validity bit plus recovered digest, with length-prefixed
OID input. This needs genuine OID conversion, digest comparison and separate
status/`bool *valid` semantics; a function-pointer cast cannot provide them.
These public operations need no internal RNG callback; nonce/key and kernel
entropy ownership stays external. Do not link desktop system seeders into XNU.

No method above may be published as a success stub. Full provider initialization,
allocation/entropy/ISA profiles, caller lifetime, ABI and runtime integration
remain separate gates after each independently tested real adapter.
