# Prospective shared guest build budgets

This is host resource governance, not a compiler trial, XNU boot, or phone result.
The default executor profile remains `legacy`: two total project jobs, legacy
approval validation, 256 MiB controller plus child, and unchanged recipe/input keys.
Use `--resource-profile project-budget-v1` for **new** source plans and execution.
Old descriptors, plans, failures, tools and evidence remain immutable.

The root coordinator alone grants an allocation in the existing canonical
`artifacts/team-coordination/20261106-team/resource-queue.json`. Its `heavy` object
must contain the immutable allocation's `id`, `allocation_path`,
`allocation_sha256`, and an exact copy of its `slots` list. Changing or releasing
that queue entry invalidates admission. A copied allocation path or alternate
queue cannot create another broker. The adjacent `.budget.lock` is a stable
flock inode; `.reservations.json` is runtime accounting, not a task registry.
Lock acquisition is nonblocking with a finite 0.5 second maximum wait; command
monitoring further bounds it by the remaining command deadline. A contended
monitor stops only its owned child and retains an unreleased reservation.
Never unlink the lock, recycle completed slots, or silently reclaim stale owners.
Root must reconcile a failed controller and its remaining processes explicitly.

Each allocation reserves at most six serial compiler slots initially, with a
maximum 512 MiB controller plus descendants per executor. The existing 256 MiB
cap remains available to callers. A separate 2 GiB reservation covers light and
auxiliary project work, including declared QEMU. All reservations fit the global
6 GiB ceiling. Every sample discovers processes whose cwd is inside MAIN or its
worktrees, follows their descendants even outside that cwd, and adds exact
PID/start-time identities declared for work rooted elsewhere. Root must declare
such external work before granting; cwd discovery is not an ownership oracle.
All observed session IDs and process PID/start identities remain retained across
commands until release verifies that every known owned process is gone. This
includes reparented children outside the project cwd and children that change
session after observation. Process RSS is summed once by PID, including controllers. Unknown project
compilers outside registered slots or declared compiler work cause deferral.
No unrelated process is signalled. RSS limits are sampled stop limits, not kernel
memory cgroups; short peaks between samples are not proven absent.

Every compiler admission retains three consecutive observations at least one
second apart with at least 4 GiB MemAvailable and acceptable project allocation.
Commands retain the 120 second default, Landlock, owned session cleanup, namespace,
output ownership and genuine source/recipe checks. Monitoring stops only the
caller's owned child on its RSS cap, aggregate cap, memory floor or lost grant.
Prospective trusted JSON uses `load_project(path, expected_sha256)`: one bounded
regular-file snapshot supplies both checksum and JSON parse. Live allocation,
queue, state, lock and temporary paths are checked for symlinks and canonical
ancestry on every transaction. The legacy loader remains unchanged.
Evidence records elapsed time, sampled peak project RSS, individual process
VmSwap, and host pswpin/pswpout counters and deltas. Host swap activity is not
attributed causally to this project.

Eight slots require a distinct root allocation with a bound passing
`project-six-job-measurement-v1` receipt containing actual six-job concurrency,
elapsed time, peak project RSS, a 4 GiB sustained memory floor, and memory/swap
samples. Root and independent review must establish the receipt's measurement
truth; a JSON schema is not proof. No eight-job trial was performed here.

## Shared API for component executors

Import this exact reviewed `tools/build/avf_kernel_objects.py`, pin its hash in
the caller's new plan, and call:

```python
budget = policy.project_approval(args, approval, executor_path=__file__)
budget.reserve()
try:
    # Use load_project for prospective hash-bound JSON inputs.
    # Validate budget.source_plan using the caller's own exact plan contract.
    result = policy.run_child(argv, cwd, out, label, supervisor, budget=budget)
finally:
    budget.release()  # Only after owned cleanup; failures retain reservations.
```

`args` supplies canonical `main`, `out`, `task`, `owner`, `experiment`, and `shard`.
The latter can identify a component such as firehose; the broker does not require
a fake 1080-row object graph. The caller validates ledger ownership, literal
paths, new output, plan contents and command vectors before execution. Each
source plan includes `resource_profile: "project-budget-v1"`. Allocation
`policy_sha256` pins this helper; every slot and approval separately pin the
actual caller's `reviewed_executor_sha256`. The caller remains serial. Passing
no budget preserves legacy command behavior; silently replacing a frozen runner
in an existing experiment is forbidden.

The JSON examples in this directory are **templates only**, not root grants.
Replace every placeholder and SHA, register a new original-owner experiment,
prepare its new source plan, obtain independent review and a separate root grant
before any compiler command. Actual six/eight trials are outside VM-037.

Run the focused synthetic process/temp-filesystem controls in a fresh own path:

```sh
python3 fixtures/public/avf-project-budgets/check.py \
  --main /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-project-budgets/controls-new
```
