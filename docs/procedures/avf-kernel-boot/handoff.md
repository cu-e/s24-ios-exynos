# VM-040 handoff

Original owner for this task: `codex-guest-collector-20261106-eh`.
Worktree `worktrees/vm-040-eh-20261106`, branch `team/vm-040-eh-20261106`,
base `d596c07d5bbb1ef8f8bca1107a4bbc0c7db7ac42`.

Delivered a real finite collector implementation with a closed genuine-image
allowlist; accepted source/format/ABI/mockfs/console/timer/stop/process helpers;
1080-object raw receipt/source/output lineage requirements; full final args;
exact QEMU/shim/XNUP/FDT/root/PID1 bindings; root lease validation; paused Linux
FDT admission; optional later Apple-tree checkpoint; typed bounded QMP; Stop,
deadline, resource and file-output controls; exact signal-attempt recording and
owned reaping; conservative single-boot observation assessment.

The immutable VM-022 plan is a source-supported future raw Mach-O -> XNUP ->
matched thirteen-source shim route, not a linked image. The current genuine
image is absent. Planning and run both refuse before launching a guest. The
legacy VM-030 classifier receives actual -S argv and retains its rejection;
its source descriptor is never altered. A future independently reviewed
image-bound paused/cont/PID1 stop descriptor and exact root lease are required.
The non-executable execution contract leaves image/admission/lease null.

Root/kernel-integrator steering confirmed that pre-cont memory capture is the
Linux input FDT only. Apple serialized DT is emitted later by the unchanged
shim. A later unique shim-complete marker may enable a diagnostic capture;
absence/races remain explicit, not invented pre-CPU Apple-tree evidence.

VMBOOTCOLLECT-001 was prospectively registered before controls. At `b309cae`,
17 controls passed in1.006s; the original measurement artifacts remain intact.
At implementation `9efba942901bf6457c4807ca91f61f5697ae48a2`,19 controls passed
in0.916255s. The added controls exercised the entire paused Linux FDT protocol
with a real owned Python/Unix-socket peer and an actual4MiB file-output limit.
The peer prints no Darwin banner and its recorded guest_started is false;
its shutdown event explicitly reports guest=false/host-qmp-quit. Direct parser
strings are authored data controls and never become kernel evidence.

Actual tiny Python natural exit was0 with no host signals. Timeout and Stop
both exited-15 after recorded SIGCONT/SIGTERM sends and zero owned survivors.
The output-limit Python exited1 with the preserved File-too-large diagnostic
and exactly4,194,304 console bytes. The real collector CLI exited2 for absent
current image, produced no plan and started no guest. Final control current-image
VmHWM was34,808KiB under inherited256MiB address-space limits. Per-session
samples do not establish an aggregate peak across nested independent sessions;
individual process controls keep their own samples and final survivor checks.

Final producer evidence is schema-valid host-test data at
`artifacts/avf-kernel-boot/measurement-9efba94-1/evidence.json`, with34 actual
artifact files, commands/exits/timing and streaming source/tool/output hashes.
Read-only canonical `lab.evidence(..., 'host-test')` validation passed; its
result is in `artifacts/avf-kernel-boot/schema-check-9efba94-1/result.json`.
Earlier b309cae artifacts are retained. Expected nonzero commands and signal
cleanup remain visible as controls, not relabeled natural guest shutdown.

Source exploration had absent guessed paths before implementation:
docs/procedures/experiment.example.json; tools/run; the guessed PID1 admission
and candidates fixtures; and a shell wildcard for nonexistent VM-022 note
names. These read-only failures are in the session transcript, not independently
captured raw artifact logs. Actual accepted procedure/card/fixture/source paths
were then read. No suite failure or kernel build failure occurred in this phase.

No compiler, linker, production packager, QEMU, guest, phone, SDK, common checks,
MAIN publication or old physical witness mutation ran. The fully admitted real
image path, genuine kernel/PID1 serial output, runtime MMU/RAM/timer behavior and
guest-origin PSCI stop remain unmeasured. The task outcome is collector source
and bounded host controls only. Independent review and kernel integrator/common
acceptance precede original-owner completion. Do not touch blocked VM-002 or
claim another task. A later root QEMU grant is conditional on an actual image
and a separately registered experiment; this producer runs no QEMU trial here.
