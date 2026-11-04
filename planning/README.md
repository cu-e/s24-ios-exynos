# File-based planning

Start with [BOARD.md](../BOARD.md), the [coordination workflow](../docs/planning.md) and current `python3 tools/lab.py board` output.

- `state/lab.json` is the only writable source of task state, ownership, dependencies, progress and events.
- `BOARD.md` is the generated Kanban and owner activity view.
- `planning/tasks/ID.md` is a generated task card with acceptance, paths, progress, handoff and evidence links.
- `state/board.json` is a generated machine-readable snapshot with the registry hash and view checksums.
- `STATUS.md` is the generated compact task/experiment summary.

Every successful state-changing CLI transaction refreshes all views under the ledger lock. `make board` refreshes them explicitly; `make board-check` checks their consistency. Reading `python3 tools/lab.py board` always renders current state without changing it.

Do not move Markdown cards or edit generated files to change task state. Use claim, update, block, resume, release and done commands. A Git branch or worktree alone does not claim a task. Unreported activity cannot be inferred from files or owner names.
