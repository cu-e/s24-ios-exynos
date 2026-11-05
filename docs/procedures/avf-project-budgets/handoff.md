# VM-037 implementation handoff

Owner: `codex-guest-budget-20261106-ea`. Task remains in progress pending
independent review, accepted common checks, and original-owner closure.

Source base is accepted MAIN `12a43eef4a00da24bed6604655854ef533d2bbb2`.
Ordered implementation commits are `308d868bc6e9dc1cfa4749f69590403503b5e0b9`
and `b712f8e` (one-line disappearing-process sampling correction).
Frozen helper SHA256 is
`48ff45164566810a69cb2bfa07e0684a7adce2e2a4d0262071df2e437f1fbd16`.
Only the reserved engine, fixture directory and procedure directory changed.
The primary checkout's physical executor and all historical experiments remained
unchanged by this owner. The original user attachment was read in full.

The implementation and schema are described in README.md; the allocation and
approval JSON files are explicitly templates, not grants. Root approved the
shared API for VM-036 component calls as well as guest-object calls. A caller
pins the helper policy SHA and its own executor SHA independently, uses an exact
new source plan and root slot, reserves once, executes serially through the
budget-aware child supervisor and releases only after owned cleanup. A single
canonical root queue, allocation path and stable broker lock prevent independent
per-executor limits from multiplying the global allowance.

Exploratory focused controls retained their original files. `control-001` failed
because the fixture's light helper was itself a descendant of its synthetic
executor, so it was correctly charged to that executor. `control-002` exposed a
fixture PID-file creation/write race. These fixture issues were corrected with
a bounded detached helper and a nonempty PID-file wait; no production guard was
weakened. `control-007` passed 46 controls before whitespace normalization and
the one-line process-read race correction. The final frozen official capsule is
listed in evidence.json when available; earlier capsules remain in
`artifacts/avf-project-budgets/` in this worktree.

Controls use real Python/sleep processes, real /proc identities and RSS, a stable
flock with two competing controllers, real Landlock writes, sampled RSS stopping,
finite timeout and owned-session cleanup. They read all 1080 genuine recipes and
compare expansion/digest results and the complete legacy input-key expression
against the immutable accepted executor. They do not run a compiler, linker,
archive tool, guest, QEMU, common suite, or any phone action.

Common checks are deliberately delegated to the root-coordinated integration
boundary after independent review. No actual six/eight compiler timing, peak or
swap experiment has been performed here. Existing VM-016 `vm_map.o` resource
stop at 269406208 bytes against the legacy 256 MiB limit remains a failed
historical observation, not rewritten evidence. Actual new trials require new
original-owner plans and separate root allocation. Cwd discovery cannot identify
an external-root process without a declared identity; root must inventory those
workloads. Sampled RSS does not prove absence of peaks between samples.

The next dependency released by acceptance is prospective planning and root
admission for the remaining genuine guest shards and VM-036 component consumers.
Their original owners can refresh new plan metadata against this helper; actual
execution still waits for independent review and a separate root lease.
