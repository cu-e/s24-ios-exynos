# ESIM-004 — Verify selected iOS 16.5 eSIM frontend and hardware-profile compatibility

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | blocked / blocked |
| Owner | codex-esim-frontend-20261105-l |
| Priority | 80 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | RES-003 |
| started_at | 2026-11-05T03:37:28+00:00 |
| last_heartbeat | 2026-11-05T03:44:36+00:00 |
| report_health | recent |
| progress_note | New pinned primary ARI method and real seven-group donor regression pass retained alongside both original failures. Actual selected-image components are unsupplied, so frontend/ABI selection remains unresolved and no native capability is advanced. Released finished shared catalog/plan reservations; retained narrow checker/patch/report paths. |
| next_step | Supply explicit selected16.5 image/build/product provenance and matching CommCenter/baseband/cache/entitlement inputs; inspect exact ABI before adapter/profile choice. Continue independent ESIM-001 host preparation meanwhile. |
| branch | main |
| handoff | docs/procedures/esim-profile/handoff.md |

## Readiness

No explicitly supplied selected iOS16.5 image/build/product manifest or matching CommCenter/baseband/plugin/cache/entitlement inputs; public/later-OS documentation and offline parser tests cannot qualify actual frontend/private ABI or select an adaptation profile.

## Reserved paths

- `tools/research/esim-profile/`
- `docs/procedures/esim-profile/`
- `fixtures/public/esim-profile/`
- `patches/cellular/ari`

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
python3 tools/lab.py task update ESIM-004 --owner codex-esim-frontend-20261105-l --note 'Observed result' --next-step 'Next concrete check'
```
