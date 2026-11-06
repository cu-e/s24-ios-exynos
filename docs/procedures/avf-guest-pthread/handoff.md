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

## Concrete four-command planning handoff

INT-003 independently rechecked the corrected predicate in source-only review
`01978b6`; the original plan and corrected complete-plan hashes matched.
Original owner registered `AVFPTH-003` as **planned**, timeout 720 seconds, on
2026-11-05T22:22:27+00:00. No compile or archive command has executed.

The proposed complete plan is `fixtures/public/avf-guest-pthread/compile-plan.json`.
It contains three exact frozen compiler argv arrays with only declared `-MF`/`-o`
placeholder substitution, followed by the genuine qualified cctools libtool
`-static -csD -filelist FILE -o` command. The frozen filelist contains exactly
`kern_init.o`, `kern_support.o`, `kern_synch.o` under the fresh absolute owned
`artifacts/avf-guest-pthread/compile-1` output. Every command uses that explicit
cwd. The output directory remains nonexistent; all product hashes remain null.
The original source plan and evidence capsules have not changed.

The selected accepted physical primary process module is now MAIN
`tools/build/avf_kernel_objects.py`, SHA256
`5c7b9c549e2740f3fad2a80c060e558dff3c9aa15e98bb2d9a56b33684e687d8`, at the
`12a43eef` common boundary relayed by INT-003 from cm. Actual source hash and
`run_child` AST equality to the earlier reviewed helper were checked. The old
physical VM-009 worktree hash `132135...` is explicitly historical/unselected.

The shared component execution adapter is missing and assigned to VM-036/dy.
The helper is insufficient by itself to enforce component/task/input/runtime/
output validity. Compiler ELF RUNPATH contains a literal backslash before
`$ORIGIN` and an empty entry; the future adapter must reject needed-library
shadows in cwd and relevant RUNPATH directories and verify actual loaded runtime.
Small `/usr/lib64` library candidates and genuine libtool bytes were streamed
through SHA256; candidate paths do not prove loader selection. No compiler,
loader, ldd or archiver was run. No source/header hash matrix was repeated.

`compile-planning-evidence.json` records only finite metadata consistency.
The plan stays proposed-not-executable until the actual VM-036 adapter and
input/runtime boundaries are independently reviewed and root grants a lease.
Each unit remains serial, one compiler maximum, combined RSS at most 256 MiB,
with the accepted helper's per-command admission and 120-second deadline.
Actual products, dependencies, Mach-O/metadata/members, callback ABI, native
alias/provider closure and all wider kernel/guest acceptance remain unmeasured.

## Original-owner accepted AF193 intake

Root permitted only new original-owner source-plan derivation after accepted
MAIN `27352788619e594314a1a85a12f07e82fc279184` / common 170 PASS. Original
owner cy registered new actual experiment `AVFPTH-004`; it remains **planned**
and has not been recorded as build PASS. The old AVFPTH-003 and historical
source/unit/filelist bytes were preserved.

One exact final physical adapter CLI child ran `--mode plan` with all original
task/owner/experiment flags, through accepted physical AF193 `run_child` with no
budget/approval CLI flags. It exited 0 in 3.778310 seconds.
The three admitted MemAvailable samples were
17269317632, 17200558080, 17825230848 bytes.
Sampled combined controller/owned-child peak was 112533504
bytes, below 256 MiB; no owned process survived. No compiler or archiver ran.

New plan: `artifacts/avf-guest-pthread/derived-af193-1/plan/execution-plan.json`,
SHA256 `288b255bfb5d38798a6889a7569596e5f04401752f3230e60c470017cbaa94bc`; canonical JSON SHA256
`5cab47a4a445f606fe2eb0ad15c814265e655311a6083b583c48ee51249d4279`.
Sibling input bindings SHA256 `683311bdafbd5d9c5b33462bb4ab7dc14eb5840944c31327b0dea731319ec44f`.
The derived files bind final adapter `e62d7592...`, policy `748db1c0...`, and
physical VM039/ej AF193. They happen to match the prior reviewer-owned plan
bytes; this intake was nevertheless generated through the actual original-owner
CLI under the new planned experiment, without copying old review artifacts.

