# AVF guest stop contract

VM-030 prepares source-bound stop admission and an offline log assessor. It
starts no compiler, QEMU, guest or phone operation. Actual guest PSCI execution
and a complete source-qualified XNU image remain unmeasured. All apparent guest
stops in the included controls are authored synthetic records.

The owner is `codex-guest-exec-20261106-dl`; branch `team/vm-030-20261106`, worktree
`worktrees/vm-030-20261106`, base `aac27cf`. Scope is this procedure directory,
`fixtures/public/avf-guest-stop/` and `tools/build/avf_guest_stop.py`. VM-002's
blocked namespace is unchanged. Integrators alone publish main and run common
checks under the shared integration lock.

## Exact source path

The committed [input descriptor](../../../fixtures/public/avf-guest-stop/inputs.json)
binds 15 existing inputs with streamed SHA256 and size. The genuine VM-007
composition and canonical source manifests bind the Scion pin
`a6f4bc38aa244359cd365c976244a88c9d6b3304`, public XNU pin
`c54f35ca767986246321eb901baf8f5ff7923f6a`, and the exact composed kernel members
with their Git blob IDs. No shared source or promisor cache is modified.

1. The genuine Scion `avf/shim/avfboot.c` reads the FDT PSCI method at lines
   370–376, defaults to HVC, uses SMC when specified, and writes the chosen
   `psci-method` into Apple DT at line 900. Its `die()` at lines 243–252 prints
   `avfboot: FATAL`, requests SYSTEM_OFF, then waits if firmware returns. A shim
   fatal stop is a distinct failure and cannot establish XNU or PID1 execution.
2. Composed `osfmk/arm64/psci_smp.c` lines 195–213 define SYSTEM_OFF
   `0x84000008` and SYSTEM_RESET `0x84000009`. `psci_system_off()` rereads
   `/chosen/psci-method` even with one CPU and returns -1 when absent; its call
   uses HVC for `hvc`, otherwise SMC. CPU_OFF stops one CPU and is insufficient
   evidence that the VM ended.
3. Composed `machine_routines.c` lines 744–759 route halt/reboot through platform
   callbacks, set `loader_exit_wanted(reboot)` and call `loader_return()`.
   `loader_return.c` lines 611–647 checks the empty loader return slot, honors
   `avf_exit=0`, prints one panic/halt/reset intent line and requests the chosen
   PSCI function. A panic wins over the reset flag. Firmware return prints
   `avf: the firmware refused to end the machine`; an earlier serial intent
   line is therefore insufficient to establish a completed stop.
4. The owned [PID1 source](../../../src/virtualization/pid1.c) verifies PID1 and
   `kern.ostype`, writes the VM002 identity marker and invokes Darwin `exit(0)`.
   Composed `bsd/kern/kern_exit.c` lines 1806–1849 route initproc through
   `proc_handle_critical_exit()` and `panic_with_options()` even for exit status
   zero. Before `kern.initproc_spawned` is set, the expected prefix is
   `initproc failed to start`; it is not a normal userspace shutdown. Composed
   `osfmk/kern/debug.c` lines 1162–1184 call `loader_return()` on panic/reboot
   paths. Some earlier faults/debugger behavior can still prevent reaching it.
5. QEMU 10.2.0 source `target/arm/tcg/psci.c` lines 122–131 turns PSCI reset/off
   into `SHUTDOWN_CAUSE_GUEST_RESET`/`GUEST_SHUTDOWN`. `system/runstate.c`
   lines 691–702 converts reset into shutdown when the reboot action is
   shutdown (`-no-reboot`), and lines 843–865 terminate the main loop after a
   shutdown request. QMP `SHUTDOWN` has separate `guest` and `reason` fields.

