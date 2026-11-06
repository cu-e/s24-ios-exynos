# REV-044 independent VM-031 review procedure

Reviewer: `codex-review-guest-crypto-20261106-ey`, separate worktree
`worktrees/rev-vm031-ey-20261106`, branch `team/rev-vm031-ey-20261106`, base
`b000b0a`. The only reserved path is `docs/reviews/vm-031`. Original DM remains
the sole producer and eventual VM031 closer. VM018 and VM043 are untouched.

Review the exact producer head
`3d903f8173acf81dc8b2b21eb1b620c34567a38c` and qualifier
`9fc0a5b3ced553d801481e5e1984b94d703daf89`, including all nine scoped ancestor
commits since `aac27cf`. Qualifier tool SHA256 is
`a50048f526c3fe9998495152a796e32e86eef14f8e32bd2f7267bdf076297e1f`;
maintained evidence SHA256 is
`8fb6d01fdb88653a9d3aebcd4ffadf6c7f425a0ea380de145f8d2a31651560e9`.
Read its original handoff, procedure, source inputs, unchanged raw success,
retained non-UTF8 failure and narrow discovery history before testing.

Prospectively register `REV044CTRL-001`, host-test, before running focused
controls. The stdlib harness has a 90 second alarm, 256 MiB address-space/current
image limit and three one-second MemAvailable admission samples >=4 GiB. It
starts no compiler, assembler, preprocessor, generator, archive, section tool,
linker, QEMU, device, network operation or common check. Read-only local Git
queries use no-lazy-fetch/no-optional-lock guards and finite timeouts.

Reuse the frozen 3,842-file scan receipt. Do not call the producer's `audit` or
`main`, enumerate the source tree, or rescan the corpus. Independently verify the
56-field declaration, 34 static assignments, deferred SHA256 and 21 unsupported
static-zero fields against the actual narrow source. Verify all 89 published
demand witnesses by their named source/hash/line and membership metadata; this
does not assert completeness outside the reused receipt. Verify the exact 32
reported crypto/startup source/configuration/argv rows against the immutable
1080-row graph, reusing the producer's complete-source hashing result.

Assess provider EARLY_BOOT/FIRST versus kmem EARLY_BOOT/MIDDLE, actual startup
sort/invoke source, selftest/CE/deferred SHA/publication/PRNG order, registration
pointer retention, competing-provider return and skipped PRNG branch. Preserve
single-generator initgen no-op, discarded reseed status and source-only entropy/
security boundaries. Do not add a native039 or allcrypto prerequisite.

Exercise only AST-extracted frozen parser/hash/text helper functions on bounded
owned temporary copies. Controls cover malformed/duplicate fields, changed
source bytes, lossless non-UTF8 reads, comment line preservation, inactive text,
string-literal lexical limitations and the fixed-source hash boundary around
synthetic duplicate designators. Positive parser acceptance of an unbound
synthetic variant is a parser limitation, not a bypass of the pinned audit.
Never mutate producer or shared source bytes. Remove temporary copies while
retaining their hashes, case outcomes and any failed/inconclusive attempt.

Deliver docs-only exact commits, review verdict, evidence and handoff to INT002
and root. Concrete findings go through them for factual relay to historical DM;
no author acknowledgement is presumed. Generated sources outside the composed
corpus, full TU/extraction/reachability/registration runtime/entropy/security/ABI
remain unmeasured. Do not close REV044 before root-authorized current-HEAD
integration/common acceptance, and never close VM031 under another owner.
