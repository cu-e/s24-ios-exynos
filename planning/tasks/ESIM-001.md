# ESIM-001 — Specify eUICC logical channels and LPA integration

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | in_progress / in_progress |
| Owner | codex-team-esim-20261105-ak |
| Priority | 93 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | CELL-001 |
| started_at | 2026-11-05T13:09:51+00:00 |
| last_heartbeat | 2026-11-05T13:09:51+00:00 |
| report_health | recent |
| branch | team/esim-001-20261105 |
| worktree | worktrees/esim-001-20261105 |

## Readiness

in_progress

## Reserved paths

- `src/platform/esim`
- `docs/procedures/esim-001`

## Acceptance

- Separate active-profile use, APDU access and profile provisioning
- Pin lpac and donor code before reuse; test error/session cleanup

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show ESIM-001
python3 tools/lab.py task update ESIM-001 --owner codex-team-esim-20261105-ak --note 'Observed result' --next-step 'Next concrete check'
```
