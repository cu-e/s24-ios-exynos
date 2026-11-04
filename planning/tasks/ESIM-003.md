# ESIM-003 — Implement and qualify test eSIM profile lifecycle

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / gated |
| Owner | unassigned |
| Priority | 50 (higher first; default 50) |
| Scope / evidence | native / native-device |
| Dependencies | ESIM-002, CELL-005 |

## Readiness

Scope not authorized: native; Dependencies: ESIM-002, CELL-005

## Reserved paths

- `artifacts/esim-lifecycle`
- `docs/procedures/esim-003`

## Acceptance

- Agreed test subscription and working APDU/LPA path
- Download/enable/switch/error recovery independently qualified; settings page cannot pass

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show ESIM-003
python3 tools/lab.py task claim ESIM-003 --owner agent-your-session
```
