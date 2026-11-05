# KRN-034 ChaCha20-Poly1305 component procedure

Owner `codex-team-crypto-chacha-20261105-bu`. Own only the ChaCha source and
procedure boundaries. This task registers no provider and does not relink or
boot XNU or touch a phone. Exact selected XNU declarations, KRN-028 requirements,
accepted runtime, source references and existing artifacts remain read-only.

Use the genuine ten-method function table and genuine 256-byte alignment8
context. Choose pinned permissively licensed streaming primitives, preserve
component notices and prove actual target fit; no allocating generic cipher,
foreign-context or function-pointer casts, fake SDK records, duplicate global
zeroizer or unlimited message buffering. Import accepted XTS zeroizer and
read-only runtime. Streamed plaintext is unauthenticated until verify succeeds.

Nonce increment encoding and lifecycle require genuine primary implementation
or consumer semantic facts. Restricted source may provide limited cited API
facts only: never copy/translate its implementation into project code. If exact
compatibility cannot be established, retain explicit incomplete acceptance;
a fail-closed callback is not a qualified ten-method implementation.

Before execution, plan experiments. Qualify actual selected source/callers,
primary RFC vectors and independent implementation oracle, then execute real
streaming, tag, phase/reset, nonce/exhaustion, alias/bounds and failure controls
with native ASan/UBSan. Compile actual typed ARM objects and execute bounded
CPU fixtures through accepted unchanged AVF/shim/QEMU only after root grants
exclusive256MiB QEMU use. No heavy build/relink or device action is authorized.
One compiler at a time, at most256MiB new RSS; aggregate below2GiB and host
MemAvailable at least4GiB. Save exact commands/exits/sources/tools/hashes and
failed evidence, scoped commit and handoff; retaininprogress for root review.

## Current boundary

The factory is deliberately named `s24_chacha20poly1305_experimental_functions`.
It returns the real selected ten-slot type, but only the explicit-nonce subset
is implemented. `incnonce` returns genuine `CCERR_NOT_SUPPORTED` without mutation.
This is an incomplete compatibility gate, never successful nonce exhaustion or
all-ten-method qualification. See `nonce-contract.json` and independent KRN-037.

Owned RFC8439 glue uses Mbed TLS ChaCha20 and Poly1305 primitives at
`068ff080b369adfac81509f9b57b2afabaf82dc5`, under their retained Apache-2.0 option.
The combined Mbed AEAD implementation is not used. Vendor provenance binds
canonical Git blobs and the accepted full archive. The earlier research cache
had a truncated `check_config.h`; this was detected and corrected from canonical
complete bytes before the first compile. Shared cache and source remain intact.
No Apple implementation body is saved, copied, translated or linked.

The context contains no pointers or heap ownership. Its actual native size is
256 bytes/alignment8, including genuine136-byte ChaCha and80-byte Poly1305
contexts. Actual selected context size/alignment is256/8 and table80/8. Owned
state moves through selected storage with `memcpy`; no replacement ABI structs
or function-pointer casts are used. Native relocation checks prove exact typed
method bindings. This is storage/method compatibility, not compatibility with
private code that inspects Apple's internal context fields.

`init` installs a32-byte key; `reset` retains that key, clears stream/MAC state
and requires another explicit12-byte `setnonce`. AAD precedes one stream
direction; finalization or verification consumes that message. The caller owns
global key/nonce uniqueness, accessible buffer capacity/lifetime, serialization
and authenticated packet admission. Same-buffer operation is supported; partial
overlap, context overlap, null nonempty buffers, pointer-extent wrap and wrong
phase are rejected before mutation. Zero-length NULL input/output is accepted
in a valid phase. Contexts require the actual selected8-byte alignment.

Decrypt emits unauthenticated plaintext immediately. A bad tag consumes the
message and cannot revoke already emitted bytes: callers must quarantine and
discard them. The fixture tests this boundary explicitly. Temporary keys,
one-time key blocks, local states and tag buffers use the single imported
accepted XTS zeroizer; public `clear` wipes all256 context bytes. No claim is
made about whole-program register/spill erasure or inaccessible pointer mappings.

## Reproduction

Plan an unrecorded matching experiment through the MAIN ledger first. Both
runners verify the actual current owner/claim and planned entry before each
child. A submitted CLI with pending output is insufficient. The first corpus
acquisition genuinely preceded the corrected plan after a failed procedure-path
submission; its actual timing is preserved, and all component execution uses
verified canonical plans.

From this worktree, with the matching `CHACHA-002` planned entry:

```sh
python3 src/platform/crypto/chacha/check.py --run fresh-host-arm-name
```

The check regenerates two primary RFC8439 section2.8.2/A.5 vectors and57
independent OpenSSL EVP vectors, verifies source/oracle/dependency identities,
then runs the actual streaming adapter with native ASan+UBSan. Tests cover
eight chunk patterns including single-byte and whole-message updates, AAD
boundaries, empty messages, exact in-place and disjoint buffers, reset, all16
corrupt tag positions, AAD/ciphertext corruption, phase/alias/extent guards and
context clearing. Artificial owned-state injections exercise byte/block counter
overflow guards without allocating256GiB; they do not qualify nonce increment.
Deliberate heap overflow and signed overflow must actually trigger their native
detectors. Three unsupported primitive profiles must fail compilation.

The same suite compiles through the genuine selected native header and table,
with exact ten relocations and a single imported zeroizer in both outputs.
Assembly is retained for bounded tag-comparison review: the observed target
loop compares16 bytes with public-index control and accumulation, and tests the
result after the loop. This is not whole-primitive or timing/side-channel proof.

Only after the coordinator grants an exclusive256MiB CPU lease and plans
`CHACHA-003`, run already qualified immutable outputs:

```sh
python3 src/platform/crypto/chacha/cpu.py --from-run qualified-host-arm-name \
  --run fresh-cpu-name --lease 'exact coordinator lease reference'
```

The unchanged accepted runtime requires its historical `_xts_entry`, cookie and
XTS harness markers. Only our entry/stack/suite are linked; no original XTS guest
is linked. Unique `CHACHA ARM PASS/FAIL` markers identify this algorithm. The
runner checks physical entry/bootargs, identical host/ARM check count and real
normal shutdown, wrong-cookie rejection, corrupted expected-vector failure and
supervisor cleanup after deliberate spin. QEMU virt is not an Exynos model and
does not execute XNU. CPU execution requires the separate lease even when host
checks pass. No kernel provider is registered.

All reports retain overall `inconclusive` while the nonce contract is missing;
supported host/ARM/CPU outcomes are separate fields. A zero process exit means
the requested supported-subset check passed, not complete KRN-034 acceptance.
Reports include exact commands, exit/outcome, source snapshots, tool/object/
header/oracle hashes and process/resource cleanup. Failed sessions are retained.
