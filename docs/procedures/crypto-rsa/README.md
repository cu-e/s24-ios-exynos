# KRN-035 bounded RSA public callback pair

Owner `codex-team-crypto-rsa-20261105-bv`; branch/worktree
`team/krn-035-20261105` / `worktrees/krn-035-20261105`.
Only `src/platform/crypto/rsa` and `docs/procedures/crypto-rsa` are owned.
The sole registry is the primary checkout's `tools/lab.py --root MAIN`.

Implement only genuine selected public-key construction and PKCS1v1.5 verify
callbacks, using genuine selected XNU headers and public licensed BearSSL i31
arithmetic. No allocating MPI, borrowed persistent keys, fake SDK records or
function-pointer casts. XNU revision is
`c54f35ca767986246321eb901baf8f5ff7923f6a`; MIT BearSSL revision is
`7bea48e5e850ab4cafbe68d3765cdaba13a86d6f`.

The selected caller prewrites `ccrsa_ctx_n` with64 units (4096 bits), into the
real1584-byte/alignment8 `rsa_pub_ctx`. Validate n and pointer arithmetic before
using genuine representation macros. Copy big-endian modulus/exponent into
owned genuine number arrays; form bounded transient byte views for the public
primitive. `struct cczp_funcs` remains opaque: this component does not qualify
unrelated cczp/public-crypt methods, full corecrypto interoperation or provider
registration. The coordinator accepted this precise callback-pair boundary.

Actual selected ASN.1 OIDs are DER tag06 plus short length and payload; BearSSL
expects length plus payload. Bound conversion before its fixed padding scratch
buffer. The genuine verifier also permits NULL-OID raw-digest mode. Status and
`bool valid` are separate; failures must not expose stale validity or digest.
Pointer readability remains a caller precondition because this callback has no
OID-buffer length argument. No native/private compatibility inference follows.

Register experiments before checks. Preserve failure capsules, source/licenses,
commands/exits/hashes and handoff. Import the accepted XTS zeroizer and shared
synthetic runtime read-only; no duplicate global definitions. One compiler job
at most256MiB, aggregate2GiB, MemAvailable at least4GiB before each bounded run.
Coordinator currently pauses compilers, sanitizer execution and QEMU while memory
is below that threshold; source/preparation may continue. QEMU additionally
requires an explicit exclusive256MiB coordinator lease. No unrelated process,
swap/cache changes, heavy kernel relink or phone operations.

Use primary published vectors plus an independent modular-arithmetic/OpenSSL
oracle; include malformed key/endian/size/OID/padding/status/lifetime/stack
controls, real host sanitizer failures and actual typed ARM CPU execution.
No FIPS, side-channel, provider registration, private ABI, XNU/native result is
claimed. Retain in_progress until independent review and coordinator integration.

## Actual stage witnesses

All paths below are under this worktree's `artifacts/crypto-rsa/`. Originals are
immutable; publication wrappers bind original hashes and primary-checkout paths.

| Experiment and capsule | Actual outcome |
|---|---|
| RSACOMP-001, `host-build-session1` | Failed resource admission before compilation, after actual source replay and tool-version children. Original plus corrected main-path wrapper retained. |
| RSACOMP-002, `host-build-session2` | RSA adapter compiled; genuine register typedef compilation found missing Darwin compiler-enum macros on Linux. No fake SDK records substituted. |
| RSACOMP-003, `host-build-session3` | Actual491-vector/782,365-check host ASan/UBSan pass, deliberate sanitizer failures, actual unchanged caller dispatch and genuine native/CPU objects. Overall capsule failed the CPU image link at missing `___memset_chk`. |
| RSACOMP-004, `finish-session1` | Frozen bytes rechecked; memory gate stopped before any new compiler/helper/link child. No new algorithm execution. |
| RSACOMP-005, `finish-session2` | Reused frozen successful objects, added only the approved synthetic checked-fill provider, passed8,304 independent memory checks and linked two actual CPU images. Canonical selected headers and accepted complete shared dependencies matched. |
| RSACOMP-006, `cpu-session1` | Actual ARM491-vector/782,365-check pass,10,604-byte observed stack; wrong-cookie, actual positive-signature mutation and3-second owned-spin controls passed. Zero owned processes remained; lease immediately released. |
| RSACOMP-007, `qualified-evidence.json` | All41 compiled owned C/header files match implementation commit `a81876609fa33928f0c415f6a7d4b30013ed9ef6`; actual19-object native symbol closure has no allocating imports. No compiler or guest executed. |

The final publication audit binds actual compiled C/header bytes to a frozen Git
commit and inspects real native object symbols. It runs no compiler or guest.
The overall public component evidence composes the actual successful phases;
it does not relabel the retained failed capsules as passes.

Complete raw source integrity is enforced against canonical Git object identities
for all33 BearSSL files, not only catalog SHA values or header filenames. The
unchanged selected XNU callback declarations/caller and19 consumed selected
headers are checked against the full pinned source. The real shared zeroizer
object and its AES companion are digest-bound to accepted XTS evidence; all
consumed full XTS headers match its accepted source manifest. No shared source,
artifact, runtime or zeroizer was edited. Source-acquisition/parser failures and
the17 unresolved non-octet-message records remain visible in artifacts/fixtures.

The native component manifest includes only the two owned production translation
units and17 real public integer/RSA primitive units. `suite.c`, `guest.c`,
`synthetic_mem.c` and shared synthetic byte routines are test-only. Actual kernel
memory/fortify/guard and shared-zeroizer symbols remain integration requirements;
their presence in a synthetic test image is not kernel provider registration.

The shared AVF runtime keeps historical XTS labels and cookie. The separate RSA
markers, exact counters and image/console hashes identify the actual RSA code
executed. The positive suite including the4096-bit exponent took1.867seconds;
this aggregate duration is not a per-vector benchmark. Total lease use41.61s
included36.03s bounded memory admission. The native frame data is static; observed
guest high-water and source frame records do not qualify every native caller or
interrupt-stack context. No additional host/native algorithm replay was needed
to repair the isolated missing-runtime-provider link.
