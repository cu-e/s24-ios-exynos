# CELL-010 — Capture exact BYH3 vendor RIL inputs through authorized read-only ADB

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | blocked / blocked |
| Owner | codex-ril-inputs-20261105-m |
| Priority | 85 (higher first; default 50) |
| Scope / evidence | android-readonly / android-userland |
| Dependencies | DEV-001, CELL-001 |
| started_at | 2026-11-05T03:48:29+00:00 |
| last_heartbeat | 2026-11-05T03:56:50+00:00 |
| report_health | stale |
| progress_note | Eight host guard groups pass. Exact live BYH3/uid2000 context reverified; two regular vendor RIL files exist, but ordinary shell checksum and normal ADB sync pulls are denied. No binary bytes acquired or privileges changed. |
| next_step | Use an explicitly supplied matching local RIL/vendor image for offline analysis, or a separately user-authorized future acquisition task; do not retry current access boundary |
| branch | main |
| handoff | docs/procedures/ril-capture/handoff.md |

## Readiness

Existing exact-BYH3 vendor RIL files deny current uid2000 shell checksums and ordinary authorized ADB sync pulls; actual file bytes/hash cannot be acquired within approved current read-only access. No supplied local matching copy exists in this task.

## Reserved paths

- `tools/research/ril-capture`
- `docs/procedures/ril-capture`
- `fixtures/public/ril-capture`
- `tests/test_ril_capture.py`

## Acceptance

- Require an already-authorized selected SM-S921B/e1s endpoint and exact S921BXXS9BYH3 identity before bounded vendor-system file access; no pairing, su, root, settings, installs, reboot or modem operations
- Copy only selected non-personal vendor RIL shared libraries into ignored private artifacts, recording source device/build and actual local SHA256 with remote checksums when permitted or two independent ordinary ADB sync reads with identical bytes/size; do not claim an unavailable remote hash, execute or publish the binaries
- Reject wrong device/build, unbounded/non-regular/wrong-architecture/mutated file inputs and retain unavailable data honestly; host guard tests remain separate from actual device evidence

## Steps

1. Implement a narrow metadata-first collector and host guards using the existing read-only device authorization
2. Register and perform one bounded passive acquisition if an authorized exact device is present
3. Bind captured input provenance to future offline CELL-009 analysis; no command replay or live RIL code execution

## CLI

```sh
python3 tools/lab.py task show CELL-010
python3 tools/lab.py task update CELL-010 --owner codex-ril-inputs-20261105-m --note 'Observed result' --next-step 'Next concrete check'
```
