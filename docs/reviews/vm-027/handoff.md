# REV-029 handoff — 2026-11-06

Owner codex-review-boot-inputs-20261106-dv atomically claimed REV-029 after the
first no-eligible result while registration was pending. REV-027/028 owners stay
unchanged. Separate WT worktrees/rev-boot-dv-20261106, branch
team/rev-boot-dv-20261106, base fd201707ac8c24ffcf9bd44e13ba2205fd7e2ea0.
Only docs/reviews/vm-027 may change. Root and INT-002 were notified.

Review PASS against exact final producer 250bce50945ab0c79235dabcd0bd355a44623d0d.
Review source frozen a5c287f156389c23aafb960dfb85fd2a258553b1; see verdict.md and
evidence.json. Session2: 204 checks, 66 input paths, 14 pinned Git reads; independent
reader reconstructed all 12540 bytes/14 nodes/84 properties; all 38 selected
preflight checks agree. Thirty actual-derived malformed trees reject, unknown
well-formed property is preserved. Public CLI exits0 actual, exits2 missing
required RAMDisk and separate input FDT. Four bounded Python jobs, maximum
47,693,824 bytes aggregate RSS, no surviving children; no compiler/guest/common.

Actual dump SHA256 afa048b454b658399636030abe71bc706665fb722564459b93e75609f7d6d491.
Producer capture capsule SHA256 b92c3e281105c3bd76ad7ff54311028830500c038b3e706a2fc68b4f965e85d2.
Source/actual launch/QMP stop/save/quit/cleanup bindings independently checked.
Session1 failure is retained: locally absent upstream non-code notice blob;
corrected reviewer identity check binds cached bytes to the actual pinned tree
entry without fetching. No producer source or artifact changed.

Source contract is deliberately the selected shim writer/profile, not a universal
Apple DT ABI. Historical source-only evidence remains inconclusive; actual capture
observed the shim and unchanged synthetic spin payload, no XNU/PID1 or phone.
Actual tree lacks RAMDisk. No blocking finding in the selected contract. Next:
root acceptance and serialized integration/common gate. Keep original dv claim
in progress; do not close producer/other reviewers' claims. Failed attempt,
historical source-only inconclusive and rejected draft capture plan remain bound.
