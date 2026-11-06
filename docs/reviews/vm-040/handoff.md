# REV-037 final independent VM-040 collector review

**PASS for the bounded collector source and host-control outcome.** Both P2
findings and the first-correction residuals are closed by the exact source below.
No remaining actionable finding in this reviewed scope. Genuine image admission,
XNU/PID1 execution and guest-origin shutdown remain unmeasured and unauthorized
by this report. Empty image allowlist and legacy VM030 rejection stay closed.

Review owner `codex-review-kernel-collector-20261106-vm037`, branch/worktree
`team/rev-vm040-20261106` / `worktrees/rev-vm040-20261106`; only
`docs/reviews/vm-040`. Review task remains in progress pending actual root/
integrator publication and fresh common acceptance. Only original reviewer closes.

## Exact reviewed source sequence

Original producer worktree `worktrees/vm-040-eh-20261106` remains unchanged:

- `d81bc09ba3123a37b2cc5d19497a1fe4720b0eab`
- `b309cae21e75aecea68f6c4ef01fdec3c430cd08`
- `9efba942901bf6457c4807ca91f61f5697ae48a2`
- `a0b64b31cceb6e4b0d3138628d4fed386d2fe2bc`

Its source SHA256 remains
`82dc4f31e0a43431e49741bc26368ff81c3820a21985a97fef82c11f6f9e6589`.
The original maintained evidence remains
`8262406bb0d684fba7e1b3e31b9cd1e6bad8fba347d968e2e04cbae1ad644083`;
raw19-control capsule remains
`08b82cb55c6d8dd593bfd28b8ae6bed95bf515e7967b2d633c8d23c508504271`.

Separate first correction `worktrees/vm-040-lease-20261106`:
`4f5fa223a85f510f9515da80c1a1b557a820ca35` + metadata
`a2ed73accaff1cbf61af4050fb1e9b7dd2ce7f48`.
Its physical source SHA256 remains
`341d813ca808cfdc9490a692dc4eb1261bf494c1964c19e4f653df130063bdc2`.

Final operative correction `worktrees/vm-040-consumer-20261106`,
`c8bd677b3280cf3610d2d1aa88dd6386a4e44a86`, based on that first correction:

**tools/run/avf_kernel_boot.py SHA256
`233da39b23ea8986e83db6bfdceb8f23c52b0c6ac044f7f1d5f30d451e145c06`.**

No producer file is edited by the reviewer. Original failures and witnesses remain
physical originals; initial `findings.md`, `evidence-initial.json` and first
correction review/evidence retain their historical changes-required outcomes.
They are superseded for final source acceptance, not rewritten or relabeled.

## Why the findings are closed

P2-1: immediately before Popen, the corrected primitive checks controller RSS,
current memory availability/PSI, exact lease through guard_extra, and Stop again.
It retains all live post-spawn checks. Admission now sleeps only between the
three samples. Source/resource/lease revocation after the final sample can no
longer pass solely on an old check before a one-second trailing sleep.

Independent final `final_recheck.py` uses the actual source's lease validator,
collect loop, Popen, monitor and cleanup, with explicitly injected host dependency
seams for unavailable image preparation, private ROOT/plan/queue and protocol.
These seams authorize no real image or guest. The only actual child is Python.
A controlled state change after sample3 exercises late expiry, lease revocation,
resource drop and Stop *during final lease validation*: each records **0 Popen**.
The valid case records **1** actual Python child, exit0, no signals or survivors.
Every case confirms exactly two admission sleeps. No QEMU or C execution occurs.

P2-2: the final FDT policy matches actual selected shim consumers for the
recorded counterexamples. It requires a direct-child memory type and excludes
root `/`, checks exact terminated compatible tokens, requires unique canonical
PL011 and GIC selections, rejects any exact ns16550a token globally (the shim
prioritizes8250), and verifies both complete GIC address/size pairs from pinned
QEMU. The peer fixture now includes the source-required memory device_type.

Fourteen independently authored/copied FDT cases pass their expected verdicts:
old invalid fixture, prefix/unterminated compatibility, zero/changed GIC spans,
wrong/root-only memory type, mixed/other8250 and competing PL011/GIC all reject;
valid direct memory child and a valid later compatible token pass. These are
source-property controls, not execution of C, the shim or a guest.

Source comparison is to actual frozen Scion `avfboot.c` and `fdtx.c`, not an
invented platform contract: memory iterates children; compatible matches whole
NUL strings; ns16550a precedes PL011; GIC sizes are propagated into Apple DT.
The final policy is conservatively narrower than generic FDT, for this exact
virt/GICv3/PL011 profile. No general FDT or hardware compatibility claim follows.

## Evidence and measured bounds

