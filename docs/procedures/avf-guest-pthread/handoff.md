# VM-021 handoff

Owner: `codex-guest-exec-20261106-cy`. Branch `team/vm-021-20261106`.
Worktree: `worktrees/vm-021-20261106`, based on `aac27cf`.
Task remains in progress; source preparation does not satisfy fresh compilation.

## Result

AVFPTH-001 source preparation and source-plan rejection controls pass. Final
capsules are `artifacts/avf-guest-pthread/prepare-2/evidence.json` and
`artifacts/avf-guest-pthread/controls-2/evidence.json` in this worktree.
Preparation verified 206 genuine pinned Git source blobs and all 1869 immutable
guest installed headers, produced three fresh source recipes, and recorded
623 positive checks. Ten source-plan controls pass, including changed actual
source bytes, E1S profile, raw kext header fallback, historical archive input,
missing metadata-builtin selector, missing TU, forged compiled claim and changed
real callback declaration. No compiler, archive, guest or phone action occurred.

Exact libpthread revision: `a6c70ca0e544347a0377babf748f831577ec24f9`.
Existing patches 0002/0003 are applied only to owned copies; their hashes and the
public TargetConditionals source/patch 0001 provenance are in source-policy.json
and the evidence. The source tree retains all upstream component notices.
The development recipe uses native `MACH_ASSERT DEBUG`, BUILD_LTO off, BCM2837,
the installed kext namespace and genuine metadata builtins. Two retained symbol
remaps isolate pthread_kern/current_uthread for static component integration.

The raw source/installed table declarations match: 45 function and 96 callback
fields. The latter includes the ARM32-only `__unused_was_map_is_1gb` conditional
slot. This unpreprocessed 141 declaration surface is not a fresh ARM64 ABI count.
The three native export alias declarations are `_mach_vm_allocate` to
`_mach_vm_allocate_external`, `_mach_vm_map` to `_mach_vm_map_external`, and
`_vm_fault` to `_vm_fault_external`; actual guest provider/relocation equality
remains unmeasured.

## Actual checks and retained attempts

Both preparation invocations used `timeout 120s env LC_ALL=C PYTHONUTF8=1
PYTHONNOUSERSITE=1 python3 -s tools/build/avf_guest_pthread.py --main
/home/egor/dev/pet/s24-ios-exynos --out artifacts/avf-guest-pthread/prepare-N`.
Both exited 0. Both controls used `timeout 30s env LC_ALL=C PYTHONUTF8=1
PYTHONNOUSERSITE=1 python3 -s docs/procedures/avf-guest-pthread/verify.py --plan
artifacts/avf-guest-pthread/prepare-N/component-plan.json --out
artifacts/avf-guest-pthread/controls-N` and exited 0 with 10 controls.
The first pair remains preserved; the second adds exact Git/Python executable
hashes. Final preparation elapsed 0.193381s with actual current-process
/proc VmHWM 33384 KiB; controls elapsed 0.006245s with
VmHWM 20972 KiB. Child RSS was not sampled; these are controller
high-water readings, not aggregate process-tree measurements. Every source Git
command had a 30 s deadline and exit 0. No failed source preparation was discarded.
Expected rejection controls retain their actual rejection messages.

Early CLI/syntax and source declaration exploration were finite read-only
preflight checks, not compiler experiments. No common project check was run.

## Next gate

Kernel integrator `/root/lab_worker` and root receive the exact scoped commits,
public prepared descriptor, component argv plan and source witness hashes.
VM-022 owner `/root/guest_exec_01` can use the metadata but must preserve real
archive/member/undefined-symbol obligations as unmeasured. VM-009 owner
`/root/misc_worker` currently admits 1080 kernel rows only; provider compilation
will use its accepted `run_child` process API rather than a second engine.

Compile only after independent VM-008 namespace acceptance, VM-009 runner
acceptance, fresh registered compilation experiment and explicit root lease.
Then build all three real TUs, inspect genuine metadata/descriptors and actual
archive members, compare compiled full kernel/kext callback types/size/offsets,
measure actual guest provider closure, and link real native alias probes. Keep
failed attempts. No historical E1S archive or symbol closure can replace these.
Independent review and integrator acceptance precede original-owner taskdone.
Main publication/common checks belong solely to integrators under the shared
primary integration lock. No physical phone work is authorized here.

## Independent predicate finding and correction

Platform integrator cn independently verified the original source, retained
patches, installed headers and emitted development recipes. The original
`validate_plan` nevertheless accepted deleting both `-DMACH_ASSERT` and
`-DDEBUG` from every TU. The old ten controls did not detect this gate defect.
Neither the original source result nor that old predicate accepts compiled ABI.

The correction binds the full parsed plan to the independently committed
canonical hash in `fixtures/public/avf-guest-pthread/execution-plan-freeze.json`.
The original `prepare-2/component-plan.json` remains byte-for-byte unchanged,
SHA256 `96065bf4ebe697cfd1a0d43eb52d0ae315275f25efe619e60ae14d66ae350298`.
The canonical JSON hash is
`bfb88d88d6f44d936fd1fc5758b687ba29ca50f19626e6750224d6db2d69f475`.
The execution predicate rejects altered definitions, forwarding/response flags,
compiler/source/output changes and any other full-plan change. Generation's
old structural check is explicitly preparation-only and cannot admit execution.
Newly generated plans require an independently reviewed freeze.

AVFPTH-002 ran only the focused predicate controls described in
`predicate-review.md`: 21 checks pass, including an actual Git-read reproduction
of the original committed predicate's acceptance and corrected rejection.
The finite command exited 0, elapsed 0.018132 seconds, controller VmHWM
21,392 KiB. Source/header trees were not rehashed or regenerated. Original
`e884676` / `f10dda9`, source capsules and evidence remain preserved.
No compiler, QEMU, common check or publication occurred. Independent cn/root
recheck remains required; no compiled ABI or execution adapter is accepted.
