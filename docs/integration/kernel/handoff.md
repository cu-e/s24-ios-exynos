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

The common path has stable 4 GiB admission before publication and check,
two-job configuration, live sampled aggregate-RSS stopping at 2 GiB, a
180-second deadline and owned-session cleanup through the unchanged supervisor.
A sampled RSS threshold is not a hard cgroup cap. The initial audit consumed no
resource lease; the first real root-leased integration is recorded below.

Next critical path: root-approved independent review of this gate, then a frozen
VM-008 source/capsule review and candidate. VM-009 executor and ten disjoint
guest object shards prepare source contracts independently; no compile until
VM-008 and runner acceptance plus a root heavy-job lease. Root supplied a
1,080-object graph and machine selectors; those source/artifact inputs remain
read-only. Root's new executor/reviewer tasks and one-QEMU queue remain the
coordination authority. This integrator does not claim original component work.

Pending: independent gate review, concrete root approval, first leased guarded
publication/common check, and actual VM-008 acceptance. Task remains in progress.

## First publication and virtual-address correction

Root accepted the gate and REV-024, then approved exact plan SHA256
`419209ae1c71bdc783c9b7eb05507364f3e312a5971c8f79f99e1c62076adaea`.
The shared gate published MAIN from `aac27cf` to exact candidate
`4bea9b59d1d24c2f7f53f4028769b6e420be556e`, retaining the unrelated dirty ledger.
The common test phase ran 153 tests and failed one JVM startup; the overall make
exit was 2, with no timeout/pressure stop. Peak owned RSS was 180,826,112 bytes
and no owned PIDs survived. The failed capsule is
`artifacts/integration-gate/gate-publication-1/evidence.json` in this worktree.
The matching heavy lease was released and the published HEAD retained.

Root's `artifacts/team-coordination/20261106-team/javac-as-diagnostic.json`
establishes the cause: `javac -version` cannot reserve 1,073,741,824 bytes of
compressed class space under the additional 2 GiB virtual-address cap and exits
1 with empty stderr; without that cap it exits 0 (`javac 25.0.1`). The policy
limits aggregate owned RSS, not virtual reservations. The minimal correction
removes only the gate's AS override, retaining all RSS/job/pressure/deadline and
cleanup controls. The evidence field is now null for no gate AS override.
No test is skipped and no JVM options are added. Independent review of this
exact delta and a fresh root-approved plan precede the justified common rerun.

VM-008 historical source/capsules remain bound to their original frozen
measurement entrypoint. A prospective three-sample admission guard is a separate
component; it must not relabel historical measurements or invalidate their
unchanged generated namespace. Future execution always needs stable three
samples and an admitted root lease. VM-009 verification and execution contracts
must distinguish those historical and prospective roles explicitly.