`derived-af193-evidence.json` gives exact artifact paths/hashes, command/exit/
resource evidence and the future execute argv template. The actual future
component product output remains `artifacts/avf-guest-pthread/compile-1` and is
absent; product hashes remain null. Future execute uses this same physical
adapter, original VM021/cy/AVFPTH-004 flags, output compile-1, and root's later
exact `--approval` / `--approval-sha256` values. No approval is invented here.

Root must intake both new original-owner component plans and grant the later
serial compiler allocation before any execute invocation. No loader, QEMU,
common check, publication or budget044 repin was performed. All compiled ABI,
provider/member/dependency/layout/alias and wider kernel acceptance remain
unmeasured. Task VM-021 remains in progress under the original owner.

## Immutable future actual-request launcher

Root supplied the immutable in-process launcher
`artifacts/team-coordination/20261106-team/in-process-component-launcher-e62d7592-600.py`,
SHA256 `abb67ea94a25dfb1da7ff1a49c1c65162516b082408bf72918875b3531cfe872`.
`derived-af193-future-request.json` records the future argv with that launcher
inserted before the exact physical adapter target; every adapter flag stays
unchanged. Whole deadline is 600 seconds, child deadline 120 seconds, one serial
component and exact combined controller/tree RSS limit 256 MiB. Root clarified
that the earlier general 512 MiB cap does not lift the adapter's 256 MiB check.
No policy/source/plan changes or regeneration were performed. This metadata
contains unfilled root approval placeholders and grants no actual execution.
The original source proof and new actual AVFPTH-004 planned state are retained.

## Actual SERIAL22 pthread build

Root issued the separate actual START only after firehose terminated and cleaned
its owned processes. Original cy launched AVFPTH-004 through the immutable
600-second launcher, exact physical e62 adapter and SERIAL22 approval. Real
executor PID/SID was 3563933; tool session 13430 exited 0. No source was changed
or compiler command retried. The execution output now exists.

Raw `artifacts/avf-guest-pthread/compile-1/evidence.json` SHA256
`30f1c8f800c36640ee716879d06717d351b87911d5835ad7e8cf50842e244514` records PASS for all eight actual
processes: four trusted-loader resolutions, three genuine fresh TU compiles and
one genuine cctools archive. Each exit was 0; every child owned-after set was
empty and no project-after/budget error occurred. Elapsed 22.581591
seconds; sampled combined controller/tree peak 159739904 bytes. Actual
controller /proc HWM was 91754496 bytes. The much larger inherited rusage
value is explicitly not a current-image measurement.

The actual archive is `compile-1/libpthread_kext.a`, SHA256
`75953383eecc86d0a3422a3f5d7c4776e841f466cc5419e4063a51c94bdd88fd` (50584 bytes), with exactly
kern_init.o, kern_support.o and kern_synch.o in that order, matching fresh object
bytes. Actual depfile counts are 265/328/315 (332 unique dependencies),
with target/source identity and hashed input closure checked by the accepted
adapter. kern_synch.o has a real 128-byte `__DATA_CONST,__kalloc_type` section.
There are 39 external definitions and 65 real external imports, including genuine
DEVELOPMENT debug obligations. No provider or native-alias resolution is inferred.

`fixtures/public/avf-guest-pthread/built-component.json` pins actual objects,
depfiles, ordered member hashes, definitions/imports, runtime-resolution records
and cleanup evidence. `actual-build-evidence.json` is the conventional command
wrapper for original-owner experiment recording. All original raw plans, units,
filelists and historical source evidence remain unchanged.

Readonly reservation observation found VM-021 status complete under the exact
SERIAL22 allocation. ps found no executor or any of its eight child/session
PIDs. The worker did not modify/release the global root lease. Independent
product review, integrator acceptance and applicable common checks remain
required before taskdone. Callback/alias ABI, full metadata semantics, real
guest provider/full kernel closure, guest boot and native-device results remain
unqualified. No QEMU, phone operation or main publication occurred here.
