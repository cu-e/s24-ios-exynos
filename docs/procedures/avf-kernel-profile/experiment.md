# AVFPROFILE-001: pinned actual XNU guest build-profile graph

Date: 2026-11-05. Task VM-006. Owner codex-team-avf-kernel-profile-20261105-bw.

Source review and host-only graph qualification. Read named relevant sources at
Scion a6f4bc38aa244359cd365c976244a88c9d6b3304, E1S donor
c8860decc62c6d6180e609036d027a2997972420 and XNU
c54f35ca767986246321eb901baf8f5ff7923f6a. Keep reference checkouts and previous
artifacts immutable, with GIT_NO_LAZY_FETCH=1 and GIT_OPTIONAL_LOCKS=0 for every
Git child. Missing source blobs fail closed or can be explicitly acquired from
pinned primary public text URLs into this worktree only, verified against the
Git tree blob and SHA256. Do not fetch SDKs, Apple binaries or firmware.

Bind the actual guest entrypoint, source/patch/dependency/configuration choices,
board/initialization/device-tree/interrupt/timer/UART/mockfs/PSCI/export/link and
header/tool requirements into a machine-readable graph. Compare the preserved
native E1S target and its 37 diagnosed export gaps without editing its features,
exports, objects, private declarations or old owners. Distinguish a generic
preflight gate from source evidence for the actual selected guest build route.

Implement bounded manifest/profile validation with meaningful incorrect pin,
changed source, board/config mixing and unresolved-input controls. Record actual
commands/exits, exact source/tool/output hashes and an actionable next build plan.
A source graph pass is not a complete dependency closure, kernel image or boot.
No full build, QEMU/CPU guest, phone, ADB, MMIO, global install or blocked-task
resumption. No compiler is required unless one disputed dependency has a named,
provenanced tiny check; any such job must be sequential and <=256 MiB RSS with
finite deadline and owned cleanup. Save dated evidence and scoped commits; leave
VM-006 in_progress for coordinator review and main common checks.
