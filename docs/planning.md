# Planning and agent coordination

This is a local task queue with dependencies, priority, ownership and generated Kanban files. It does not spawn agents, schedule calendar jobs or establish that an agent process is alive. The canonical state is state/lab.json.

## Views

Open [BOARD.md](../BOARD.md) for the Kanban, active owners, their latest progress/next step and recent events. Each card links to a generated file in planning/tasks/. [state/board.json](../state/board.json) provides the same tasks and owner reports for tools. English is used throughout maintained planning data.

| Column | Meaning |
|---|---|
| Ready | Pending, authorized, dependencies done, paths available |
| In progress | Claimed by its recorded owner |
| Blocked | Explicit obstacle; owner and path reservations retained |
| Waiting | Pending dependencies or paths held by another task |
| Needs authorization | Scope is not currently authorized; dependencies may also be pending |
| Done | Passing evidence recorded; CLI checks structure, an agent/reviewer assesses acceptance |

Priority is an integer from 0 to 100; higher values come first, default 50. Equal priorities retain registry order. Priority never bypasses dependencies, scope authorization, ownership or path reservations.

## Taking work

Use a unique stable owner name per agent session, such as agent-touch-20261105-a. Owner labels are cooperative bookkeeping, not authentication. Do not reuse another session's owner to bypass ownership checks.

```sh
python3 tools/lab.py board
python3 tools/lab.py task next --scope host
python3 tools/lab.py task claim-next --owner agent-touch-20261105-a --scope host
```

`next` only previews candidates. `claim-next` chooses and claims one eligible task while holding the shared ledger lock; two agents cannot take the same task. Review the returned task using `task show ID` before implementation. Optional --branch/--worktree values are reported context only: the CLI does not create or check out a branch/worktree. Omit them until known. To choose an exact task instead:

```sh
python3 tools/lab.py task claim DRV-001 --owner agent-touch-20261105-a
```

A failed claim changes no task state. When no eligible work exists, inspect dependencies, reservations and authorization rather than retrying a busy loop.

## Progress and handoff

```sh
python3 tools/lab.py task update DRV-001 --owner agent-touch-20261105-a \
  --note 'Parser rejects truncated packets in host fixtures' \
  --next-step 'Check coordinate boundaries' \
  --handoff research/notes/DRV-001-handoff.md
python3 tools/lab.py task heartbeat DRV-001 --owner agent-touch-20261105-a
```

Create the handoff file before referencing it. Progress is an observation, not an invented percentage. `update` may also record --branch and --worktree. Updates and heartbeats refresh last_heartbeat; progress/next step are retained in the event history. Report at meaningful checkpoints and before yielding, not on a timer without useful context.

Reports older than 30 minutes are marked stale when the board is rendered. Existing snapshots do not change with wall-clock time: run `board` for a current assessment. Stale/unknown does not mean dead and never releases or transfers a claim. A heartbeat does not prove a process is running.

## Obstacles, return and release

```sh
python3 tools/lab.py task block DRV-001 --owner agent-touch-20261105-a \
  --reason 'Need the pinned donor protocol header'
python3 tools/lab.py task resume DRV-001 --owner agent-touch-20261105-a
python3 tools/lab.py task release DRV-001 --owner agent-touch-20261105-a
```

Only the recorded owner may update, heartbeat, block, resume, release or complete owned work. Blocked tasks retain their paths until released or completed. Resume preserves the owner and rechecks prerequisites/scope. Release returns the task to pending; it does not revert files or Git changes. Save a handoff first. There is no automatic expiry, forced takeover or impersonation flow: inspect work and coordinate with its owner before explicit release.

The only takeover is `task transfer ID --from-owner OLD --owner NEW --reason R --decision docs/decisions/FILE [--handoff PATH]`. It requires an owner decision record (currently 0002 and 0003, for any finished or stopped executor: Codex, Claude or their subagents), an active or blocked task held by OLD and a concrete reason. Check first that no live process works on the task. It keeps files, branch and results, appends `ownership_history` and leaves status unchanged. There is still no automatic expiry.

Scope flags change only with `project permit --scope S --value true|false --decision docs/decisions/FILE --owner NAME`, which records the decision path in `project.permission_decisions` and in the event. The flag mirrors the owner's written decision; it never grants anything by itself.

## File reservations and parallel work

Task paths are literal relative files/directories. Parent/child paths overlap: tools/ conflicts with tools/lab.py. Traversal, globs, absolute paths and symlink aliases are rejected. Claims on overlapping active/blocked task paths are rejected, even under the same owner. Pending tasks may overlap while waiting; narrow their planned scope before adding them.

A planner may shrink the reservation of a pending, unowned task whose broad historical paths overlap active work:

```sh
python3 tools/lab.py task narrow DRV-002 --owner planner-session \
  --paths tests/test_ufs_contract.py \
  --reason 'Only this test remains in scope; tests/ overlapped another reservation'
```

Each new path must equal or lie inside one of the task's current paths; widening, duplicates and an unchanged set are rejected. The old and new paths go to the task's `path_history` and to the event. Narrowing never assigns an owner and never applies to claimed or blocked work.

Reservations are CLI coordination, not OS access control. They cannot stop direct edits by an uncooperative process. Shared generated state/views are maintained by the CLI and do not need to be listed in each task. Keep shared task boundaries narrow. Existing task boundaries are not silently broadened or automatically reassigned.

Parallel implementation still requires explicit authorization and separate worktrees. All workers must address the same primary checkout ledger:

```sh
python3 /home/egor/dev/pet/s24-ios-exynos/tools/lab.py \
  --root /home/egor/dev/pet/s24-ios-exynos board
```

Do not claim against independent worktree copies of state/lab.json. This uses fcntl advisory locking on one local filesystem; it is not distributed coordination across machines or independently synchronized checkouts. No parallel workers are launched automatically.

## Planning and completion

Add a pending task with `task add --file SPEC --owner planner-session`. Follow docs/procedures/task.example.json and set optional priority. Dependencies must be acyclic; scope and evidence_kind must agree. A planner may reprioritize pending work:

```sh
python3 tools/lab.py task prioritize RES-001 --owner planner-session \
  --priority 80 --reason 'Pin sources before implementation work'
```

Reprioritizing does not assign an owner or authorize device work. After actual acceptance verification, record dated evidence and complete:

```sh
python3 tools/lab.py task done DRV-001 --owner agent-touch-20261105-a \
  --evidence artifacts/drv-001/evidence.json
```

The CLI publishes updated STATUS.md, BOARD.md, cards and state/board.json after each successful mutation. Generated files are snapshots; the registry remains authoritative. `board --check` detects stale, missing or edited views. If publication fails after the registry is saved, the error explicitly says the state was saved. Do not repeat the claim blindly; inspect `task show`, fix the filesystem problem and run `board --write`. Publication of many files is not one filesystem transaction; the JSON checksum index is written last to make incomplete refreshes detectable.

Commit relevant code, evidence, registry and generated views together. Do not hand-merge generated snapshots; reconcile the ledger, then regenerate. Use [the agent workflow](agent-workflow.md) for evidence and source requirements.
