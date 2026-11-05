# Genuine guest crypto route

VM-031, owner `codex-guest-exec-20261106-dm`; source review only.

The selected Scion guest already supplies a genuine minimal crypto provider.
Complete native E1S crypto integration is not an established prerequisite for
attempting the first genuine guest console. The next relevant gate is compiling
and linking the unchanged coherent guest route, then observing its actual startup
and boot consumers. This audit creates no provider, stub or reduced profile.

The frozen VM-008 graph contains 1080 source/recipe slots, SHA256
`afc5cd206965de7e36a0aa17c4eb86a1f305689f386ccb22c55bd983567dd1dd`.
The provider exactly matches Scion commit
`a6f4bc38aa244359cd365c976244a88c9d6b3304`, canonical Git blob
`4ba60565d8ccb9943a7dba22e91b69df28b02db2`, SHA256
`06e18046c6073eb32add23fb4eab4e85646518a19b27d44eff32a1a1aff64869`.
Public XNU is pinned at `c54f35ca767986246321eb901baf8f5ff7923f6a`.
[inputs.json](../../../fixtures/public/avf-guest-crypto-route/inputs.json) binds the
source manifest, relevant source/header bytes and separate adapter descriptors.
Upstream sources retain their component notices in the immutable source tree.

The selected registration declaration contains 56 fields. The donor initializer
assigns 34 statically and assigns SHA256 after CE initialization, before publishing
the table. All remaining 21 fields have C static zero initialization: two XTS,
two GCM, two GCM helpers, one ChaCha table, eight DES/TDES modes, two DES helpers,
two CTS3 and two RSA callbacks. These are unsupported surfaces. Their presence in
a selected wrapper or a direct textual reference does not establish execution on
the console path. The donor comment's ramdisk-shell claim is upstream source
commentary; this task has not observed such a shell.

The actual source route is `mc_digests`, `mc_provider`, `mc_aes`, `mc_ce`,
`mc_keywrap`, Monocypher and three BearSSL AES objects, together with selected
public digest/HMAC/DRBG/SHA helpers and kernel PRNG/entropy objects. The route
manifest retains each object's exact source, configuration hash and genuine
future compile argv, including `mc_ce_asm.h` include text. These are source recipe
memberships; there is no object definition/import measurement in this task.
`mc_keywrap`/Monocypher membership does not mean the provider invokes them during
initialization. No E1S source object, SDK header or native archive is substituted.

`minicrypto_init` is registered at EARLY_BOOT/FIRST. Source order is digest/AES
selftests, `mc_ce_start`, deferred SHA256, `register_crypto_functions`, then
`register_and_init_prng` after successful registration. Registration retains the
table pointer; its static mutable callback table is not copied or sealed by
registration. An existing provider returns -1, so that branch also skips this
donor's PRNG initialization. Actual startup sorts by subsystem then rank and
invokes the hooks; kmem's random context initialization is EARLY_BOOT/MIDDLE.
The source order therefore supports this intended provider-before-kmem route.
It does not establish linker section retention, extraction, address correctness,
execution, the absence of competing FIRST-rank providers, or entropy quality.

The donor PRNG is a single shared HMAC-DRBG with interrupts disabled around its
simple lock. `initgen` intentionally does nothing because all CPUs share that
generator; this existing source behavior is not a new success stub. DRBG init and
generation errors panic, while reseed discards `ccdrbg_generate`'s return. The
source uses `strictFIPS=0`, boot seed, timebase nonce and the kernel entropy
collector. CE source checks the architectural feature register and has a C
fallback after selftest failure. None of entropy security, bounds, interrupt/
thread safety, instruction availability or FIPS is qualified by this audit.

The native/component routes remain separate:

| Route | Existing evidence boundary | Guest consequence |
| --- | --- | --- |
| KRN-031 XTS | Accepted genuine native provider/caller patch, strong selected graph and bounded synthetic CPU evidence | Does not patch the frozen guest provider. Guest XTS stays unassigned. |
| KRN-032 DES/TDES, KRN-033 GCM, KRN-035 RSA | Accepted typed public adapters and bounded tests | Factories/helpers alone do not publish guest callbacks or prove guest ABI, storage, imports, initialization or startup. |
| KRN-034 ChaCha | Reviewed nine-method subset; exact selected `incnonce` contract remains blocked | No complete ten-method provider claim. This does not block a measured guest path that never invokes it. |
| KRN-036 CTS3 | Separate pending integration/review; generic callbacks tested with real bounded CBC fixtures | CBC16 and memory services are fixture-only; production CBC provider/import closure and selected NFS ignored-return handling remain separate gates. |
| KRN-039 DES native caller integration | Separate pending owner/review/runtime work | Actual strong native providers/caller modifications are not the frozen guest source. No shared039 edits or inferred guest dependency. |

For the minimum console attempt, retain the selected Scion provider and all
selected features/exports. After namespace acceptance and root admission, compile
its actual guest objects and inspect genuine definitions/imports, complete link
and startup sections. Observe selftest/CE/registration/PRNG progression and the
actual console/ramdisk/PID1 path under an explicit guest lease. A failure then
identifies an actual missing callback or route dependency; source counts cannot
predict a positive boot. Encrypted filesystems, IPsec, signatures and other users
of absent slots need their own real integration and consumer/error qualification.

Reproduce the finite source audit in a fresh owned destination:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
python3 -s tools/build/avf_guest_crypto_route.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out docs/procedures/avf-guest-crypto-route/runs/NEW
```

The reader streams hashes, verifies every bound guest source, records direct
source/header demand witnesses and rejects altered source/rank/callback/deferred
SHA/publication order. Its source scan strips comments but does not preprocess;
header or unselected source references retain empty selected-object witnesses.
There is no inferred reachability or ABI offset measurement. Limits are 256 MiB
address space and 60 seconds; current-image VmHWM/RSS are recorded separately
from inherited historical `ru_maxrss`. No compile, preprocessor, generator, link,
QEMU, network acquisition, physical device action or MAIN common check occurs.

The first planned run is retained under `runs/source-audit1`: it stopped on an
actual non-UTF8 byte in source after admission, before completing the scan. Its
current-image VmHWM was 73,028 KiB. The corrected reader uses lossless Latin-1
for ASCII C tokens; no source byte or input hash changes. Read-only discovery
failures are preserved separately in `discovery-failures.json`. A documentation
patch initially failed to match its expected sentence and was reapplied to the
actual sentence; it changed no source or measurement output.

The corrected preplanned VMCRYPTO-002 run at source qualifier
`9fc0a5b3ced553d801481e5e1984b94d703daf89` passes: all 1080 selected source rows
match, 3842 source/header files yield 89 direct field references, 32 relevant
crypto/startup recipes are bound, and five altered-input controls reject. The
registration/PRNG token inventory contains the actual definitions/declarations
and the donor provider calls; it finds no other direct source caller. This is a
textual inventory, with macros/external consumers and runtime still unmeasured.
Elapsed time was 5.868 seconds, current-image VmHWM 76,724 KiB, and the minimum
of three one-second admission samples was 13,776,150,528 bytes available.
`evidence.json` binds both unchanged raw runs and the full route manifest.
