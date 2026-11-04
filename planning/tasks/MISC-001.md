# MISC-001 — Specify haptics, NFC, biometrics, video and external display gaps

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

- `src/platform/misc`
- `docs/procedures/misc-001`

## Acceptance

- Each peripheral has exact inputs, interface and a separate native acceptance
- No claim of Apple security or service compatibility

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

## CLI

```sh
python3 tools/lab.py task show MISC-001
python3 tools/lab.py task claim MISC-001 --owner agent-your-session
```
