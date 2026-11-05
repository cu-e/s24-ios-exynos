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

No compiler or guest launched by this reviewer. No device operations. Next:
register and execute independent read-only source/Mach-O/hash audit, review final
qualified capsule when available, record exact commands/exits/hashes and scoped
review commit. Leave task in progress for coordinator acceptance.
