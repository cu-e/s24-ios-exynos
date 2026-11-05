# AUDIOHOST-002: constructor lifetime followup

Date: 2026-11-05. Task: AUD-003. Owner: codex-team-audio-host-20261105-bh.

REV-013 identified an unstated constructor precondition: init → bind(epoch1) →
start → claim(slot0) → init(live storage) → bind(epoch1) → start → claim(slot0)
can produce identical old/new lease tokens. Retiring the old token can then
clear the new lease. Retain this review counterexample as unsupported-use
evidence, not a firmware replay exploit or a measured native backend result.

The intended API is a constructor, not a live reset. Document fresh or fully
retired storage, exclusive ownership, no live-state cloning/restoration/movement,
backend/callback/borrowed-view retirement and an external nonreused epoch
authority across reconstruction. Do not inspect uninitialized storage or change
the constructor's unconditional initialization behavior.

Before execution, plan one bounded commit-bound run of the existing source
oracle/sanitizer/ARM64 checks with the new lifecycle regression. The regression
must fully Stop, retire, CLOSED, fence and release the old epoch before init;
then use the caller's newer external epoch, deliberately reuse the same local
slot and serial, and show an old token is rejected without mutating the new
lease. Finish retiring/fencing/releasing the new instance. This is a synthetic
host ownership contract test; no actual backend, borrowed view or callback is
created, and no native DMA quiescence is measured.

Keep the original evidence immutable. Store new dated report/index/evidence in
owned paths. One compiler job, <=256 MiB sampled total owned RSS, 20-second
command deadlines, owned-session cleanup, no heavy build or device operations.
Leave task in_progress for coordinator/reviewer followup.
