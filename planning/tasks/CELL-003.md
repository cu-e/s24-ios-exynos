# CELL-003 — Qualify native CP startup, SIM and registration

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 50 (higher first; default 50) |
| Scope / evidence | native / native-device |
| Dependencies | CELL-002, DRV-003 |

## Readiness

Dependencies: CELL-002, DRV-003

## Reserved paths

- `artifacts/cellular-registration`
- `docs/procedures/cell-003`

## Acceptance

- Actual CP startup, correct slot/PIN state and network registration
- Requires agreed carrier/test subscription and redacted evidence

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show CELL-003
python3 tools/lab.py task claim CELL-003 --owner agent-your-session
```
