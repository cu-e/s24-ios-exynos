# REV-041 final corrected-core handoff

Original owner `codex-review-link-main-20261106-eu`; review branch
`team/rev-vm022-link-eu-20261106`, worktree
`worktrees/rev-vm022-link-eu-20261106`. Maintained scope remains only
`docs/reviews/vm-022-link`.

Read `final-review.md` and `final-evidence.json` for the final source-only pass.
Author source is immutable commit6bf9c0eef728f24c9bb76d040b98d3631edeecf0,
helper9f80e32305ce84e33ab27bcf37d589465a97c2d03c5eb6830fd3540f204400c5.
Final independent controls: 76/76 PASS, CLI0, actual FD identities3→3,
current-image HWM46,612,480B. Both real partial-iterator SQLite leaks and escaped
reads are fixed; primary failures survive complete teardown. Unfinished stage
evidence is schema-valid inconclusive with complete product false.

Keep `evidence.json`/README.md and `correction-evidence-1.json`/
`correction-findings-1.md` as immutable failed history. Final raw control report
`artifacts/rev-vm022-link/cursors-1/evidence.json` has SHA256
`d5a1df14447665158e83bfe126c20f70c41a8040385563726e9178fff4b53610`.
Reproduction `cursors.py` has SHA256
`1a9bda73c9a9d9b7e5bb659378c59c13d0f542a5112c7c57de7f6883b6cb5456`.
Only the focused changed cursor/schema surface was run; no prior full matrix,
700k benchmark, target command, productive allocation or common check replay.

Acceptance is limited to the corrected core source. Productive046 profile and
complete-product pins remain empty. Runtime VM-047/reviewer FD047 and allocator
VM-048/reviewer FE048 proceed separately; actual qualified module contracts,
product source-to-link proof, genuine image/package and boot are not supplied by
this report. No phone operation is authorized.

INT002/root own publication and common checks after active wave29; this worker
does not publish or run them. The next dependency is their exact corrected-source
and review acceptance receipt. Original EU may then close REV-041 once when
explicitly instructed. Original REV-039 remains done and unchanged.
