# REV-034 independent stop source and offline-observation review

Verdict: PASS for the bounded source/preflight/classifier contract. No actionable
finding within the reviewed immutable-input workflow. No actual XNU/kernel/PID1
shutdown, executed PSCI instruction, or native behavior is established.

Original review owner `codex-review-boot-gates-20261106-ed`; branch
`team/rev-boot-ed-20261106`, worktree `worktrees/rev-boot-ed-20261106`, base
`f22951619f2869adeea329f0ae1a7c3d8fdfc8a4`. Only `docs/reviews/vm-030` changes.
The review remains in progress until actual integration/common acceptance; only
this owner closes REV-034. Producer VM-030 ownership and VM-002 remain unchanged.

## Exact source and actual historical observation

Reviewed producer final `925080513827cd32d5ea36db386baaad81d9f5b7`, including
implementation `8ea3ea619f5e8b98c72c0410afce1ce40c1dd6ad`, evidence
`847150ada8b52fe5226dbb4cdb5e281af8bbcdf0`, and legacy-gate correction
`bc92b3c48cab58ba0252555384acc0536a918a14`.

| Producer input | SHA256 |
| --- | --- |
| `tools/build/avf_guest_stop.py` | `1c2dd72b2682b3ff8c45634626f4989d552f90eeafe04f5abe62aad3052582ee` |
| `fixtures/public/avf-guest-stop/inputs.json` | `4e0119b5a19502d0dfdbba8ea94ec4023fd953df18030d8a3580e907e272661f` |
| `docs/procedures/avf-guest-stop/evidence-final.json` | `30f97abcf05e9cd31c0b84048c0036fcaf33b361493ffa04a87afbe33609d912` |

All17 selected inputs and148 original artifact hashes match. Canonical source
and composed members bind XNU `c54f35ca767986246321eb901baf8f5ff7923f6a`, Scion
`a6f4bc38aa244359cd365c976244a88c9d6b3304`, exact genuine QEMU10.2.0 archive and
binary `bca8564182c786eb00e9f43c3153328f68e2edf50bfabe28236dbaac438acc11`.
Archive-to-Git equivalence/signature validation is not inferred. Source/member
identity is exact to the manifests, not private Apple ABI or complete image proof.
Original source component licenses remain in immutable trees; no source/binary
or SDK acquisition, build, guest or device operation occurs in this review.

Actual historical VM-027 files, relative to MAIN:

- `worktrees/vm-027-20261106/artifacts/avf-guest-device-tree/capture-1/report.json`,
 9944 bytes, SHA256 `02319a8a9c7de8f1fe1f9a3c10b35b24d51c4f4d095b4fd34d9830f9bc34d41e`.
- Sibling `console.log`,909 bytes, SHA256
 `41632a0e31625f322f819031a013f59463399ff6def2c265efbdbb8a0755af33`.

The report preserves a sent QMP `quit` and received
`SHUTDOWN {guest:false,reason:"host-qmp-quit"}`. The reviewer extracts received
event objects unchanged into `runs/review-2/actual-vm027-events.json`.
Those events plus actual console classify **inconclusive**, with
`guest_stop_observed:false`. The same actual events plus an explicitly authored,
favorable halt console still classify **inconclusive**. Other favorable supervisor
fields in these contrast controls are explicitly synthetic, not recovered runtime
facts. Thus this is an actual historical host-origin rejection, not new execution
or an invented genuine guest-stop positive. VM-027 ran a shim/synthetic spin
payload; its successful exit/tree capture does not become XNU/PID1 shutdown.

## Independent source assessment

The actual selected declarations support this narrow intended route:

1. Scion `avfboot.c:243–252` prints a fatal message, requests SYSTEM_OFF, then
   waits if it returns. This is shim failure, not kernel stop. Lines370–376
   select FDT HVC/SMC; line900 propagates the method into Apple DT.
2. Composed `psci_smp.c:195–213` defines SYSTEM_OFF0x84000008 and
   SYSTEM_RESET0x84000009. `psci_system_off()` reads `/chosen/psci-method`
   even for one CPU, fails when missing, selects HVC for `hvc`, otherwise SMC.
   CPU_OFF alone does not establish machine termination.
3. `machine_routines.c:744–759` invokes platform halt/reboot callbacks before
   loader-exit intent/return. `loader_return.c:611–647` requires no active loader
   return slot, honors `avf_exit=0`, selects panic-off before reset/halt, prints
   intent **before** calling PSCI, and prints firmware refusal if it returns.
   Source reachability can be prevented by earlier platform/debugger faults.
4. `kern_exit.c:1806–1849` routes initproc through critical-exit panic even for
   status0. The early expected prefix is `initproc failed to start`, later
   `initproc exited`; debug.c's loader-return path does not prove it executed.
   The new owned PID1 deliberately exits and therefore expects a panic stop,
   not normal OS shutdown. Its runtime syscall/initial-stack gates remain open.
