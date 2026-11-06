# REV-043 handoff

Owner `codex-review-guest-runtime-20261106-ex`; actual atomic claim REV-043.
Worktree `worktrees/rev-vm023-ex-20261106`, branch `team/rev-vm023-ex-20261106`.
Scope is exclusively `docs/reviews/vm-023`. The producer remains DE; no other
review/source task was claimed or changed.

Frozen VM-023 HEAD `8eefa50abe26ec9e8e8368fea82bc06465841441` and implementation
`0e44b04827b4c3258ed0f7bd724d03acc728bf26` were inspected. Maintained producer
evidence matches `feaf78a5050c239f144a1ab56e5bfd481c660a3d2e0347a5c33a3088ab48ce18`.
Read procedure.md for exact bounded controls and prohibited execution boundaries.

Initial source review confirms the intended distinction: positive existing
driver `-###` selects the exact archive once, while an absent resource root
omits it with exit zero. All 47 external names remain explicitly unresolved.
No full link/runtime/header/private ABI acceptance follows from this lookup.

REVVM023-001 was registered in MAIN before the controls. Review source commits
are `a0063ef` and `f1bceb4743b6b0ef9289ea1a94eb485abc299d36`; the latter adopts
the actual row-list producer artifact-index schema before the first control run.
The pre-control schema inspection's AttributeError is retained as a reviewer
diagnostic. It is not a producer finding, and no control attempt was overwritten.

Actual `runs/review-001/report.json` outcome PASS, exit 0: 10,858 assertions,
624 source/tool/output file bindings rechecked before/after, all 287 member and
source/object/recipe witnesses, ten rejection controls, and exact 47 unresolved
external imports. Raw report SHA256:
`79c227af65fe021e02fc85e08522197e2b1cc5c742fe892ede8b3a5a93a67fcd`.
Elapsed 2.465497 seconds, current-image VmHWM 84,918,272 bytes, no child or tool
execution. Owned binary control copies remain locally preserved under the run's
ignored cases directory; their hashes and bounded mutations are in the report.

Verdict: PASS within the archive/source/recipe and existing lookup scope, with
no actionable P0/P1/P2 finding. `review.md` explains the evidence and limits;
`evidence.json` binds the exact tested source, command, reports, controls, source
freeze and cleanup/resource facts. No compiler-driver/build/corpus rerun,
archive/link/QEMU/common or allocation occurred. The existing missing-root
driver command still exits zero while omitting the archive, and the link-only
resource root is not compiler-header qualification. Old graph identities and
unresolved imports remain explicit. Producer DE remains sole implementation
writer and source-task closer; VM-015 and VM-042 remain untouched.

Next: INT-002/root and designated publisher inspect the exact docs-only freeze,
integrate on current MAIN and run common checks under the shared integration
lock. Keep REV-043 in progress until explicit root acceptance authorizes its
original reviewer owner to close it. No further control, driver or corpus run
is needed absent a concrete review concern.
