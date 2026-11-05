# Bounded RSA public callback pair

This component implements the selected RSA public constructor and PKCS1-v1.5
signature verifier using genuine XNU declarations and pinned MIT BearSSL public
arithmetic. It allocates no MPI or heap context and registers no provider.
Its named C functions are `s24_rsa_make_pub`, `s24_rsa_verify_pkcs1v15` and the
genuinely typed callback factory `s24_rsa_callbacks`; there are no function-pointer
casts or replacement SDK structures.
The factory receives two distinct writable pointers of the genuine callback
typedefs; it supplies callbacks without installing a kernel table.

The profile is deliberately the actual selected `rsa_make_pub` wrapper: a real
`rsa_pub_ctx` allocation of1584 bytes/alignment8, prewritten n=64, maximum4096-bit
modulus/exponent. Smaller numeric keys still occupy that fixed container. Other
n values are rejected before macro-derived number offsets. Callers must provide
actual readable input buffers and a writable complete context; arithmetic extent
checks cannot establish memory accessibility. Construction requires exclusive
access; immutable constructed keys may be read by the stateless verifier.

N/E inputs are big endian,1..512 bytes each, with leading zeroes permitted.
The constructor stages a complete local genuine container and copies owned
numbers into `ccrsa_ctx_m/e`, preserving the destination on every rejected input.
Accepted values have odd N, odd3<=E<N, and N at most4096 bits. These checks do not
prove N composite or generate a key. Actual bit length is recorded. Input ranges
may not overlap the destination. Staging/transient buffers are cleared through
the accepted shared XTS `mbedtls_platform_zeroize`; no duplicate is defined.

The opaque funcs pointer and unused Montgomery regions remain zero. A successful
construction qualifies this callback pair only. **Do not pass its context to
other cczp/corecrypto operations.** General public-context/Montgomery/private-ABI
interoperation is unqualified; no invented function record is populated.

Verification serializes genuine number values into bounded automatic big-endian
arrays and creates a temporary real `br_rsa_public_key` view over those owned
arrays. No caller key pointer is retained. Recovered digest bytes are compared
with the supplied prehashed digest using a fixed-length XOR reduction; no hash
function or message hashing is implemented. This is not a side-channel claim.

OID conversion accepts NULL raw-digest mode, or DER tag06 with a short-form
payload length1..32 and canonical base128 subidentifiers. BearSSL receives the
required length-prefixed payload. This cap keeps its43-byte padding scratch
bounded. Digest lengths are1..64; identity is compared with the provided OID, not
looked up as a hashing service. The caller must supply readable OID bytes; the
selected ABI has no OID-buffer span argument. Longer/BER encodings are rejected.

| Result class | Status and output |
|---|---|
| Matching signature, padding, OID and digest | `CCERR_OK`, valid=true |
| Admissible but mismatching signature/padding/digest | `CCERR_OK`, valid=false |
| Invalid key/length/OID with valid distinct output storage | `CCERR_PARAMETER`, valid=false |
| Invalid output alias, misaligned context or impossible pointer extent | `CCERR_PARAMETER`, no storage written |

Callers must check status as well as validity, as the genuine selected consumer
does. The validity bool must be disjoint from all input extents. Signature,
digest and key are not modified. This component provides no signing, private-key,
PSS, generic MPI, RNG or provider initialization implementation.

The primary input is [NIST's RSA corpus](https://csrc.nist.gov/Projects/cryptographic-algorithm-validation-program/digital-signatures),
archive SHA256 `8405aeb3572a4f98ed4b1a3ccb3f2f49e725462dd28ec4759d6a15d88855d19c`.
It contributes481 supported records from four named PKCS1-v1.5 files.17 odd-nibble
message records remain unsupported/unresolved; they are not labeled malformed
or hashed by guessing missing bits. Integer signature S is converted by
[RFC8017 I2OSP](https://www.rfc-editor.org/rfc/rfc8017.html#section-4.1), including
one published positive with511 hex digits.10 further public cases use independent
Python integer arithmetic and OpenSSL, including4096-bit N and E, raw36 mode,
absent NULL parameters and controlled bad encodings. Published expectations and
independent encoded-message checks are not adapter round trips.

Actual host and accepted AVF/QEMU ARM runs each passed491 vectors and782,365
assertions. The unchanged genuine caller dispatch is exercised through a real
two-slot synthetic table, which is never registered. Actual invalid-signature,
wrong-cookie and owned-timeout controls passed. Observed guest stack high-water
was10,604 bytes of an owned64KiB stack; native production frame records are static.
These measurements do not prove a full native caller-stack budget.

All33 consumed BearSSL files match canonical exact-pin Git blob identities;
original MIT notices remain in vendor/. Genuine selected headers are compiled
and checked against XNU `c54f35ca767986246321eb901baf8f5ff7923f6a`. Linux-host tests
use the exact selected BSD compiler-enum macro block because glibc lacks it;
the real native profile uses genuine target headers directly.

`synthetic_mem.c` is an approved CPU-only fortified memset runtime provider.
It preserves the capacity guard and was independently checked for byte/zero/
int conversion, excess-before-write traps and reaped-child cleanup. It is excluded
from production manifests. The original missing-provider link failure is retained.
The shared virtual-board runtime remains unchanged, including its historical XTS
labels/cookie; separate RSA markers identify the algorithm actually executed.

Reproduction requires existing qualified tool/runtime inputs and a planned run:

```sh
python3 src/platform/crypto/rsa/check.py --run NEW_BUILD --archive ABSOLUTE_NIST_ZIP
# After an explicit exclusive coordinator lease:
python3 src/platform/crypto/rsa/run_cpu.py --run NEW_CPU --build BUILD/evidence.json --lease-id ACTUAL_LEASE
```

One compiler job is bounded to256MiB; process starts require MemAvailable>=4GiB.
The guest uses256MiB and runs only under an exclusive finite lease. No full kernel
relink, XNU boot, S24 operation, provider registration, private Apple compatibility,
FIPS validation or side-channel assurance follows from this component evidence.
