# CELL-004 — Implement packet data and iOS telephony service adapters

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / waiting |
| Owner | unassigned |
| Priority | 70 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | CELL-001, BLD-001, KRN-001, CELL-009 |

## Readiness

Dependencies: KRN-001, CELL-009

## Reserved paths

- `src/platform/cellular/ios`
- `docs/procedures/cell-004`

## Acceptance

- Specify selected iOS 16.5 ABI rather than assuming iOS 17 compatibility
- IPv4/IPv6, events and reconnect behavior have host models

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show CELL-004
python3 tools/lab.py task claim CELL-004 --owner agent-your-session
```
