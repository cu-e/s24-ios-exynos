# VMBOOTCOLLECT-001: collector source and bounded host controls

Task VM-040, owner `codex-guest-collector-20261106-eh`.
Register this procedure in the sole MAIN ledger before running its controls.

Hypothesis: an owned collector can bind exact accepted helper/source/tool and
future image/package/admission inputs, refuse absent or unadmitted genuine
images before any guest launch, and preserve bounded process/QMP/cleanup
evidence without confusing host termination or authored text with XNU success.

Only source reading, stdlib Python parser controls, temporary owned filesystem
operations, local Unix sockets and tiny owned Python subprocesses are admitted.
No compiler, linker, packager production, QEMU, guest, phone, SDK or common
repository checks run. Historical physical worktrees and VM-002 remain read-only.

1. Freeze the collector and control implementation in scoped commits. Reuse
   accepted VM-026 memory, VM-027 tree, VM-028 console, VM-029 timer, VM-030
   stop, VM-025 candidate and VM-024 package boundaries. Pin the exact VM-022
   raw Mach-O to XNUP to thirteen-source matched shim plan as future lineage.
2. Run serial finite controls for absent image/refused admission, changed pins,
   payload embedded-kernel/ramdisk mismatch, repeated/conflicting console or
   shutdown records, QMP framing/types/limits, output/symlink/socket ownership,
   stale lease/time, stop-before-start and stop-during-owned-process behavior.
3. Exercise a tiny actual Python child for natural exit, finite timeout,
   cooperative Stop and bounded output. Use only newly owned temporary files
   and sockets. Assert exact owned process reaping; never kill other processes.
   QMP protocol fixtures are authored Python peers, not QEMU or guest evidence.
4. Run the real collector CLI against the current absent-image descriptor and
   require explicit refusal with no child launch. CLI/parser results must never
   claim genuine kernel, PID1, guest-origin shutdown or hardware execution.
5. Preserve actual argv/cwd/exits/time, failed attempts, streaming source/tool/
   input/output hashes and current `/proc` VmHWM. Controls use 256MiB address
   limits and finite per-case deadlines; whole experiment has a120-second cap.

Evidence uses the repository host-test schema (`kind`, `origin`, `outcome`,
`recorded_at`, `summary`, `commit`, `commands`, `artifacts`, `limitations`).
An independently reviewed collector implementation is the task outcome. Actual
genuine XNU execution requires a future image-bound admission, exact root lease,
accepted final plan and separate experiment. A256MiB guest/512MiB owned budget
is a limit, not an assertion that the absent image will boot within it.
