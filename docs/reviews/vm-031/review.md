# Independent VM-031 review

Verdict: PASS for the frozen source and evidence snapshot. No blocking source,
data or scope mismatch was found. Publication and common acceptance remain the
integrator's responsibility; this receipt does not close VM031 or REV044.

Reviewed producer HEAD `3d903f8173acf81dc8b2b21eb1b620c34567a38c` and source
qualifier `9fc0a5b3ced553d801481e5e1984b94d703daf89`, all nine scoped commits,
original procedure/handoff and maintained evidence SHA256
`8fb6d01fdb88653a9d3aebcd4ffadf6c7f425a0ea380de145f8d2a31651560e9`.
The qualifier and final tool bytes match
`a50048f526c3fe9998495152a796e32e86eef14f8e32bd2f7267bdf076297e1f`.
Later producer commits change documentation/evidence only. The original UTF8
failure, lossless Latin1 correction and discovery failures remain preserved.

## Independent observations

The narrow actual source agrees with all 56 callback fields: 34 static
assignments, deferred SHA256 descriptor initialization and 21 unsupported fields
left at static zero. Unsupported fields cover XTS, GCM helpers/modes, ChaCha,
DES/TDES modes/helpers, CTS3 helpers and RSA. This classification says nothing
about arbitrary calls outside the frozen route.

The provider source orders digest and conditional AES selftests, CE startup,
deferred SHA setup, registration and PRNG initialization. Selftest failures
panic. A competing provider causes registration failure and return before the
provider's PRNG call. Registration retains the mutable table pointer and sets
its publication flag afterward; the global pointer's late read-only annotation
does not establish a const pointed-to table or runtime synchronization.

The declared startup rank is EARLY_BOOT/FIRST, before kmem EARLY_BOOT/MIDDLE.
Actual startup source sorts subsystem/rank and invokes each entry. PRNG source
orders entropy initialization, context/table preparation, nonce, entropy-backed
initialization, initgen, ready publication and boot-seed clearing. The genuine
single-generator initgen is empty; reseed discards the DRBG status, and the
configuration disables strict FIPS behavior. These are source observations.

The review reuses the original 3,842-file receipt without enumerating the source
tree or calling the producer audit/main. It verifies all 89 published textual
demand witnesses through the 12 named files' exact bytes, lines and membership
metadata, and compares all 32 reported source/configuration/argv recipes against
the immutable graph. It does not repeat all 1080 source hashes. All 55 generated
source slots are outside the composed scan corpus. Separate historical native
input receipts are retained as historical inputs; native039 is not added as a
prerequisite for this source route.

## Focused controls and boundaries

Prospectively registered `REV044CTRL-001` ran source commit
`50548cebb0ab70a6e95238a211c237db1cc89a88`: 417 checks and 11 parser/tempFS
controls passed, exit 0, 2.2053807079792023 seconds, current-image VmHWM 75,788
KiB. Three one-second admission samples exceeded 4 GiB. The 90-second alarm and
256 MiB address-space/current-image limits were installed. Historical inherited
ru_maxrss is reported separately and is not used as current-image memory.
Owned temporary copies were removed; the frozen provider bytes stayed unchanged.
No compiler, guest or producer audit/main was invoked. Local Git queries were
finite and synchronous. The harness process completed normally.

Two nonblocking limitations were measured with synthetic owned copies:

- The producer's lexical reader leaves quoted literals and inactive branches as
  text. Published counts remain textual witnesses, not live call reachability.
- The standalone parser collapses duplicate initializer designators. A synthetic
  unbound duplicate passes that parser, while its changed file is rejected by
  the actual source-hash admission helper. This is not an admission bypass for
  the exact frozen snapshot; the parser is not a general C parser.

No source correction is required for this fixed snapshot. The controls do not
qualify corpus completeness, generated sources, preprocessing/full translation
units, extraction, linking, runtime registration, ABI, console, entropy,
cryptographic security, concurrency or FIPS behavior. No allcrypto milestone is
inferred. Concrete notes go to INT002/root for relay; the historical producer
DM is not currently known to be live and acknowledgement is not presumed.

The raw immutable review capsule is `runs/focused-1/evidence.json`, SHA256
`53c8cb801cd0cb4feba8e27e5a513016275438d8a0377f3222c8a1c1a7649cab`.
