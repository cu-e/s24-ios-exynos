# INT-002 initial gate handoff

Owner `codex-integrator-kernel-20261106-cm`; primary ledger claim verified INT-002;
worktree/branch `worktrees/int-kernel-20261106` / `team/int-kernel-20261106`, base
`aac27cfbc0d71b34eda33ddf366c72427507ae0b`. Scope is
`tools/integration_gate.py` and `docs/integration/kernel`. The permanent role
continues after tool review; this is not completion of component acceptance.

Both integrators agreed on primary `state/.integration.lock`, disjoint from the
short-lived lab lock. Platform integrator `/root/review_esim` uses this shared
tool rather than duplicating it. Candidate preparation occurs outside the lock;
the frozen exact base must still match after acquiring it. Publish only the
concrete root-approved plan by fast-forward, preserving validated candidate SHAs.
Refresh candidate/plan/approval after any main advance. Never commit worktree
registry copies or replace the stable lock inode. Preserve unrelated live dirty
primary registry/views and reject staged or intersecting changes.

The tool checks full source/candidate identities, ordered commits, exact changed
paths, source-to-candidate raw binary/full-index patch equality, clean candidate,
and streamed review/evidence/dependency capsule SHA256 bindings. It rejects
registry/planning/lock changes, candidate source collisions including ignored
data, and symlink parents. Plans/receipts are bounded snapshots of the exact
hashed JSON bytes. The root receipt binds the exact plan and resource lease;
it is cooperative authorization bookkeeping, not authentication.

Initial prospective `INTGATE-001` was registered and verified before tests.
Light tests use disposable Git repositories and real competing processes. The
6-test draft, expanded 8-test draft and strengthened 11-test draft all passed.
Peer findings from the platform integrator were resolved before freezing:
unrelated source labels, lock replacement, aggregate monitoring and admission
before publication. The final source also explicitly disables Git textconv for
raw patch comparisons. A final 11-test run binds that frozen production source.
Each case preserves actual CLI command, exit, stdout/stderr and gate report in
the local light-run artifact directory; all earlier successful drafts remain.

Actual temporary fast-forwards verify exact candidate HEAD and dirty ledger
preservation. A tiny substituted check callback verifies that another open file
description cannot acquire the lock; a synthetic callback failure proves the
published HEAD is retained with failure evidence and no implicit rollback. These
tests do not execute the real admission/supervisor/common-check path and do not
establish real-host publication qualification. No actual primary Git publication,
project `make check`, compiler, QEMU, phone or ADB operation has occurred here.

The future common path has stable 4 GiB admission before publication and check,
two-job configuration, a 2 GiB per-process address-space cap plus live sampled
aggregate-RSS stopping, a 180-second deadline and owned-session cleanup through
the unchanged existing supervisor. This path needs independent review and the
first explicitly leased real integration. A sampled RSS threshold is not a hard
cgroup cap. No resource lease is invented or consumed by the initial audit.

Next critical path: root-approved independent review of this gate, then a frozen
VM-008 source/capsule review and candidate. VM-009 executor and ten disjoint
guest object shards prepare source contracts independently; no compile until
VM-008 and runner acceptance plus a root heavy-job lease. Root supplied a
1,080-object graph and machine selectors; those source/artifact inputs remain
read-only. Root's new executor/reviewer tasks and one-QEMU queue remain the
coordination authority. This integrator does not claim original component work.

Pending: independent gate review, concrete root approval, first leased guarded
publication/common check, and actual VM-008 acceptance. Task remains in progress.
