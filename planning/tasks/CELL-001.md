# CELL-001 — Specify Samsung CPIF control and packet transports

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | done / done |
| Owner | codex-radio-research-20261105-b |
| Priority | 70 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-002 |
| started_at | 2026-11-04T23:39:53+00:00 |
| last_heartbeat | 2026-11-04T23:53:15+00:00 |
| progress_note | Versioned Samsung input contract and bounded SIPC5/SIT host parser implemented; six boundary-test groups passed; seven donor model targets pass under Clang with sanitizers and initial GCC failure retained |
| next_step | Recover matching vendor schema under CELL-009 and verified DT/queue/SMC inputs before native control work |
| branch | main |
| handoff | docs/procedures/cell-001/README.md |

## Readiness

done

## Reserved paths

- `src/platform/cellular/contracts`
- `docs/procedures/cell-001`
- `tests/test_cellular_framing.py`

## Acceptance

- Document S5000AP/shared-memory/SIPC inputs and unresolved firmware commands
- Separate boot, control, SIM registration, data, SMS and IMS requirements

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

Evidence: [state/evidence/CELL-001.json](../../state/evidence/CELL-001.json).
Original evidence SHA256: `c163815802805266ee6a76c41650fd966deccd9bc5e88ca51cc0b58ae9ade6ad`.

## CLI

```sh
python3 tools/lab.py task show CELL-001
```
