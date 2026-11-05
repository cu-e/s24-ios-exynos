# REV-014 handoff — 2026-11-05

Owner `codex-team-review-xts-20261105-bp`.
Branch/worktree `team/rev-xts-20261105` / `worktrees/rev-xts-20261105`.
Base main 220d003; owned paths only `docs/reviews/krn-029`.
Frozen candidate 396517f55102a2ded50245b053684dfffb6c2ec8 plus
7b7607b1f907d2e51dbb55766de9cdee772c0842, metadata
de3c63326c1e89c232bfd018a4c940b13179766e.

Bounded conclusion: no P0/P1/P2 finding within the stated descriptor/test
contract. README records source-line assessment and distinctions between crypt
admission preservation, initializer error clearing and rejected input aliases.
No implementation/shared inputs/provider/original ownership changed. REV-014
remains in progress pending coordinator inspection/common-check/acceptance.

XTSREV-001 was registered before the actual command:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 docs/reviews/krn-029/reproduce.py review1
```

Exit 0; UTC `2026-11-05T17:22:04.570009+00:00`; six groups / 31 commands.
All 125 capsule artifacts, owned source/dependency hashes and genuine selected
ccmode blobs match. Retained upstream Mbed archive/member bytes/license and the
sole common.h include-only port patch match. Independent NIST parsing gives 1200
full raw-IV records, 600 each direction, with 800 partial/2000 sequence-format
exclusions; fresh actual OpenSSL EVP replay regenerates the identical 1220 corpus.
The distro OpenSSL binary rebuild is not claimed.

Replayed original ASan+UBSan host suite: 40,708 checks / 1220 records. Independent
boundary probe: 12,349 checks, every vector both directions plus key/tweak byte-
offset input/output aliases, partial-overlap directions, touching ranges, rekey,
const copies, explicit clearing and count/error preservation. Independent real
synthetic memory helpers: 132,096 overlap/compare cases plus byte/fortify bounds;
isolated excessive fortify copy exits -4 (SIGILL), as expected.

All four existing immutable ARM payloads replayed sequentially with unchanged
qualified shim/QEMU and 256 MiB RAM. Positive actual entry/bootargs/handoff,
40,703 checks, failure_line0 and natural PSCI exit; wrong-cookie rejects;
corrupt-vector fails algorithm without PASS and naturally exits; spin reaches
the two-second timeout and owned cleanup. First three console digests exactly
match originals. The host-only five maximum-unit assertions explain count delta.
No new ARM/backend/kernel build or provider/XNU execution.

Actual process VmHWM 27,728 KiB; sampled total owned peak 114,576 KiB. One compiler
at a time <=256 MiB, one guest at a time <=512 MiB total, finite owned-session
cleanup; all sessions quiescent afterward. Root's later MemAvailable-floor note
arrived after the bounded run had completed. Completion-time read-only probe
showed 8,347,492 KiB; no further runtime test was started or repeated.

Evidence:
`worktrees/rev-xts-20261105/artifacts/rev-krn-029/review1/evidence.json`

SHA256: `44af27b7a56a81298f2195a76b5c199619c03758e333c0562da511e43d2e08c6`.

Report SHA256:
`88c8002e5a9b3e63f31a0d90458038927e4830a55d22bb343f1be5c54605e92e`.

Exact commands/exits, stdout/stderr, hashes, corpus directions, actual lifecycle/
memory markers, guest conditional acceptance and resources are retained there.
Generated outputs stay local/untracked. Committed files contain reviewer prose
and code only, with no SDK or redistributed binary artifact.

Next: coordinator inspect/accept review commit, run the upcoming main common
check and decide completion. Keep software ROM-table side-channel/FIPS limits,
caller lifetime/access/serialization and initializer-clearing rules, ignored
kernel-wrapper xts return, provider/XNU/privateApple/fullcrypto/native gates.
No additional tests or implementation change is requested by this review.
