# CELL-009 — Recover matching Samsung vendor command schemas through offline RIL analysis

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | done / done |
| Owner | claude-takeover-20261110-6c8f |
| Priority | 80 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-003, CELL-001 |
| started_at | 2026-11-05T03:56:48+00:00 |
| last_heartbeat | 2026-11-10T07:47:35+00:00 |
| progress_note | CELL-010 measured exact live vendor filenames/sizes and denied normal acquisition, replacing the assumed missing-file gap with actual evidence. No matching RIL bytes or qualified static analyzer were supplied; no schema extraction pass. |
| next_step | Supply explicit matching BYH3 RIL/vendor-image provenance and hashes, then qualify isolated analyzer and extract command/request/event schemas without live replay |
| branch | main |
| handoff | docs/procedures/ril/handoff.md |

## Readiness

done

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

Evidence: [docs/procedures/ril/evidence.json](../../docs/procedures/ril/evidence.json).
Original evidence SHA256: `09da83f1405ca85061aaf3b98422694aa549d6faaad9466dc437cfd9a1cc055d`.

## CLI

```sh
python3 tools/lab.py task show CELL-009
```
