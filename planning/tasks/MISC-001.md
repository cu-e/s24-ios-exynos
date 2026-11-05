# MISC-001 — Specify haptics, NFC, biometrics, video and external display gaps

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | done / done |
| Owner | codex-team-misc-20261105-an |
| Priority | 70 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-002 |
| started_at | 2026-11-05T13:28:27+00:00 |
| last_heartbeat | 2026-11-05T14:03:31+00:00 |
| progress_note | Coordinator accepted specification criteria after independent REV005 review d0e3e0ef: no bounded P0/P1/P2 findings. Main implementation 6a3e127 and review 3b5b4f9 integrated; common make check passed 146 tests at 3b5b4f987bc73b7cb1e7f056d1efa0252fa5c70c. Integration evidence: artifacts/team-coordination/20261105-ah/integration-003/evidence.json. All native hardware gates remain open; no Apple service or security compatibility asserted. |
| next_step | Complete accepted MISC-001 with original passing source-audit evidence; future native work requires separate tasks and acceptance. |
| branch | team/misc-001-20261105 |
| worktree | worktrees/misc-001-20261105 |
| handoff | worktrees/misc-001-20261105/docs/procedures/misc-001/HANDOFF.md |

## Readiness

done

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

Evidence: [worktrees/misc-001-20261105/artifacts/misc-001/2026-11-05-source-audit/evidence.json](../../worktrees/misc-001-20261105/artifacts/misc-001/2026-11-05-source-audit/evidence.json).
Original evidence SHA256: `458a5ab066a99c8b5cc3588347c49974e8ba293e196d1f24b434c868736b8abb`.

## CLI

```sh
python3 tools/lab.py task show MISC-001
```
