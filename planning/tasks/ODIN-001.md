# ODIN-001 — Fix the pinned odin4 for e1s restore: proven wire sequence, strict PIT, one session per Download Mode entry, no resend, staged completion

> Generated task card. Edit state through tools/lab.py, not this file.

[Kanban](../../BOARD.md) · [Workflow](../../docs/planning.md)

| Field | Value |
|---|---|
| State / column | blocked / blocked |
| Owner | claude-takeover-20261110-6c8f |
| Priority | 92 (higher first; default 50) |
| Scope / evidence | host / host-test |
| Dependencies | NAT-013 |
| started_at | 2026-11-10T11:39:05+00:00 |
| last_heartbeat | 2026-11-10T11:45:18+00:00 |
| report_health | recent |

## Readiness

Stopped by the safety classifier at about 11:44Z on 2026-11-10 while writing the fake-libusb host test harness; not retried, reworded or delegated. Done: three local patches against odin4 338fde45 in artifacts/odin4-e1s/work (1fdfc82 wire sequence, 8030309 PIT chunks/no resend/payload total/pre-validation, e543114 session ledger/node check/staged report); built; upstream 47 tests pass; binary artifacts/odin4-e1s/odin4 (untested against any device or fake). Not done: wire-equivalence harness, patch export to patches/odin4-e1s, docs, evidence. The patched odin4 is not qualified; the NAT-013 tool stays the supported restore path. Resume only on an explicit owner instruction after support review.

## Reserved paths

- `patches/odin4-e1s`
- `docs/procedures/odin4-e1s`
- `artifacts/odin4-e1s`

## Acceptance

- Keep local changes as numbered patches against odin4 338fde4569ee3b0743098714199361835f96015b with license (Apache-2.0), attribution and an explanation per change; leave references/odin4-nat008 at its pinned tree.
- Remove every unproven wire behaviour for S921BXXS9BYH3: no 0x64/1 before or after BeginSession, BeginSession version 4, no ZLP or empty transfers, no automatic resend of commands or data, exact PIT chunk lengths, total bytes equal to member payload sizes; keep the original strict PIT checks.
- Enforce one Odin session per USB enumeration across runs and refuse while another process holds the device node; report upload acknowledgement, session end, reboot and the still-required Android readback as separate stages, never as overall success.
- Host-test the patched odin4 through its real code path against a fake libusb that models the recorded S-Boot behaviour: the wire sequence for the stock recovery tar must equal NAT-012 restore-003, a second session in one entry must be refused, and the upstream test suite must still pass. No phone I/O.

## Steps

1. Write the patch set and build it reproducibly from a clean export of the pinned tree
2. Add a fake-libusb harness and wire-equivalence, session-ledger and PIT-chunk tests
3. Document supported use and limits; save evidence

## CLI

```sh
python3 tools/lab.py task show ODIN-001
python3 tools/lab.py task update ODIN-001 --owner claude-takeover-20261110-6c8f --note 'Observed result' --next-step 'Next concrete check'
```
