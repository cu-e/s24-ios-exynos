# VM-040 handoff

## Final selected-consumer correction

The final continuation uses `worktrees/vm-040-consumer-20261106`, branch
`team/vm-040-consumer-20261106`, based on first-correction metadata a2ed73a.
Both prior physical source worktrees and all capsules remain unchanged. REV-037
preserved its original and first-correction findings separately; its first
process recheck was honestly deferred before any spawn due host PSI. That
deferral was not a producer process failure and was not bypassed here.

The reviewer independently confirmed a residual: root `/` also satisfies a
one-slash test, although the shim scans root children. A canonical compatible
list containing both PL011 and ns16550a also selects the shim's priority8250
path, so merely finding the PL011 token is insufficient. Those cases remain
in reviewer `runs/correction-fdt-residual-1/report.json`.

Final operative source commit is
`c8bd677b3280cf3610d2d1aa88dd6386a4e44a86`, collector SHA256
`233da39b23ea8986e83db6bfdceb8f23c52b0c6ac044f7f1d5f30d451e145c06`.
It explicitly excludes root from memory-child selection. All compatible lists
used for selected-consumer checks must terminate; canonical PL011 and GIC
consumers must be unique. Any exact ns16550a token across nodes rejects the
selected PL011 route, preserving its real global priority. This is a narrow
conservative selected-route policy, not a general shim/device-tree emulator.
No additional parser redesign or image/runtime admission was added.

VMBOOTCOLLECT-004 was prospectively registered. Nine focused pure-FDT cases
pass: valid child/root-plus-child/exact-token-list positives, plus root-only,
canonical mixed8250, other-node8250, competing PL011/GIC and unterminated-list
rejections. No subprocess/process admission was replayed by this producer under
the reported PSI condition. Current-image VmHWM was29,792KiB under256MiB address
space. Raw capsule
`artifacts/avf-kernel-boot/consumer-c8bd677-1/evidence.json` SHA256 is
`0da4671e19d14bd1df6f853a39425e3aa95c14996ff7bb51783a5530ba0a9d1e`;
its report SHA256 is
`3aaad760fe516f7d7e4441cdf75d160e8d5b1de34fbb77de5e6041a56b07ee0d`.
Maintained copy is `consumer-correction-evidence.json`; canonical evidence
schema passes. `consumer-validation-c8bd677-1/report.json` verifies unchanged
original82dc source/raw capsule and first-correction341d source/two capsules.

The independent reviewer subsequently reported PASS29 checks on this exact
c8bd677/source233da39b freeze, including replayed original/residual FDT cases,
and actual Python late-expiry/revocation/floor-drop/Stop-during-final-lease
zero-spawn cases. Its valid Python case spawned exactly once and exited
naturally without signals/survivors; external resource admission passed.
The reviewer is binding its final independent capsule. No additional producer
source change or control run is needed. This remains source/host-control
acceptance only: no actual image, QEMU FDT, XNU, PID1 or guest result is claimed.
Task closure still requires accepted integrator publication/common checks and
explicit original-owner completion authorization.

## REV-037 correction continuation

The original physical `vm-040-eh-20261106` source/four commits/capsules remain
unchanged. Correction worktree is `worktrees/vm-040-lease-20261106`, branch
`team/vm-040-lease-20261106`, based on original tip
`a0b64b31cceb6e4b0d3138628d4fed386d2fe2bc`, with the same original EH owner.

Independent REV-037 measured two P2 defects in the frozen original source:
an expired lease could spawn during a trailing admission sleep before the first
post-spawn guard, and the FDT gate accepted a missing memory.device_type,
prefixed compatible strings and zero GIC extents. The review's source-backed
Python reproductions and actual owned-process cleanup remain in its worktree
under `docs/reviews/vm-040/runs/lease-expiry-1` and `fdt-predicates-1`.
The original19-test pass did not detect these source-contract defects.

Root authorized minimal source fixes and focused host regression controls only.
Correction source freeze is `4f5fa223a85f510f9515da80c1a1b557a820ca35`, collector
SHA256 `341d813ca808cfdc9490a692dc4eb1261bf494c1964c19e4f653df130063bdc2`.
The collector now checks current resource admission, exact lease and Stop
immediately before Popen and retains post-spawn guards. Three admission samples
use only two inter-sample sleeps. The selected Linux FDT requires exact root
memory.device_type/RAM, complete terminated compatible-list tokens and the
full pinned QEMU GIC spans. Only the new worktree's authored fixture gained
memory.device_type; the original invalid physical fixture is unchanged.

VMBOOTCOLLECT-002/003 were registered before the focused runs. Lease regression
has four actual no-spawn rejection cases (late expiry/revocation/memory/Stop),
plus one real tiny Python spawn exiting0 without signals or survivors. The
admission-loop boundary is virtual time2 rather than the original trailing3.
FDT regression has13 source/byte predicate cases: two accepted source-valid
authored fixtures/lists and11 rejections, including the original frozen fixture.
One focused real Python peer exercised corrected paused Linux-FDT capture/cont,
with host-origin shutdown, guest_started=false and zero survivors. No full19
suite or original failing baseline matrix was repeated. Actual current-image
VmHWM was27,096KiB for lease controls and29,844KiB for FDT controls, both under
256MiB address-space limits. Virtual admission seams are explicitly labeled;
they do not create a root guest lease or an admitted image.

Raw capsules remain under this correction worktree:
`artifacts/avf-kernel-boot/lease-4f5fa22-1/evidence.json` SHA256
`af030005d05a00a4f68e6995f78abb624b1f325f512600e5832f52228960f110`, and
`fdt-4f5fa22-1/evidence.json` SHA256
`872a33cf0af56a5a7051fc4dc9c175a7b99e9a5ead6a828a6df4eb98700cd16c`.
Maintained copies are `lease-correction-evidence.json` and
`fdt-correction-evidence.json`. Canonical read-only lab.evidence schema checks
pass for both. `correction-validation-4f5fa22-1/report.json` records unchanged
original collector/evidence/raw-capsule/invalid-fixture hashes and exact reviewer
finding/reproducer hashes. Nothing in those historical physical witnesses was
rewritten to make the new checks pass.

The exact combined source/capsules were sent to vm_worker for independent
REV-037 recheck before further publication. The empty genuine-image allowlist
remains unchanged. No compiler, QEMU, phone, common checks or MAIN publication
ran; no actual QEMU FDT, XNU, PID1 or guest-stop qualification is claimed.
Original EH task remains open until independent acceptance, kernel integrator
publication and common checks. The following text preserves the original
source/control handoff as historical context.

## Original source/control handoff

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
