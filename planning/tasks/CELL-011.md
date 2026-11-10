# CELL-011 — Copy the two measured BYH3 vendor RIL libraries to the host with read-only root (decision 0002 item 3)

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | done / done |
| Owner | claude-takeover-20261110-6c8f |
| Priority | 55 (higher first; default 50) |
| Scope / evidence | android-readonly / android-userland |
| Dependencies | none |
| started_at | 2026-11-10T07:45:44+00:00 |
| last_heartbeat | 2026-11-10T07:45:44+00:00 |
| branch | main |

## Readiness

done

## Reserved paths

- `docs/procedures/ril-root-capture`
- `artifacts/ril-root-capture`

## Acceptance

- Before any read, the single selected endpoint reports SM-S921B, e1s and S921BXXS9BYH3; otherwise nothing is read.
- Only /vendor/lib64/libsec-ril.so and /vendor/lib64/libsecril-client.so are read, through su with cat and sha256sum only; no write, chmod, mount, setenforce, setprop, service, modem or RIL command is issued and nothing is executed from the files.
- Each copy&#x27;s host SHA-256 equals the on-device sha256sum and its size equals the CELL-010 measurement (5459848 and 134368 bytes); the bytes stay in ignored artifacts and are never committed or published; only hashes, sizes and ELF header facts are recorded.
- Evidence records the exact commands, exit codes and the device inventory, and states that root access is not proof of safety.

## Steps

1. Identity check
2. Two read-only su reads with on-device hashes
3. Host hash/size/ELF check and evidence

Evidence: [docs/procedures/ril-root-capture/evidence.json](../../docs/procedures/ril-root-capture/evidence.json).
Original evidence SHA256: `da5609b16e5a5dbd47c9ac2170ab022771bb755242fd5ec286a872d2a2ded4ac`.

## CLI

```sh
python3 tools/lab.py task show CELL-011
```