Prospective experiments: REVCOLLECT-001 initial FAIL (two P2s), REVCOLLECT-002
first correction FAIL (residual source cases/resource deferral), REVCOLLECT-003
final focused PASS. Failures were recorded before their successor experiments.

`runs/correction-c8bd677-1/report.json` SHA256:
`139f3f8dfcd0340f5d7975c2d6498587726aee22b7db0f41cac39ddc6876d327`.
Final recheck: **29 checks,5 process-admission cases,14 FDT cases,0 findings**.
Actual controller current-image VmHWM25,296,896 bytes;256MiB AS inherited by
children and stricter256MiB sampled RSS limit for the Python control. Real child
watchdog2s, outer120s. Three actual external resource samples per case, >=1s
apart with accepted PSI; lowest MemAvailable19,429,294,080 bytes. Actual samples
are now persisted *before* checking them. Virtual admission sleeps/lease clocks
are explicit test seams, not relabeled wall-clock or genuine-run observations.
No continuously measured aggregate RSS peak is asserted.

`final_bindings.py` performs101 read-only binding checks across original,
first-correction/final raw capsules, original reviewer index and source fields.
It also confirms that the final parser accepts the same valid input FDT bytes
captured by the first-correction Python peer. Those bytes have SHA256
`4cb04e5345fea0c987fd263870f8dcbbdaab35ac8f2476dcaec103e7784c5574`.
That actual peer event is still `guest:false/reason:host-qmp-quit`, guest_started
false, no signals/survivors. It was measured with source341d813, not source233da39;
only current parser acceptance is rechecked. No historical peer run is relabeled.

The earlier supporting independent review additionally passed76 checks/19
rejections/43 source/artifact bindings without running the producer's broad suite.
It covers empty allowlist/no child, source/helper/VM022 hashes, incomplete1080
lineage, exact full arguments, bounded paths/JSON/QMP, and conservative supplied
observation classification. Authored positive observations always retain kernel,
PID1 and PSCI-trace qualification false; actual host quit cannot become guest stop.

Read-only correction raw capsules, all rehashed:

- Lease `worktrees/vm-040-lease-20261106/artifacts/avf-kernel-boot/lease-4f5fa22-1/evidence.json`,
  SHA `af030005d05a00a4f68e6995f78abb624b1f325f512600e5832f52228960f110`.
- FDT `.../fdt-4f5fa22-1/evidence.json`, SHA
  `872a33cf0af56a5a7051fc4dc9c175a7b99e9a5ead6a828a6df4eb98700cd16c`.
- Final consumer `worktrees/vm-040-consumer-20261106/artifacts/avf-kernel-boot/consumer-c8bd677-1/evidence.json`,
  SHA `0da4671e19d14bd1df6f853a39425e3aa95c14996ff7bb51783a5530ba0a9d1e`.

## Preserved limitations and next actual gate

The operative program requires an exact committed image allowlist entry binding
independent descriptor review/root acceptance, real raw Mach-O and XNUP embedded
bytes, root/PID1/candidate/package, FDT/layout, source-to-link evidence and a NEW
image-bound paused/cont stop protocol. It rehashes ordered1080 sources, producer
objects, raw compile receipts/dependencies and link inputs. This is a future
complete-image admission route, not an available qualified image. Full admitted
prepare/execute remains unmeasured. Source checks cannot replace independent
complete link closure/transform/SDK/private-ABI/image review.

The final proposed append string is not the whole kernel command line: the
shim defaults/XNUP/FDT arguments must reconstruct the exact complete vector,
including debug/rd/kprintf/console flags, and match the printed single boot-args
line. Actual `-S` argv remains unchanged in legacy VM030 classification. A new
image-bound descriptor does not rewrite old witnesses or waive the legacy result.

Pre-cont memory is **Linux input FDT**. Only a later unique shim checkpoint can
support an optional source-derived paused **Apple serialized DT** capture; missing
or racing capture remains diagnostic/unmeasured. Host Python peers are protocol
controls, never proof that these transitions occurred in a genuine kernel.

Actual next gate: independently accepted genuine full image/source-to-link/root/
PID1/FDT/stop-protocol admission, exact plan and fresh root QEMU lease, followed by
a separately registered genuine collector experiment and independent serial/QMP/
supervisor assessment. Root/integrator review, publication and common checks are
still required for this source outcome. Reviewer ran no compiler, QEMU, common
suite, physical device operation or source/witness edit, and claims no real
Darwin/PID1/runtime MMU/timer/PSCI stop/iOS/S24 result.

Preparation/failed-review facts remain recorded: project-outside spec refusal,
initial reviewer indentation error before main, resource admission deferral before
any child with its exact rejecting sample missing from the initial reporter, and
actual source counterexamples. The subsequent /proc observation was labeled as
such, not substituted for that missing sample. Final reporter fixes that recording
order prospectively; none of these are misrepresented as a producer runtime fault.
