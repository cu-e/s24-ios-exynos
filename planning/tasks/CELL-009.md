# CELL-009 — Recover matching Samsung vendor command schemas through offline RIL analysis

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / ready |
| Owner | unassigned |
| Priority | 80 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-003, CELL-001 |

## Readiness

ready

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
python3 tools/lab.py task claim CELL-009 --owner agent-your-session
```
