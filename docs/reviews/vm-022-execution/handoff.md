# REV-039 final handoff: corrected four-tail source accepted

Original reviewer: `codex-review-link-executor-20261106-er`.
Reviewer branch/worktree: `team/rev-vm022-execution-er-20261106`,
`worktrees/rev-vm022-execution-er-20261106`.
Base main: `27352788619e594314a1a85a12f07e82fc279184`.
Review source commits: initial `74b5aa92cef44b7f279fb7f2e8841263d9c81c7c`,
focused correction controls `b2a06e4eb007532321296186337dc977bd84027f`.

Verdict: the exact corrected source and deterministic four-tail plan are ready
for serialized integration/common checks and a separately authorized future
tail experiment. This review grants no production allocation and qualifies no
actual tail object, archive, complete link, image, XNUP payload or guest runtime.
The task remains in progress until root/integrator acceptance and original-owner
closure. The old failed helper is not accepted by this verdict.

Accepted author boundary:

- Worktree `worktrees/vm-022-tail-cancellation-20261106`, commit
  `468cc06064085b1f75721b590cd871b57a7c0443`.
- Helper `tools/build/avf_guest_link_inputs.py`, SHA256
  `99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060`.
- Plan `artifacts/avf-guest-link-inputs/tail-fix-plan-2/execution-plan.json`, SHA256
  `6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569`.
- Reused exact accepted AF193 common executor SHA256
  `af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.

## Initial failure retained

REVTAIL-001 completed 80 independent checks in 4.672889 seconds; 78 passed and
two blockers prevented acceptance of original author commit `0d68b46` / helper
SHA256 `67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f`.
Actual default-SIGTERM controller behavior left its Python child alive in a new
session; the reviewer watchdog removed only that identified session and verified
cleanup. The raw-only constructor size guard also reached an unbounded read of
a sparse transformed file; an observer prevented allocating its contents.

[Initial findings](findings.md), [initial evidence](initial-evidence.json),
the original author worktree and all failed author harness attempts remain
unchanged. The later focused run additionally established that a valid sparse
257 MiB ARM64 object passes the preceding streaming parser; the verifier's own
read bound is necessary. No initial result was target production evidence.

## Correction and focused result

REVTAIL-002 completed 57 focused checks in 6.021840 seconds, all passing. It
reconstructed the new plan, streamed its exact source/tool/capsule bindings and
verified that the full original plan changes only its executor/output identity.
All four source recipes, flags, ordering and accepted namespace transitions
remain unchanged. This reuses the initial passed lineage/namespace/dependency/
object/approval/write-confinement checks instead of broad repeated builds.

The constructor correction opens both files with O_NOFOLLOW/O_NONBLOCK, checks
regular equal sizes at most 16 MiB, reads only expected-size-plus-one from actual
FDs, and closes the FD/path device/inode/size/mtime/ctime identities. Thirteen
independent controls exercised exact-size success and real post-fstat growth,
shrink, same-byte and changed-byte path replacement, symlink replacement and
retained-original-inode symlink replacement on both files. Actual reads ran;
none was mocked or bypassed. Each worker retained exactly four FDs before/after.
MemoryError would have failed, rather than satisfied, a rejection control.

The caller-owned cancellation context preserves AF193. It defers asynchronous
raises while the shared runner is active, injects pending cancellation through
an already caught budget work callback, and lets the shared finally finish.
It then propagates a dedicated non-pass cancellation with the actual command
record preserved. Reservation commit plus both ownership flags and final
release/evidence are also protected; prior handlers are restored last.

The three independent real-Python cancellation scenarios were first signal
during work, first signal at the actual shared final budget callback, and first
signal immediately after the real reservation-state os.replace but before
registered=True. Each received `[SIGTERM, SIGINT, SIGTERM, SIGINT, SIGTERM]`
across work/shared cleanup/caller cleanup. All wrote non-pass evidence, completed
the actual reservation release, restored handlers and left no live child.
No watchdog rescue was needed. Policy state used the real ProjectBudget API
against explicitly synthetic allocation/queue files under reviewer storage;
it grants no production authority and never changes MAIN's resource queue.

Primary current-image VmHWM was 33,050,624 bytes; maximum sampled combined new
owned RSS was 73,302,016 bytes. FD workers had 192 MiB address-space containment.
No compiler, assembler, archive/section tool, linker, packager, QEMU, phone action
or common repository check ran.

## Next gate

Integrators may publish only this exact accepted corrected source under the
shared integration lock and run fresh main common checks. Original VM-022 owner
then needs a new production experiment and exact root ProjectBudget allocation
binding reviewed source, plan, task/owner/worktree, slot and fresh output.
Genuine tail compilation may still fail; only measured actual dependency/object
receipts and constructor byte conversion can qualify that phase.

The later main-link executor is a separate author worktree and is not reviewed
here. Current 1080 object receipts, accepted provider/component capsules, real
direct link/archive/image validation and bounded XNUP remain separate gates.
The source-supported Mach-O -> XNUP -> matched AVF shim route is unchanged.
Actual runtime additionally requires its own qualified image and root QEMU lease.

The earlier APFS missing-flag diagnosis is superseded: genuine `-idirafter`
already exists, resource availability remains unresolved, and this review adds
no ad hoc include flag/header. No complete-kernel, private Apple ABI, iOS or S24
qualification follows from these authored fixtures or source-level results.

See [evidence.json](evidence.json) for actual commands, times, 162 streamed
artifact bindings, exact source hashes, signal/cleanup observations and limits.
