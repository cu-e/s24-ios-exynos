# CELL-005 — Qualify native mobile data, IPv6 and reconnect

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / gated |
| Owner | unassigned |
| Priority | 50 (higher first; default 50) |
| Scope / evidence | native / native-device |
| Dependencies | CELL-003, CELL-004 |

## Readiness

Scope not authorized: native; Dependencies: CELL-003, CELL-004

## Reserved paths

- `artifacts/cellular-data`
- `docs/procedures/cell-005`

## Acceptance

- Actual IPv4/IPv6/DNS/HTTPS and repeated reconnect
- Status bar alone cannot pass

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show CELL-005
python3 tools/lab.py task claim CELL-005 --owner agent-your-session
```
