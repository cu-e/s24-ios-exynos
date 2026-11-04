# CELL-002 — Implement host-buildable Samsung CP startup and control

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 70 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | CELL-001, BLD-001, KRN-001 |

## Readiness

Dependencies: KRN-001

## Reserved paths

- `src/platform/cellular/transport`
- `docs/procedures/cell-002`

## Acceptance

- Bounded boot/shutdown, framing, reply/event matching and reset states
- Models cover malformed frames, missing replies and resource cleanup

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show CELL-002
python3 tools/lab.py task claim CELL-002 --owner agent-your-session
```
