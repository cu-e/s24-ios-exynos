# VM-037 additive correction handoff

Original owner remains `codex-guest-budget-20261106-ea`. The task is in progress;
independent REV-035 recheck, root-controlled common checks and acceptance remain
required. No six/eight compiler trial has been granted or performed.

The original `vm-037-ea-20261106` worktree is physically unchanged at `5b92f32`.
Its helper SHA `42f84aff5febfe4800cb0f84f4052bc98ac539766f8d4ecd7739a63d2fb7dd0d`,
47-control capsule `b21a0c901fabca37ec4502776edf4e42ab6027907120db2d84bf149ddc98e677`
and producer receipt `f353e0222ba9d9271c4c70b7d43e5ba4e8b26f2f4303a9cf238903aac5b5fde6`
were rehashed unchanged. Those controls passed their original scope; independent
review subsequently found genuine acceptance defects. Neither the passing old
controls nor the failed review receipts have been rewritten or relabelled.
INT-002's earlier `90fab69b` intake paths remain intact.

Corrections are isolated in `worktrees/vm-037-ea-fix1-20261106`, based on the
original frozen candidate. Apply additive source commits
`478d47372e04f9953c9b32e9cee9edde30a5be2d` and
`22afd3d5ece62eb1ab119e363a0e68a417c7308c` after the original stack.
The corrected helper SHA is
`6caa0872750874937c1343b26a168c0d016fa4c98677f54303546e7d194f915a`.

The independently reproduced defects and corrections are:

- An old command's orphan outside project cwd disappeared when the next session
  replaced its identity. The broker now retains all observed sessions and known
  PID/start identities, including descendants after reparenting or session
  changes. Release refuses any live known owned process. A new child is deferred
  while any prior owned command remains alive, preserving the serial slot.
- A blocked flock prevented child memory/deadline supervision indefinitely. Lock
  acquisition now uses nonblocking retries with a 0.5 second bound, further
  limited by the command's remaining deadline. Lost admission terminates only
  the current owned session; final sampling and release are bounded as well.
- Live allocation/queue paths could become symlinks after admission. Every
  transaction rechecks canonical allocation, queue, state, lock and temporary
  paths and ancestors; the acquired stable lock inode is checked explicitly.
- The legacy JSON loader hashed and parsed separate opens. Prospective trusted
  JSON now uses `load_project`, hashing and parsing one bounded regular-file
  byte snapshot. Legacy loading remains unchanged.
- A declared external root could disappear while leaving an outside-cwd orphan.
  A missing/zombie declared root now fails closed for root reconciliation.
  Known dynamically discovered light-process identities are retained as well.

`VM037BUDGET-003` was registered in MAIN before the frozen corrective run.
`artifacts/avf-project-budgets/fix1-frozen-001/evidence.json` passed64 focused
controls with exit0; exact hashes and the original independent failure receipts
are bound by `correction-evidence.json`. The regressions use real processes,
flock contention, owned cleanup, path symlinks and a deterministically scheduled
real path replacement. They also retain the original legacy1080 recipe/key
checks. No compiler, archive/link tool, QEMU, common suite or phone action ran.

The public broker API remains compatible. `sample` additionally accepts an
optional `lock_timeout` keyword. VM-036 should use `load_project` for its new
hash-bound prospective JSON and pin this corrected helper only after independent
acceptance. Existing candidate approvals/plans are not silently updated.
Root, INT-002, VM-036 and REV-035 received this exact source freeze directly.
After acceptance, original shard/component owners can refresh new plans and
root can allocate the separately measured six-job trial. Original ea alone
closes VM-037 after accepted common evidence.
