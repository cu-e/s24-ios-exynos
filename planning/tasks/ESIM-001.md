# ESIM-001 — Specify eUICC logical channels and LPA integration

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 70 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | CELL-001 |

## Readiness

Dependencies: CELL-001

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
python3 tools/lab.py task claim ESIM-001 --owner agent-your-session
```
