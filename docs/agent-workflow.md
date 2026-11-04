# Agent workflow and handoff

## Entry

```sh
python3 tools/lab.py status
python3 tools/lab.py board
python3 tools/lab.py task next
python3 tools/lab.py task show RES-001
python3 tools/lab.py history
```

`task next` defaults to host tasks with completed dependencies. `--scope android-readonly` selects read-only tasks. Scope flags record agreed boundaries; they do not authorize expanding those boundaries.

## One task, one owner

```sh
python3 tools/lab.py task claim RES-001 --owner agent-a
python3 tools/lab.py task block RES-001 --owner agent-a --reason 'Access to the selected upstream is required'
python3 tools/lab.py task release RES-001 --owner agent-a
```

Claims are atomic and protected by a local filesystem lock. `task claim-next --owner UNIQUE-SESSION --scope host` chooses and claims an eligible task in one transaction. State is saved by replacing a temporary file. Active/blocked tasks reserve their paths; overlapping claims are rejected. Do not edit the registry manually in parallel. Claims do not expire automatically: inspect unfinished work before explicitly releasing it. Independent agents must not share an owner name. The [planning workflow](planning.md) documents priorities, owner reports, heartbeat, resume and failure recovery.

## New tasks

Create a spec from task.example.json, then:

```sh
python3 tools/lab.py task add --file docs/procedures/task.example.json --owner planner
```

The example ID is EXAMPLE-999; do not add it without a real task. Define the objective, scope, evidence_kind, dependencies, acceptance, paths and narrow steps. Dependencies must remain acyclic.

Use branch names such as `task/RES-001-description`. For explicitly authorized parallel work, use a separate worktree per task and keep the shared ledger in the primary checkout. Path ownership is coordinated by agents; the CLI does not enforce tasks.paths against filesystem edits.

## Completion

Save real artifacts and evidence first, then run task done and make status. `done` requires pass and existing files; acceptance still needs review. Commit code, tests, documentation and associated registry changes together. Do not include another owner's work or private artifacts.

## Handoff

For sustained work, maintain `research/notes/ID-handoff.md`: objective, sources read and SHAs, changes, commands and actual exit codes, known defects, device boundaries and the next concrete step. Update before stopping. Keep failed experiments.

The next agent resumes from handoff and history rather than repeating the entire review. Use `task update` to attach the handoff, progress and next step before yielding. STATUS.md, BOARD.md, task cards and state/board.json are derived; resolve conflicts by regenerating them after reconciling state/lab.json. Every successful mutation refreshes the views. `make board-check` detects stale or edited generated files.

Use English for maintained project text. Preserve original evidence and provide attributed translations as described in [the language policy](language.md).
