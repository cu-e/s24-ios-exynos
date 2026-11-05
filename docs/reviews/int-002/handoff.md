# REV-024 independent integration gate review

No actionable finding was identified in frozen INT-002 commit
8042e6529e34d470620940e9263ede76e9331b18. The bounded source and temporary
Git/flock/process review passes. Actual MAIN publication and its project common
check remain for the integrator under a concrete coordinator-approved plan and
resource lease. REV-024 remains in progress until fresh MAIN acceptance.

Reviewer codex-review-guest-headers-20261106-cs atomically acquired REV-024 in
the sole MAIN ledger. Root confirmed the role swap after the other reviewer
claimed REV-023 first; no owner transfer occurred. The separate clean worktree
was already named worktrees/rev-vm008-20261106, branch team/rev-vm008-20261106,
base aac27cfbc0d71b34eda33ddf366c72427507ae0b. All maintained changes are scoped
to docs/reviews/int-002. REVGATE-001 was verified planned before execution.

The review independently streamed and verified all 54 bindings in producer
capsule light-4/evidence.json (SHA256
2807bf0826091372c20b5ff1c8a35d7ee02fb4575f9114c6f3a32fff5f10273c), checked
all four files against their exact Git commit bytes, and inspected the thirteen
final CLI reports. Every report uses the frozen production tool SHA256
24e17f2fb06f379103707ed784a9d5b644f936c0a3863a2b4ddcb2a800b9a77f.
Earlier successful producer drafts and expected rejection reports are retained.
The fresh producer suite passed all eleven tests. Four independently authored
probes passed, with a second trace-retention run after adding preserved sample
logs. The first passing run remains unchanged.

Source inspection confirms that primary/candidate identity, ordered ancestry,
every commit's exact path set, full-index binary source/candidate patch identity,
and streamed capsule bindings are checked after acquiring the one primary
state/.integration.lock. Candidate state/planning/lock mutations are rejected.
The primary index must be unstaged, source/dirty intersections and ignored new
file collisions fail, and unrelated live registry bytes remain untouched. The
lock inode is never unlinked. An exact bounded plan snapshot is approved by its
digest; the receipt is cooperative session bookkeeping, as documented.

Publication and common check remain inside one continuous flock. The tool
requires stable available memory before fast-forward and again before check,
rechecks the frozen HEAD, preserves the published HEAD on check failure and
records that failure. The unchanged supervisor samples the newly owned session,
including separate process groups, and cleans its descendants. The sampled RSS
threshold is not a hard cgroup cap.

The independent probes add coverage beyond rerunning the supplied suite:

- A candidate moved after plan freeze is rejected while dirty ledger bytes and
  primary HEAD remain intact.
- An ignored symlink parent cannot redirect a new candidate file outside its
  literal primary namespace.
- A child inheriting the lock descriptor retains exclusion after the parent
  closes its copy; a contender times out until that child exits.
- The actual common_check function and unchanged qemu_host supervisor execute
  a tiny fixture-only make executable that verifies lock exclusion, creates an
  owned child in another process group, and exits 7. The production failure
  gate rejects it and removes the remaining child. Final owned-process lists
  are empty. The final run's sampled child-session peak is recorded in
  run-2/cases/review-actual-common.json; controller current-image VmHWM was
  23,904,256 bytes.

The last probe substitutes admission explicitly. It does not run this project's
make check. It uses the actual 2 GiB preexec virtual-address cap with a 256 MiB
data cap; inherited hard AS=256 MiB would prevent the production child from
setting its real 2 GiB limit. All child work is tiny. The real three-sample
admission, 2 GiB exhaustion stop, 180-second deadline, actual project workload,
and primary publication are not experimentally qualified by this review.
Their source paths were inspected. No compiler, QEMU, SDK, phone, ADB, global
installation, shared reference hydration or unrelated process termination ran.

Deliver this scoped review and evidence.json to /root/lab_worker and root.
The integrator must prepare the exact fresh candidate and source map, bind this
review and its inputs, obtain coordinator approval/resource admission, and run
fresh MAIN common checks. Only the original reviewer owner closes REV-024 after
that acceptance; this review does not close INT-002 or any component task.
