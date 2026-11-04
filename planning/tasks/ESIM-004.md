# ESIM-004 — Verify selected iOS 16.5 eSIM frontend and hardware-profile compatibility

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | pending / ready |
| Owner | unassigned |
| Priority | 80 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-003 |

## Readiness

ready

## Reserved paths

- `tools/research/esim-profile/`
- `docs/procedures/esim-profile/`
- `fixtures/public/esim-profile/`

## Acceptance

- Inventory actual locally supplied OS components, version and digests without committing Apple files or silently switching the approved first OS
- Determine whether the selected iPhone X identity/image includes the required eSIM frontend and matching CommCenter/IOKit ABI; a later eSIM-capable reference is not assumed compatible
- Record a concrete adaptation/profile decision and host validation; missing binaries or indirect documentation are not a compatibility pass

## Steps

1. Accept explicit local inputs and verify provenance
2. Inspect frontend capabilities and ABI boundaries without executing or downloading Apple binaries
3. Publish the evidence required before native eSIM lifecycle qualification

## CLI

```sh
python3 tools/lab.py task show ESIM-004
python3 tools/lab.py task claim ESIM-004 --owner agent-your-session
```
