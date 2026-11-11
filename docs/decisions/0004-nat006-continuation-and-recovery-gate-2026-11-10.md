# 0004: Owner instruction to continue held NAT-006 and gate RECOVERY test on verified recovery conditions (2026-11-10)

Status: accepted by project owner (Egor) in the 2026-11-10 Antigravity session (`aca2cbd5-82ac-4f6d-b52c-1974899d7a84`).

## Decision

The project owner directed the Antigravity session (`agy-nat006-20261110-aca2`) to take over `NAT-006` from its held preservation state (`claude-takeover-20261110-6c8f`, `next_step: "Held; not restarted. Owner decides next action."`), complete the interrupted `NAT-006` host image builder and independent verifier in `worktrees/nat-006-recovery-image-20261110` (`team/nat-006-recovery-image-20261110`), inventory all saved artifacts and hashes, verify the connected SM-S921B/e1s and partition backups, and evaluate pre-flash recovery readiness.

## Scope and mandatory safety gate

- Authorized within this instruction:
  - Transferring `NAT-006` from the held preservation state (`claude-takeover-20261110-6c8f`) to `agy-nat006-20261110-aca2` via `tools/lab.py task transfer` while keeping the worktree `worktrees/nat-006-recovery-image-20261110` and commit `ac22ef588e0830a80847bd3475ae0d6796d8b3e7` intact.
  - Completing `docs/procedures/nat-006/verify_image.py` and `tests/test_e1s_recovery.py`, running `tools/build/e1s_recovery.py`, and verifying the `RECOVERY`-format image (`STR-041` kernel + patched E1S loader) and stock restore package on the host.
  - Using ADB and root (`su`) for read-only device diagnostics and backup verification against the connected phone.
  - Writing a verified image **only** to `RECOVERY` and attempting a native boot **only if** pre-flash recovery conditions after a hang (Download Mode entry, availability of host recovery tools, verified backup match, and absence of a recovery boot-loop trap that could strand Android) are confirmed.
  - Creating follow-up tasks in `state/lab.json`, committing results, and recording a verifiable handoff report for the main session.
- Mandatory boundary:
  - The installed Android system, apps, settings, accounts, and user data must remain intact.
  - Reset, formatting, unlock with wipe, and writing `BOOT`, `init_boot`, `vendor_boot`, `dtbo`, `vbmeta`, `USERDATA`, or any partition other than `RECOVERY` remain strictly forbidden.
  - If the chosen method requires forbidden actions or if critical recovery conditions after a hang are unconfirmed, stop before writing `RECOVERY` and record a concrete blocker.
