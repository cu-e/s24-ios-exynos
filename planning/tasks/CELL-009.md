# CELL-009 — Recover matching Samsung vendor command schemas through offline RIL analysis

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | blocked / blocked |
| Owner | codex-ril-inputs-20261105-m |
| Priority | 80 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-003, CELL-001 |
| started_at | 2026-11-05T03:56:48+00:00 |
| last_heartbeat | 2026-11-05T03:56:51+00:00 |
| report_health | stale |
| progress_note | CELL-010 measured exact live vendor filenames/sizes and denied normal acquisition, replacing the assumed missing-file gap with actual evidence. No matching RIL bytes or qualified static analyzer were supplied; no schema extraction pass. |
| next_step | Supply explicit matching BYH3 RIL/vendor-image provenance and hashes, then qualify isolated analyzer and extract command/request/event schemas without live replay |
| branch | main |
| handoff | docs/procedures/ril/handoff.md |

## Readiness

No explicitly supplied matching BYH3 RIL bytes/hash or vendor-image artifact; CELL-010 verified current ordinary shell and ADB sync access denial. Static schema extraction cannot run on file metadata or another-device examples.

## Reserved paths

- `tools/research/ril/`
- `docs/procedures/ril/`
- `fixtures/public/ril/`

## Acceptance

- Analyze an explicitly supplied matching SM-S921B/BYH3 vendor RIL with recorded hashes and a pinned isolated analyzer/toolchain
- Separate transport headers from SIM/APDU/registration/PDP/SMS/IMS request and event schemas, preserving uncertainty and unsupported commands
- No automatic command replay, device fuzzing, modem reset, profile operation or proprietary binary publication; static inference is not a hardware pass

## Steps

1. Review analyzer/runtime requirements and local binary provenance
2. Perform static extraction and independent checks on synthetic or offline inputs
3. Version only sanitized schema facts and reproducible analysis reports

## CLI

```sh
python3 tools/lab.py task show CELL-009
python3 tools/lab.py task update CELL-009 --owner codex-ril-inputs-20261105-m --note 'Observed result' --next-step 'Next concrete check'
```
