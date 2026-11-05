# REV-017 handoff — 2026-11-05

Owner: `codex-team-review-kernel-xts-20261105-ca`; branch
`team/rev-kernel-xts-20261105`; worktree
`worktrees/rev-kernel-xts-20261105`, created from main `0ce4faad573522e1f19252d7fe44b328249b6f4f`.
Only `docs/reviews/krn-031` is reserved/edited. Shared registry is main.

Successfully atomically claimed REV-017. Read AGENTS.md, README.md,
docs/agent-workflow.md, docs/planning.md, board and the task card. Read frozen
helper, provider/caller patches, accepted adapter contracts, host publication
fixture, high-VA caller fixture and builder. No source defect identified so far;
source review is ongoing and is not final acceptance.

Verified named followup `b87957bfd89d8ab82162e546d9c9eee3c018078f`
changes only two builder expressions to scope pre-mapping spin proof correctly.
It does not change helper/provider/caller/fixture implementation. Existing
frozen-native1 and frozen-native2 are failures and cannot complete the review.
The latter currently fails the incompatible-callback rejection check. Final
qualified native/host/guest capsule remains pending from implementation owner.

Registered REVKXTS-001 before tests. Review-only checkpoint commit `f9c06a6`
preserves source review, auditor snapshot and raw evidence. Exact checkpoint
invocation is recorded in checkpoint-evidence.json: Python source auditor exit 0,
75 checks, 50 bound inputs and 21 successful pinned Git commands. The separate
frozen-native2 admission control exits 1 as expected; it cannot be accepted.
Checkpoint outcome is deliberately inconclusive and final_acceptance false.

Named followup `e3b6b7da1217a716b0a2b152207b61ab73c749cf` was read in full.
The selected compiler had emitted a separate strict function-pointer diagnostic
as a warning with exit 0. Followup strengthens the actual negative and unchanged
helper positive, and permits retained-manifest image lookup. No production glue,
patch or fixture changes. strict-native1 stopped before any command on the 4GiB
floor; do not turn this into a compiler/algorithm failure or acceptance.

No compiler or guest launched by this reviewer. No device operations. `make check`
invokes C/C++/javac suites and is deferred to coordinator resource scheduling.
Further named followups reviewed: `0551ab0279adbc7e1f0bae3e698f4857865c4888`
binds complete caller/publication check counts; `376a2f3f639d88ab954d9807220854779e995dc8`
adds finite stable memory admission (three samples and final >=4GiB, <=45s per
command/180s total). Only builder/qualification procedure changed. No production
glue, caller/provider patches or fixture changed.

Strict-native3 now passes exactly two selected-compiler jobs. Independent
native-audit-function-bound.json passes 6016 checks, 4500 bound inputs and 27 Git
commands. It independently verifies exact strengthened command diffs, genuine
source reconstruction, all 982 original source/object and 3156 dependency hashes,
actual 34+2 relocations/deferred SHA256/19 unsupported zeros, bounded initializer
BL order, typed descriptors/layout/imports, runtime archive and 37 export demands,
real gated/mismatch factory copies, 105+5 host controls and cleanup. Reviewer's
earlier unlisted-followup and overbroad BL-scan failures are preserved; corrected
reader bounds the actual function extent rather than counting later functions.
They are not production findings. Tested reader snapshot is preserved separately.

Final measured milestone: full-audit.json PASS, 6198 checks / 4545 bound inputs /
30 actual pinned Git commands. Exact final invocation, stdout/stderr, exit 0 and
Python executable hash are preserved in full-audit-command.json and associated
files. The immutable final-auditor-snapshot.py matches the tested source hash.
Recommendation is acceptance of bounded component integration, with no blocking
production finding. Task remains in progress for coordinator acceptance.

Final guest proof is the immutable final-guest1 three-case prefix, exact
mapping-reinspection1 and final-pending-guest1 five-case continuation, all bound
to strict-native3. Positive is 1220 vectors / 7350 checks. Native uses 34 original
slots plus two XTS, deferred SHA256 and 19 unsupported slots. Real host controls
remain 105+5 checks. The independent mapping_audit.py/read-only snapshot proves
normal PA43004d38 versus shifted PA42e04d38 outside the loaded image, exact slot4,
ESR02000000, linked ELR and FAR0 plus pinned shim handler -> die -> PSCI path.
The original failed aggregate remains failed. No guest rerun by this reviewer.

Named final followup `9dc0c9f92c26373263ed17439eb44d0f2ea2268d` changes only
qualification code/procedure: precise observed mapping classification, stronger
specific negative check counts/lines, named five-case continuation, and 300s
whole-batch deadline. Final continuation captures that exact clean builder hash.
All XNUP kernels/cookies, sole corrupted ciphertext byte, real addresses/TCR,
specific negative source lines/check counts, resources and cleanup are verified.
Observed native RSS <=155.911MiB, strict jobs <=79.075MiB and guests <=70.852MiB;
all owned process lists are empty after execution.

Final owner tip `a84ac4ec571fd36b1d435036d453fa68982d88b3` is metadata-only.
Final-binding.json PASS binds capsule
`b5f772163a286e2586d1a76f38640ca8e3b75d38a681d3b1b09198e91e6e2a47`,
all raw reports, exact 985-object manifest (982 base/2 replacements/3 additions),
runtime/export gates and primary source/license hashes to the independent audit.
Its first schema-comparison failure is retained, then corrected to compare the
complete export path/hash/entries record. No production finding.

Review evidence is evidence.json; recommendation is accept the bounded component
integration. No new tests/compiles/guests are needed. Root explicitly schedules
kernel common checks after implementation/review integration; there is no
circular wait and no reviewer compiler. Do not conflate those pending consolidated
checks with the passing independent review. Record REVKXTS-001, report the final
scoped review commit, and leave REV-017 in progress for root acceptance.
