# ESIM-002 — Qualify an already-active test eSIM profile

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 50 (higher first; default 50) |
| Scope / evidence | native / native-device |
| Dependencies | ESIM-001, CELL-003 |

## Readiness

Dependencies: CELL-003

## Reserved paths

- `artifacts/esim-active`
- `docs/procedures/esim-002`

## Acceptance

- Actual native registration using an agreed test eSIM
- No production-profile mutation; record slot behavior without identifiers

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show ESIM-002
python3 tools/lab.py task claim ESIM-002 --owner agent-your-session
```
