# KRN-035 working handoff

Original owner `codex-team-crypto-rsa-20261105-bv`, branch/worktree
`team/krn-035-20261105` / `worktrees/krn-035-20261105`.
Claim was atomic after KRN-029 done and all KRN-031..034 claimed; no other task
was taken. Baseline `0ff6a7c`. Scope only crypto/rsa and docs/crypto-rsa.

RSACOMP-001..003 were planned before their executable checks. The current
`host-build-session3` capsule has actual host491-vector/782,365-assertion ASan/UBSan
success, genuine unchanged selected-caller dispatch, both deliberate sanitizer
faults, full native typed component objects and synthetic CPU objects. It remains
an overall failed capsule because CPU linking exposed missing `___memset_chk`.
No QEMU run has occurred. Do not describe source replay/tool-version children as
no execution: the first memory-gated attempt completed those stages, then stopped
before compilation. The second attempt retained a host compiler-macro issue;
Linux lacked Darwin's `__enum_decl`. The exact canonical BSD compiler-macro block
is now extracted only for host compilation, with no replacement SDK records;
the genuine native header/profile is unchanged.

Source/interface findings: actual selected `rsa_make_pub` writes64 units before
the callback; the genuine container is1584 bytes/alignment8, maximum4096-bit N/E.
Big-endian input is explicit in the genuine constructor declaration. Selected
`chunklist.c` byteswaps its original inputs before that wrapper, passes exponent
65537 and a SHA256 DER OID, and checks both status and bool-valid. This does not
authorize silently byteswapping inside the callback a second time.

Implement a transactional local genuine rsa_pub_ctx then copy its own m/e limbs
and actual bit length into the caller's fixed64-unit profile. Wrong n must be
rejected before macro-based offsets; errors preserve destination. Separate
status/bool semantics and invalid output-alias preconditions remain explicit.
The coordinator approved this selected profile, not general cczp methods or
opaque funcs/Montgomery compatibility. Never invent a cczp_funcs record.

Pinned BearSSL i31 public arithmetic and PKCS1 unpadding operate on transient
big-endian views and return validity plus recovered digest. Its pad2 scratch
buffer is43 bytes; DER-to-length-prefixed OID conversion must cap payload32.
Genuine NULL-OID raw mode is supported by the declaration. Pointer readability
is a caller premise because the selected signature has no OID-buffer length.
Use the accepted XTS zeroizer/shared runtime read-only; no duplicate definitions.

Resource gate: check actual MemAvailable before each bounded process and wait
at most25seconds without starting a new one when below4GiB. One compiler job
at most256MiB, aggregate2GiB. QEMU additionally needs explicit exclusive root
lease for256MiB. Do not alter unrelated processes, swap or caches.

All33 consumed BearSSL files are independently checked against canonical Git
blob identities, including complete headers and every arithmetic source body.
The15 overlapping older catalog entries match. No shared source/cache changed.
The official NIST archive SHA256 is
`8405aeb3572a4f98ed4b1a3ccb3f2f49e725462dd28ec4759d6a15d88855d19c`.
The481 supported primary cases and10 independent cases are public verification
inputs.17 records in `SigVer15_186-3.rsp` have unresolved odd-nibble message
representation and are excluded with exact ordinals; they are not declared
malformed. An integer signature S with511 hex digits is canonicalized using
RFC8017 I2OSP; its published positive result is independently verified. Public
integer and OpenSSL controls include a4096-bit modulus and4096-bit exponent.

Actual native layout is `[1584,8,64,8,24,24,1568,24]`. All production stack usage
records are static: constructor1664, verifier1280, i31 public2272, PKCS verifier592,
unpad160, modpow176 bytes, plus smaller callees. These are component measurements,
not a complete native caller-stack proof. The observed build process group peak
was96,440,320 bytes. CPU stack high-water/finite execution remains pending.

The coordinator approved an RSA-owned CPU-only real `__memset_chk`, excluded from
production manifests. `finish-session1` stopped on the memory gate before any
new bounded child; its immutable original and main-path failure wrapper remain.
`finish-session2` reused frozen successful objects, passed8,304 independent helper
checks (allowed/zero/int-byte, two actual excess traps before shared-buffer writes,
both children reaped), and linked actual normal/spin payloads. No accepted shared
runtime/memory/zeroizer source was modified.19 genuine selected headers and all
consumed accepted XTS dependencies were checked against complete qualified bytes.

RSACOMP-006 / `cpu-session1` executed under the explicit exclusive root lease:
all491 vectors and782,365 checks passed on real ARM CPU emulation. Observed stack
was10,604 bytes; the positive guest took1.867seconds, including the full4096-bit
exponent case. This is an aggregate suite duration, not a per-vector benchmark.
Wrong-cookie rejected before RSA, an actual positive signature byte mutation
produced RSA FAIL and PSCI shutdown, and the owned spin timed out at3seconds.
All four process groups ended with zero owned processes. The lease was released
immediately. Total run41.61seconds included36.03seconds finite memory admission.

Next: frozen Git/source-byte publication audit, scoped commits and independent
coordinator review/integration/common checks. Keep in_progress until accepted.
No native, provider/private-ABI/FIPS/side-channel qualification is established.
This task performs no heavy kernel relink. See the component README for exact
fixed-container, OID, status/alias and unrelated-cczp limitations.
