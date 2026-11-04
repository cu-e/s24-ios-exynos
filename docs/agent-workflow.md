# Agent workflow and handoff

## Entry

```sh
python3 tools/lab.py status
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

Claims are atomic and protected by a local filesystem lock. State is saved by replacing a temporary file. Do not edit the registry manually in parallel. Claims do not expire automatically: inspect unfinished work before explicitly releasing it. Independent agents must not share an owner name.

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

The next agent resumes from handoff and history rather than repeating the entire review. STATUS.md is derived; resolve conflicts by regenerating it after reconciling state/lab.json.

Use English for maintained project text. Preserve original evidence and provide attributed translations as described in [the language policy](language.md).
