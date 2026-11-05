# Active-zombie controller follow-up

This additive VM-037 follow-up is isolated in `vm-037-ea-fix2-20261106`, based on
`f663af60c7e272af45053c1b930591b5bfe4c473`. The old original and fix1 worktrees,
helpers and all measured evidence remain physically unchanged.

REV-035 independently confirmed the earlier ownership, lock/deadline, live-path,
JSON snapshot and external-root corrections. Its later real-process finding
showed an active registered controller left unreaped in state `Z`: the PID was
still present, so another executor accepted its snapshot while a never-sampled
orphan remained alive outside project cwd. The original failure receipt is
`worktrees/rev-vm037-eg-20261106/docs/reviews/vm-037/zombie-controller-control.json`.

The production source change is exactly one predicate: an active reservation
requires its controller to exist and have state other than `Z`. Missing or zombie
controllers both fail closed for root reconciliation. No public API, allocation
schema, legacy function, compiler recipe or input key changes.

The narrow `check-zombie.py` fixture creates two legitimate synthetic slots,
leaves one real registered worker deliberately unreaped after it launches an
outside-cwd child, and verifies the observer rejects the snapshot while the child
is still alive. Its own finally block cleans only the created session and reaps
the worker. It also verifies that the entire helper source differs from the
physically preserved fix1 helper only by the intended predicate and that all
legacy top-level function ASTs remain identical. It does not repeat the previous
64-control suite, run a compiler, perform common checks, start a guest or act on
the phone.

Register the new experiment in MAIN before the narrow check:

```sh
python3 fixtures/public/avf-project-budgets/check-zombie.py \
  --out artifacts/avf-project-budgets/zombie-frozen-001
```

The exact frozen source hash, measured capsule and command result are recorded
in `zombie-evidence.json` after execution. Original owner ea retains VM-037 until
independent final recheck and root common acceptance. Only then can original
shard/component owners refresh new prospective plans and root grant the separate
six-job measurement trial.
