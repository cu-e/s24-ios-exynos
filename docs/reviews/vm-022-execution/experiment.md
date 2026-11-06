# REVTAIL-001: independent four-tail executor review

Task REV-039, owner `codex-review-link-executor-20261106-er`.
Reviewer worktree `worktrees/rev-vm022-execution-er-20261106`, based on
MAIN `27352788619e594314a1a85a12f07e82fc279184`.

Frozen author worktree `worktrees/vm-022-execution-20261106`, commit
`0d68b46a4b7dd3f2de16962fdbb3806843751d82`; helper SHA256
`67efebaa055207258235801b9a8b9f85c9271ea68786d443deb99d8a9001bf0f`.
Frozen four-tail plan SHA256
`d67ab9e647c7f468a1cd8b789884c5f97e3ddaa3d0a26e0831e24af66e65d499`.
The accepted common executor must remain exact AF193 SHA256
`af193e91ef5a7c24cbba0f797415cc1f2944673e62aadc6d4ace4511810582e0`.

Hypothesis: the frozen helper preserves exact source-derived tail order and
flags, requires original owner/planned experiment and reviewed plan/allocation,
validates namespace/dependencies/ARM64 object bytes and constructor conversion,
and inherits finite child cleanup from accepted AF193. This review may find
defects; a failed check is preserved and prevents an unconditional acceptance.

Prospectively authorized light checks:

1. Stream-hash the exact author helper, plan, capsule, retained control reports,
   source recipe bindings, namespace receipt and accepted common executor.
   Reconstruct the deterministic plan in memory without creating author output.
2. Independently compare every original/resolved argv position and the genuine
   Make OBJROOT/VM038 substitutions. Exercise malformed/missing output/profile,
   owner/experiment, source-plan and approval rejection before any target child.
3. Use small authored ARM64 MH_OBJECT byte fixtures and real temporary files to
   test object/dependency parsing, exact constructor byte conversion, changed
   payload/load commands, malformed extents and unbound namespace shadow/delete.
   A bounded sparse-file/read-observer check may detect an attempted oversized
   allocation without allocating its contents.
4. Exercise the actual accepted ProjectBudget API only against an explicitly
   synthetic allocation/ledger/queue under the reviewer temporary directory.
   Test exact slot/owner/plan/output, stale/expired allocation, lock replacement,
   Stop/cleanup and retained-process accounting. It grants no production lease.
5. Exercise actual AF193 run_child with finite Python-only children and the
   accepted supervisor, isolated temporary output/cwd, no target tool. Test
   success, nonzero exit, deadline, SIGINT and SIGTERM cancellation observations,
   child in a separate process group, and write escape rejection. The parent
   watchdog removes only identified reviewer-owned survivors and preserves
   any failure of the tested controller to clean itself up.

The review starts no compiler, assembler, archiver, linker, section tool,
packager, QEMU, phone action or common repository check. All synthetic object
and allocation fixtures remain marked as fixtures and cannot qualify a kernel.
No author source or historical witness is edited. Main-link/image/provider
production is outside this implementation and remains explicitly gated.

Each real Python control has a finite deadline of at most 8 seconds; the whole
review command deadline is 120 seconds. New owned RSS must remain below 256 MiB.
Use LC_ALL=C, PYTHONUTF8=1, PYTHONNOUSERSITE=1 before Python starts. Preserve exact
commands/exits/times/current-image memory and hashes, including failed attempts.
