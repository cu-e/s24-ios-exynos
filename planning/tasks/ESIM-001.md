# ESIM-001 — Specify eUICC logical channels and LPA integration

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | done / done |
| Owner | codex-team-esim-20261105-ak |
| Priority | 93 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | CELL-001 |
| started_at | 2026-11-05T13:09:51+00:00 |
| last_heartbeat | 2026-11-05T13:56:03+00:00 |
| progress_note | Coordinator accepted host acceptance after independent exact review b005e7b and integration 6c18ad3+07f873e; common make check PASS 146 tests at f18eba26816d8fa1ce93d4ebb60496a1607ee4ed, evidence artifacts/team-coordination/20261105-ah/integration-002/evidence.json. ESIMHOST-005 passing capsule retained; physical transport, provisioning and selected iOS16.5 frontend remain unqualified. |
| next_step | Host task accepted; exact Samsung physical eUICC transport and selected iOS16.5 frontend qualification remain separate authorized tasks |
| branch | team/esim-001-20261105 |
| worktree | worktrees/esim-001-20261105 |
| handoff | worktrees/esim-001-20261105/docs/procedures/esim-001/handoff.md |

## Readiness

done

## Reserved paths

- `src/platform/esim`
- `docs/procedures/esim-001`

## Acceptance

- Separate active-profile use, APDU access and profile provisioning
- Pin lpac and donor code before reuse; test error/session cleanup

## Steps

1. Inspect the task dependencies and pinned inputs
2. Implement or measure only this task boundary
3. Record real results, failure modes and next-step handoff

Evidence: [worktrees/esim-001-20261105/artifacts/esim-001/session5/evidence.json](../../worktrees/esim-001-20261105/artifacts/esim-001/session5/evidence.json).
Original evidence SHA256: `80c28f663d0059731e9a032640a0268420e96e9423c49392b7baec02015e075e`.

## CLI

```sh
python3 tools/lab.py task show ESIM-001
```
