# QUAL-001 — Run full-system native stability qualification

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 50 (higher first; default 50) |
| Scope / evidence | native / native-device |
| Dependencies | GPU-010, NET-003, BT-002, AUD-002, CAM-002, PWR-002, SEN-002, CELL-006, ESIM-003, BT-005 |

## Readiness

Dependencies: GPU-010, NET-003, BT-002, AUD-002, CAM-002, PWR-002, SEN-002, CELL-006, ESIM-003, BT-005

## Reserved paths

- `artifacts/qualification`
- `docs/procedures/qual-001`

## Acceptance

- 24-hour mixed workload plus repeated boot/sleep/reconnect
- No unexplained faults, leaks or experimental-storage corruption; all remaining limitations visible

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show QUAL-001
python3 tools/lab.py task claim QUAL-001 --owner agent-your-session
```
