# CELL-006 — Qualify SMS, IMS and bidirectional voice calls

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 50 (higher first; default 50) |
| Scope / evidence | native / native-device |
| Dependencies | CELL-005, AUD-002 |

## Readiness

Dependencies: CELL-005, AUD-002

## Reserved paths

- `artifacts/cellular-voice`
- `docs/procedures/cell-006`

## Acceptance

- Agreed carrier/test endpoints; incoming and outgoing calls with duplex audio
- SMS including multipart, IMS state and routing are individually measured

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show CELL-006
python3 tools/lab.py task claim CELL-006 --owner agent-your-session
```
