# STR-001 immediate decision handoff

Owner `codex-strategy-scion-20261106-sr1`, branch
`team/str-001-scion-20261106`, worktree
`worktrees/str-001-scion-20261106`; base MAIN951f23336c1521c8ee94828e26fc98bfcf1e8411.
Maintained scope is only `docs/strategy/2026-11-06/scion`.

Read report.md, source-bindings.json and evidence.json. Official current Scion
is renamed `Scion-Project/scion-kernel`, exact main
8bee16f38f6e34751d2867a8945577edc7cd30c7, 111 commits ahead of our unchanged
a6f4bc38aa244359cd365c976244a88c9d6b3304. Complete official Git trees establish
the generic AVF shim, QEMU runners, payload packager, minimal hello/libmini and
kernel build wrappers are unchanged. EFI loader organization and profile/source
application have changed; they do not remove the existing generic guest blocker.
Current hello retains the inline x1 defect: preserve already admitted VM034.

Recommended next root-owned action is one bounded direct-link diagnostic from
the preserved source template and matching existing objects/tails/providers,
with actual stderr/exit/entry evidence. No new full build, executor, archive,
packaging, guest or productive pin adoption follows from this source audit.
If a concrete required input is missing, report that exact input instead of
opening more generic infrastructure. This worker did not invoke any target tool.

CN owns the native E1S route, CM owns infrastructure/receipt overhead, root owns
HakiOS and the combined A/B/C choice. Scion's current tree has no named E1S or
Exynos2400 donor; AVF device eligibility remains unknown. The probe's permission
changes are not authorized and were not run. Hardware source-contract work can
continue independently of guest console reproduction.

Local read-only source acquisition is retained under this worktree's ignored
`artifacts/strategy-scion`: exact refs, complete trees, bounded API comparison,
verified source files, all initial/retry failures, and verified local-donor
fallbacks. The compare file list is capped at300, so no absence claim relies on
it. Primary code bytes were accepted only after matching canonical Git blob
SHA1 and SHA256; unsuccessful fetches were not silently substituted. No source
pin, pinned checkout, shared ref, build result or previous task was changed.

This is a source-review decision, not reproduced boot, E1S adaptation or device
verification. Root can integrate the compact result immediately; original owner
holds task closure for acceptance. No further donor survey is needed here.
