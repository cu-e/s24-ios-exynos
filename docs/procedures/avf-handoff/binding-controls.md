# AVFHOST-002: provenance rejection controls

Task: VM-005. Owner: codex-team-avf-handoff-20261105-bd. Date: 2026-11-05.

After actual CPU handoff succeeds, verify that the final orchestrator binds the
accepted images to the recorded source builds rather than accepting unrelated
metadata. Keep every original input read-only.

1. Copy the genuine shim build report into this task's artifacts and change only
   the claimed donor SHA to all zeroes. Invoke the final verifier with original
   qualified QEMU, original pinned Image and this intentionally false report.
   Require exit 2 and the explicit source-binding rejection, before compilation
   or QEMU execution. No target output or guest console is manufactured.
2. Copy the qualified original QEMU source manifest and change only the recorded
   `hw/arm/boot.c` SHA256 to all zeroes. Require exit 2 and explicit board/boot/
   PSCI source-manifest rejection, with no object, payload or guest execution.
3. Retain the false metadata, exact commands/exits, report hashes and assertions
   that `cases` is empty and no `normal.o` exists. Both controls are host-only;
   the real CPU/PSCI/guest timeout evidence remains AVFHOST-001.

No build lease, guest RAM, phone, ADB, root, physical MMIO, unrelated-process
signal, SDK/Apple binary or shared source/artifact mutation is involved.