Primary sources are [pinned Scion](https://github.com/Scion-Project/hackios-xnu-kernel/tree/a6f4bc38aa244359cd365c976244a88c9d6b3304),
[pinned public XNU](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a)
and [QEMU PSCI](https://gitlab.com/qemu-project/qemu/-/blob/698104725efad4b29079d857dfdebbd804e34c99/target/arm/tcg/psci.c).
Local QEMU source is the independently hash-qualified official 10.2.0 archive,
SHA256 `9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`.
The Git tag commit was independently resolved in VM-004; archive-to-Git byte
equivalence/signature validation is not claimed. The exact source-built QEMU
executable hash is `bca8564182c786eb00e9f43c3153328f68e2edf50bfabe28236dbaac438acc11`.
Original component licenses and notices remain with the immutable source; no
upstream implementation or binary is copied into this commit.

## Admission criteria

| Observation | Classification |
| --- | --- |
| Exact stop-enabled boot args, running QEMU with `-no-reboot`, exactly one expected serial PSCI intent, one matching QMP `SHUTDOWN` with `guest: true`, exit zero before the finite deadline, no host signals and no live owned PID | Guest-origin stop evidence consistent with the bound PSCI path |
| For the PID1 case, Darwin banner followed by owned identity, critical-initproc panic and SYSTEM_OFF intent, plus all criteria above | Expected owned-PID1 panic stop evidence |
| Identity/serial intent appears, but timeout occurs or the host sends a signal | Host cleanup, regardless of exit zero or identity marker |
| Only exit zero/serial text, missing QMP or missing signal/reaping records | Inconclusive |
| Shim fatal, firmware refusal, host-origin or duplicate shutdown, reset loop, unexpected panic event, stale source/tool/log binding | Rejected or inconclusive |

`guest-stop` is an assessment of supplied observations, not a new measurement
by this program. QMP guest origin and console intent do not trace an executed
PSCI instruction. Collector authenticity, complete QMP capture and the binding
between a qualified kernel image and these sources require separate review.
No complete kernel is accepted by this tool and it grants no build/guest lease.

The existing VM-002 supervisor records a deadline flag and exit code, but does
not record QMP shutdown cause or exhaustive host signals/reaping. It can label
an identity-bearing console `observed` despite timeout. That legacy result must
not be promoted to a genuine guest stop. VM-030 changes none of those reserved
files. The common runner owner has been told the required telemetry contract.

## Use

Read-only source preflight, using the primary checkout as the artifact root:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 python3 -s tools/build/avf_guest_stop.py \
  --out artifacts/avf-guest-stop/NEW-preflight.json preflight \
  --root /home/egor/dev/pet/s24-ios-exynos
```

The offline runtime record schema is demonstrated by
`artifacts/avf-guest-stop/controls-2/synthetic-runtime.json` in this worktree.
It references console, QMP JSON event array, supervisor JSON and preflight JSON
using relative paths and exact SHA256. All paths remain under the record's
directory; traversal and escaping symlinks are rejected. The supervisor binds
the preflight and QEMU hashes and contains `guest_started`, `argv`, `boot_args`
and `termination` (`timed_out`, `host_signals`, `live_owned_pids`, `exit_code`,
`elapsed_seconds`, `deadline_seconds`). Missing facts remain unknown.

```sh
python3 -s tools/build/avf_guest_stop.py --out NEW-assessment.json assess \
  --record runtime.json --expected pid1-panic
```

`--expected halt` and `--expected reset` inspect distinct future stop cases.
Exit 0 accepts a source preflight or supplied guest-stop observation set;
exit 2 rejects it or records host cleanup/inconclusive status. Output paths
must be new to preserve previous attempts. JSON and console inspections are
bounded to 16 MiB each; hashing uses 1 MiB blocks. Current Python image VmRSS
and VmHWM are preserved in CLI reports.

Synthetic controls are executable without a build or guest:

```sh
LC_ALL=C PYTHONUTF8=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 python3 -s \
  fixtures/public/avf-guest-stop/controls.py \
  --root /home/egor/dev/pet/s24-ios-exynos \
  --out artifacts/avf-guest-stop/NEW-controls
```

The final scoped controls exercised 43 cases with a 256 MiB address-space cap;
current-image HWM was 40,292 KiB. Actual CLI source preflight passed, synthetic
artifact assessment passed, and a changed console digest was rejected with
exit 2. The preceding 38-case run remains as `controls-1`; it predates added
malformed-record and preflight binding controls and is not the final freeze.
Registered experiment VMSTOP-001 then exercised four actual negative Python
CLI invocations. Timeout with exit zero was `host-cleanup`, host-origin QMP was
`inconclusive`, and malformed QMP/unreviewed preflight failed; all exited 2.
Each invocation completed in less than 0.12 seconds with current-image VmHWM
at most 19,624 KiB under its inherited 256 MiB address-space cap.
See [evidence.json](evidence.json) and [experiment.md](experiment.md) for exact
commands, retained negative outputs and acceptance limits.

## Handoff

Independent review should inspect the 15 immutable bindings, source trace,
classifier's separation of guest origin and forced cleanup, and all retained
negative logs. The kernel integrator receives the scoped commit and evidence.
The original owner retains the task until review and integrator acceptance.
Future execution requires accepted VM-008 namespace, a qualified full guest
kernel and source-to-image provenance, explicit root resource admission and a
single-QEMU lease. Fresh main common checks remain an integrator operation.
