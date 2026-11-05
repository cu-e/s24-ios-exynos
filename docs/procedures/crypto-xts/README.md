# Genuine selected AES-XTS descriptor bridge

KRN-029 implements two actual full-block `ccmode_xts` descriptors. The adapter
compiles against selected XNU c54f35ca767986246321eb901baf8f5ff7923f6a headers
already present in the research workspace; none are replicated or redistributed.
`src/platform/crypto/xts/xts.h` exposes the owned descriptor factory and explicit
key/tweak clearing. There is no crypto provider registration in this claim.

## Ownership and exact operation

Call `s24_xts_descriptor(&mode, decrypt)` with decrypt0/1, then retain the
immutable descriptor for all its consumers. Its real function-pointer fields
are assigned without casts. Caller provides accessible16-aligned storage of
`mode.size` and `mode.tweak_size`, keeps it alive, serializes writes/clear/reinit
against all readers and supplies sufficiently large accessible input/output.
Pointer arithmetic checks establish numeric extents, not mapping or capacity.
The measured ARM key object is608 bytes/alignment16, below each genuine
1072-byte `symmetric_xts` buffer; tweak is48/alignment16; descriptor80 bytes.
The genuine backend AES context is288 bytes. No foreign object is overlaid by
casting: byte copies move owned records into genuine, aligned temporary C types.

Init consumes two distinct16/32-byte keys, **per key**, and retains expanded
schedules rather than input pointers. Data encryption/decryption schedules are
direction-specific; the tweak schedule always encrypts. Void `key_sched` executes
real expansion through the same path. An admitted invalid init clears the key;
misaligned/inaccessible/overlapping storage is outside its writable contract.
A global relaxed atomic64-bit generation, with overflow rejection, binds each
mutable tweak to this exact key instance and address. Reinit makes an old tweak
invalid, even for identical keys. Contexts cannot be relocated/copied after a
tweak is set. There is no persistent allocation, free hook, entropy or OS call.
Input key/IV uniqueness and sector policy belong to the caller.

`set_tweak` AES-encrypts the raw16-byte IV, resets the block counter and binds the
key identity. It clears an admitted writable tweak on error. Each `xts` call
performs genuine XEX, advances the little-endian GF(2^128) polynomial state and
writes it back, so split calls continue the same data unit. Zero blocks accept
NULL input/output and return the actual tweak pointer without state changes.
Nonzero calls accept identical or disjoint input/output, reject partial overlap,
key/tweak overlap, wrong direction/identity/generation, malformed schedules,
count/extent overflow, and more than2^20 cumulative blocks before writes.
Rejected crypt admissions preserve output/tweak. Unexpected primitive failure
clears produced output and invalidates tweak. Working schedules/blocks are
cleared through volatile stores; clear APIs erase persistent state. Context
mutation by the caller is not cryptographically authenticated storage.

## Primitive and profile

Real Mbed TLS AES is pinned to068ff080b369adfac81509f9b57b2afabaf82dc5.
The minimal source/header closure, complete upstream LICENSE, original file
notices, source hashes and one include-only freestanding patch are under
`src/platform/crypto/xts/vendor`. The component license choice is Apache-2.0.
The patch omits unused libc assert.h only in this named AES-only C profile;
it supplies no SDK types or assertion stub. Mode glue and GF progression are
attributed to the same licensed AES source.

`s24_xts_profile.h` admits regular software AES with static ROM tables. ALT,
AESNI, AESCE and assembly profiles are actively rejected in checks; PadLock is
also rejected in the configuration. No PSA/hardware/heap/entropy/selftest module
is enabled. The regular AES object contains only rounds, offset and inline key
words; offset0 and10/14 rounds are checked before calls. Copying it into a bounded
genuine mutable temporary avoids casting away callback const. Static tables
avoid runtime lazy initialization. Table lookups do **not** provide a
constant-time/side-channel assurance claim. Production profile selection and
kernel stack/concurrency policy remain integration work.

## Independent checks and reproduction

[Primary NIST XTS vectors](https://csrc.nist.gov/Projects/cryptographic-algorithm-validation-program/CAVP-TESTING-BLOCK-CIPHER-MODES)
are pinned by archive/file SHA256 in `testdata/vectors.json`. All1200 raw-tweak
complete-block records are used, including both original direction sections and
both key sizes.800 raw-format partial-bit/block records and2000 sequence-number
format records are explicitly excluded. No ciphertext-stealing support is
claimed. Each record is tested in both directions;1220 is the record count,
not the number of distinct encryption-only executions.

The independent oracle is the installed OpenSSL3.5.9 libcrypto binary, pinned
by full path/hash and version. It cross-checks every admitted NIST result and
creates20 deterministic extra records of1..256 full blocks. The real public EVP
API is called with one whole-unit update and double-length combined keys, as
specified by [its pinned primary documentation](https://github.com/openssl/openssl/blob/45e844fa2a14ec92d146bd8f5778ac130b6625fb/doc/man3/EVP_aes_128_gcm.pod).
The release/document/license pin is `oracle-provenance.json`. This is independent
binary-tool evidence; rebuilding that distro binary from that source is not
claimed. XTS provides confidentiality and no authentication.

From the task worktree:

```sh
python3 src/platform/crypto/xts/fetch_vectors.py --out artifacts/crypto-xts/primary-fresh
python3 src/platform/crypto/xts/check.py --run replay-fresh \
  --nist-archive artifacts/crypto-xts/primary-fresh/XTSTestVectors.zip
```

Every run must be fresh. The checker verifies source/input hashes, regenerates
the NIST/oracle corpus, compiles the actual host adapter with ASan+UBSan and real
heap-overflow/signed-overflow detector controls, then compiles actual ARM objects
using the qualified selected kernel recipe and genuine Clang builtin limits.h.
All actual dependencies, compiler/resource/sanitizer archives, expanded host link,
commands/exits/timestamps and source pins are recorded. Git reads disable lazy
fetch and optional locks. Shared references/artifacts remain read-only.

The same adapter/suite executes in a synthetic owned ARM64 MachO payload, using
`fixtures/public/avf-handoff/runtime.h`, the unchanged qualified AVF shim and
QEMU virt. It checks bootargs/DT/EL/MMU/cookie, calls the actual typed descriptors,
reports vector checks and exits via PSCI. Wrong cookie, one corrupted expected
ciphertext in the actual payload, and a separately compiled spin control verify
rejection/algorithm-failure/finite owned-session cleanup. No printed PASS is
accepted without expected entry addresses, algorithm count and natural exit.

One compiler runs at a time under256MiB monitored RSS; each guest has256MiB RAM
and512MiB total owned RSS budget. Session monitoring samples every50ms, records
child ru_maxrss and kills only owned descendants on deadline/overrun. Virtual
address-space limits are deliberately absent because lld/ASan reserve sparse
regions. The real maximum-unit cumulative test is host-only; ARM runs the same
suite except those five boundary assertions. No successful check is skipped.

## Limits and next integration gate

No XNU kernel or provider runs here. The selected kernel wrapper
`libkern/crypto/corecrypto_aesxts.c` ignores the `xts` pointer return and returns0;
these checked descriptor failures do not repair that caller. A separately scoped
integration must wire descriptors into a genuine provider, qualify caller key/
sector/lifetime/error semantics and repair error propagation if required. Full
crypto, compiler-runtime support, Apple private ABI, volume compatibility, FIPS,
side-channel resistance and native S24 operation remain unqualified. The virtual
runtime's UART MMIO applies only to QEMU's virtual PL011, never the phone.
