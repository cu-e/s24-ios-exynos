# CELL-001 — Specify Samsung CPIF control and packet transports

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / ready |
| Owner | unassigned |
| Priority | 70 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-002 |

## Readiness

ready

## Reserved paths

- `src/platform/cellular/contracts`
- `docs/procedures/cell-001`

## Acceptance

- Document S5000AP/shared-memory/SIPC inputs and unresolved firmware commands
- Separate boot, control, SIM registration, data, SMS and IMS requirements

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show CELL-001
python3 tools/lab.py task claim CELL-001 --owner agent-your-session
```
