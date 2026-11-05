# VMSTOP-002: reject legacy PID1 runtime admission

Task VM-030, owner `codex-guest-exec-20261106-dl`, 2026-11-06.

VM-025's pinned source review identifies input-only x1 in the legacy syscall
wrapper while selected XNU overwrites that register. Root assigned VM-034 for a
qualified replacement. Historical source and synthetic stop contract findings
remain useful; the legacy PID1 must remain inadmissible for actual execution.
This source diagnosis does not claim a measured failure of the old binary.

Hypothesis: the revised descriptor/preflight explicitly rejects legacy PID1
runtime assessment. The unchanged observation classifier can still separate a
synthetic halt/timeout from clean guest-origin QMP stop evidence without making
legacy PID1 eligible. No compiler, QEMU, genuine guest or phone is started.

1. Use final source-only controls to prepare a bound synthetic halt record.
2. Run five finite Python CLI cases in fresh owned directories: timeout with
   exit zero, host-origin shutdown, malformed QMP, unreviewed preflight and
   default PID1-panic assessment against the known inadmissible legacy input.
3. Require exit 2 for all five; timeout is host cleanup, host-origin shutdown is
   inconclusive, malformed/unreviewed/PID1 admission fail with explicit reasons.
4. Preserve all prior VMSTOP-001 reports and source/evidence commits, including
   the now-superseded positive synthetic PID1 artifact admission. No earlier
   result becomes genuine runtime evidence.

Each Python process inherits a 256 MiB address-space cap and a five-second
deadline. The full experiment deadline is 30 seconds. Record actual commands,
exits, times, current-image memory, source/tool/input/output hashes, stdout and
stderr. Independent review and VM-034 source-to-image qualification are future
gates; no task completion, main publication or common check is performed here.