5. QEMU `target/arm/tcg/psci.c:122–131` requests guest-reset/guest-shutdown for
   SYSTEM_RESET/SYSTEM_OFF. `system/runstate.c:691–702` turns reset into shutdown
   under no-reboot; qapi/run-state.json:136–161 provides independent QMP `guest`
   and `reason`. QMP guest origin is consistent with this path, not an instruction
   trace: other guest mechanisms can request the same shutdown cause.

The classifier requires one expected serial intent, one matching guest-origin
SHUTDOWN, exact stop-enabled args, running `-no-reboot`, before-deadline exit0,
no host signals and complete owned reaping. Firmware refusal, shim fatal,
conflicting/duplicate intents, wrong origin/cause, RESET/GUEST_PANICKED, and
unknown termination facts cannot pass. Forced deadline/signals classify host
cleanup. JSON bools and numeric fields use strict types; nonfinite JSON is
rejected. Identity plus exit0 alone is insufficient.

Full `assess` additionally binds confined runtime paths and hashes, reviewed
source descriptor and every input, supervisor/preflight hash and exact QEMU hash.
These are consistency checks over supplied records. Collector authenticity,
complete event capture and immutable trusted inputs remain external requirements;
this is not a hostile concurrent-writer sandbox or authenticated runtime trace.

## Replacement PID1 and next freed gate

The frozen descriptor still pins legacy `src/virtualization/pid1.c` and VM-025's
unchanged rejection evidence, sets `pid1_runtime_admissible:false`, and names
replacement VM-034. The actual full assessor **rejects** an otherwise ideal
synthetic identity/panic/QMP record before claiming a PID1 stop. Direct classifier
positive fixtures deliberately exercise future contracts only.

VM-034/REV-026 compiled acceptance does not silently change that frozen gate.
The next meaningful handoff is a **separately reviewed replacement stop descriptor
and source-to-image binding** for the accepted owned candidate, plus qualified
real kernel and loader/namespace/config inputs. A later root-leased collector must
capture genuine serial/QMP/supervisor records with exact hashes, finite deadlines,
signal history and no owned survivors. No new guest lease or complete kernel
admission follows from this review. Do not edit the old descriptor/witnesses to
relabel historical results. Root/INT002 were notified of this remaining gate.

## Measured controls, failure preservation and resources

Registered `REVSTOP-001` before execution. Independent `review.py` does not run
producer suites, compile, link, start QEMU, or edit any producer/physical witness.
Final `runs/review-2/report.json`: **358 checks and38 classifier controls PASS**,
174 input bindings, two real serial readonly child commands (frozen `git show`
and offline CLI legacy rejection), all reaped with expected exits0/2.

Focused controls include the actual host-QMP-quit rejection, synthetic halt/reset
and low-level PID1-panic contrast positives, integer guest boolean, wrong cause,
duplicate/reset/panic events, missing/truncated/conflicting intents, shim fatal,
firmware refusal, timeout/signals/live children, bool/negative/nonfinite/at-deadline
timing, paused/nonterminating argv and wrong boot args. Wrong canonical source
pin and composed member are rejected. Confined-path traversal/escaping symlink,
malformed event data, captured-data hash substitution, nonfinite JSON and full
legacy admission are rejected. All synthetic positives remain explicitly authored.
`psci_call_observed` remains false, even for a supplied guest-stop classification.

Actual controller VmHWM:47,468,544 bytes. Controller and children use the same
256MiB address-space cap; command deadline10s and outer120s. Each child has three
actual >=4GiB admission samples spaced>=1s; lowest14,468,071,424 bytes. This is
current-image HWM plus a virtual cap, not continuous aggregate RSS measurement.

First run `runs/review-1/report.json` failed **before classifier controls** after175
bindings/checks: MemoryError reading composition JSON under the reviewer's256MiB
AS cap. It omitted the producer's LC_ALL=C environment. ResidentHWM was27,246,592
bytes. Preserved `diagnostic-1.json` gives traceback and baselineVMS246264KiB;
standardmalloc `diagnostic-2.json` still fails. `diagnostic-4.json` measures this
process's default C.UTF-8 locale archive mapping of233,242,624 virtual bytes.
`diagnostic-3.json` with original LC_ALL=C passes the unchanged source preflight
under the **same cap**, residentHWM38,436KiB and baselineVMS18,124KiB. Final run
therefore restores the documented original environment; no budget increase or
producer fix was made. The initial failure is reviewer environment evidence,
not a producer defect. All failed/diagnostic capsules remain unchanged.

Scoped Git diff checks pass; common checks and publication belong to integrators.
