# Initial independent review: changes required

Reviewer `codex-review-link-executor-20261106-er`, task REV-039.
Frozen author commit `0d68b46a4b7dd3f2de16962fdbb3806843751d82`, helper
SHA256 `67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f`.

The initial independently registered light run completed 80 checks in
4.672889 seconds, with current-image VmHWM 32,550,912 bytes. Seventy-eight
checks passed; two counterexamples prevent acceptance of this freeze for an
actual tail lease. No production compiler, assembler, archiver, linker,
section tool, packager, QEMU or guest ran. All identified reviewer-owned child
processes were removed and cleanup was independently verified.

## 1. Caller cancellation does not reach owned child cleanup

Frozen `execute_tails()` at lines 897–990 installs no signal handler, and AF193
`run_child()` at lines 850–912 creates a distinct child session. Its `finally`
cleanup runs when Python unwinds, including SIGINT's default KeyboardInterrupt,
but default SIGTERM terminates the controller without unwinding.

The review's real Python-only controller called exact accepted AF193
`run_child()` with the same default signal policy. SIGTERM returned controller
exit -15 and left the recorded child alive in its separate owned session.
The reviewer watchdog verified that child's start identity, signaled only that
recorded session, and verified no live survivor. SIGINT and the deadline control
with an independent child process group cleaned themselves up successfully.
This tests the actual API/caller cancellation boundary; it is not a measured
production `execute_tails()` invocation or a target-tool execution.

The caller needs a scoped cancellation boundary spanning the reserved phase.
Cancellation must unwind through `run_child` cleanup and the executor's
evidence/budget-release finally, produce a non-pass outcome, and restore prior
signal handlers. The already accepted AF193 bytes must remain unchanged.
Hard SIGKILL is inherently outside a cooperative Python cancellation guarantee.

## 2. Transformed constructor bytes are read without a size bound

Frozen `verify_constructor_transform()` at lines 872–894 bounds the raw object
to 16 MiB, but calls `transformed.read_bytes()` without checking its length.
The preceding streaming Mach-O validation accepts bounded load commands without
limiting the whole file length. An oversized output can therefore request an
unbounded controller allocation after the target child has exited.

A real sparse 257 MiB transformed fixture reached that read. An observer on
that exact path prevented allocating its contents and recorded the attempted
size. The raw fixture was a small valid authored ARM64 MH_OBJECT. Require the
transformed file to have the exact same bounded length before reading it, then
retain the existing full-byte comparison and genuine source-defined rename.

## Passed boundaries and remaining gates

Exact helper/plan/capsule/source/tool bytes, deterministic plan reconstruction,
all four argv/source/output positions, original owner/worktree/experiment
refusal, changed-plan refusal, namespace shadow/change/delete checks, escaped
compiler dependency parsing, ARM64 object extents, full-width constructor
conversion, debug-section exclusion, caller approval, stale allocation and
finite budget-lock contention passed. Actual Python success/failure/deadline
and Landlock write confinement controls also passed.

The root allocation used by the policy controls was explicitly synthetic and
confined to reviewer temporary storage. It grants no real production lease.
The source implements only four tails and constructor conversion. Main-link,
all 1080 current object/provider admission, archive/image validation, XNUP and
guest execution remain separate unimplemented or unmeasured phases.

The author acknowledged both findings and will provide a distinct corrected
freeze, preserving the original worktree and reports. The APFS missing-flag
diagnosis is superseded: `-idirafter` already exists in genuine source recipes;
resource availability remains unresolved and this review supplies no ad hoc
flag/header correction.

See [initial-evidence.json](initial-evidence.json) and the preserved actual
artifact report for commands, identities, cleanup observations and hashes.
