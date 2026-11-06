# REVTAIL-002: focused correction challenge

Task REV-039, original reviewer `codex-review-link-executor-20261106-er`.
The initial failed freeze and REVTAIL-001 results remain immutable.
Execution requires a separately supplied corrected author commit, helper path,
SHA256, exact plan/capsule and correction API. Pin those actual inputs in the
control report before testing; a moving author worktree is inadmissible.

Frozen correction supplied before this experiment's registration:
`worktrees/vm-022-tail-cancellation-20261106`, commit
`468cc06064085b1f75721b590cd871b57a7c0443`, helper SHA256
`99d8db30fcfb3c510dadcecf1fb89121ed5062d3af3379442ac2e905c303b060`.
The exact `tail-fix-plan-2/execution-plan.json` SHA256 is
`6b01e7c535176ffe41f83aca2bf4eded2a75e9af715e260bf8042232c9ba3569`.
Correction APIs are `constructor_snapshots`, `owned_cancellation`,
`CancellationState.cleanup/command/check` and `run_owned_child`.

Hypothesis: the corrected caller converts cancellation into a non-pass unwind
that retains finite child cleanup/evidence/budget release, even when additional
SIGTERM/SIGINT arrives during cleanup; the corrected constructor verifier reads
actual bounded FD snapshots and rejects post-stat growth or path replacement.

Only these changes and their direct lineage are retested. Existing passed
source/argv/namespace/approval findings are reused when their exact bytes remain
unchanged. A new helper/plan/output identity must be explicitly rebound; no
tail or full-link production is authorized by a review fixture.

Filesystem controls use real authored ARM64 MH_OBJECT bytes in reviewer-owned
temporary files. Include a valid large sparse Mach-O to test the preceding
streaming parser's size behavior. For the corrected verifier, trigger real
growth/replacement immediately after its actual stat/fstat or open boundary,
then let its actual read execute. An observer may wrap a stat/open boundary to
schedule the real filesystem mutation, but must call the real operation and
must not mock, replace, suppress or shortcut any read. Check exact-size success,
extra bytes, shrink, symlink swap, changed inode/content, same-length path swap,
and growth beyond the limit. A bounded child memory cap contains any unsafe
read; MemoryError is a failed bounded-read claim, never a successful rejection.

Cancellation controls use the corrected caller's actual cancellation context
with exact AF193 run_child and real Python-only children, never a production
tool. Include an owned child that ignores SIGTERM to create a measurable cleanup
interval; send first cancellation during work, then additional SIGTERM/SIGINT
during cleanup. Verify finite exit, no surviving owned process, no pass outcome,
recorded cancellation and restored previous handlers. Where the correction's
API permits, use actual ProjectBudget reserve/release against a clearly marked
synthetic allocation/queue under reviewer-owned temporary storage; no MAIN
resource queue or real reservation is changed.

Each child/control deadline is at most 8 seconds; whole command deadline 120
seconds. Track actual controller/child current-image RSS/HWM, below 256 MiB new
owned RSS, and preserve every failed/inconclusive attempt. All hashes stream.
Use LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 before Python starts.

No compiler, assembler, linker, archive/section tool, packager, QEMU, phone action,
common repository check or author edit is permitted. The parent watchdog may
remove only its independently identified reviewer-owned sessions if the tested
cleanup fails; that rescue remains a finding, not a successful control.
