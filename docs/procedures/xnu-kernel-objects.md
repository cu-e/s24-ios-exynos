# Selected E1S kernel object closure

KRN-008; owner codex-kernel-objects-20261105-s; main at ae79e6f.
KRN-008 remains in progress. KRN-007 and this turn both made concrete host
progress. All recorded build/audit sessions are terminal; no prior running build
is being restarted. Complete kernel/native iOS GPU/display/Wi-Fi/SIM/eSIM/
userland acceptance remains unqualified.

## Actual component coverage

All eight original component configurations and GNU Make queries execute.
The actual component OBJS selection contains978 entries. All925 entries with an
existing source and compile rule were attempted;53 generated sources are absent.
The corrected run produces679 real thin arm64 Mach-O outputs and246 actual
compile failures. No compiler process crashed or timed out.

| Component | Selected | Actual ARM64 objects | Compile failures | Missing generated sources |
|---|---:|---:|---:|---:|
| osfmk | 300 | 175 | 91 | 34 |
| bsd | 464 | 331 | 131 | 2 |
| libkern | 77 | 75 | 2 | 0 |
| iokit | 102 | 65 | 20 | 17 |
| pexpert | 11 | 11 | 0 | 0 |
| libsa | 1 | 0 | 1 | 0 |
| security | 23 | 22 | 1 | 0 |
| san | 0 | 0 | 0 | 0 |

san has no objects selected by this RELEASE configuration. Its header exports
still participate in the actual source dependency closure.

KOBJECT-005 independently checks all925 original command/source associations,
type checks enabled, absence of the old constant compatibility header/blanket
-w, actual679 object digests and source hashes. Independent LLVM header and
symbol readers inspect every successful output:9478 external and6905 local
code symbols are defined. This is emitted code, with no ARM execution.

The same audit captures2598 unique actual dependency-file paths/hashes and the
per-object .d associations. Keep that graph for conservative cache invalidation;
new generated include roots can change header resolution, so a source hash alone
cannot justify reusing an old object under a new compiler/header profile.

## Broader kernel requirements

978 is the component count, not the final kernel's complete direct/link input
count. Source-bound KOBJECT-006 traces four additional direct objects in actual
MakeInc.kernel: nonlto.o, version.o, lastkerneldataconst.o and
lastkernelconstructor.o. They remain unattempted in this turn. The known direct
object inventory therefore has982 entries, with679 built and303 unresolved.
Archive members are additional inputs whose total is not established here.

Actual link expressions still require cc_kext, firehose_kernel, pthread_kext,
all-kpi.exp, all-alias.exp and symbolsets.plist. The prior component archives
remain separately qualified; this turn does not qualify a complete kernel link,
symbolsets, selected private ABI or SDK closure. Optional external REDWOOD_OBJECTS
are not supplied by this standalone profile. Source recipes also require
genassym/assym and relevant object segment processing before a final link.

See the [pinned public kernel link rules](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.kernel).
The prepared-tree witness binds the actual locally selected rules and patches.

## Exact observed failures and next actions

The246 genuine failed compiles separate into155 missing-header cases,80 cases
with unsupported metadata errors and11 other compiler errors. This is a
primary-cause grouping; one source may have further issues after the first fix.
The independent AtomicType control does not prove all80 metadata cases have
the same cause.

Most missing-header cases involve generated sys/sysproto.h (69),
mach/resource_notify.h (31), mach/mach_host_server.h (8), assym.s (8),
mach/host_priv_server.h (6) and libkern/version.h (5). Others include syscall,
firehose, user-notification and MIG server/client declarations. Full diagnostics
and the per-object unresolved manifest are retained; do not invent replacements.

KOBJECT-004's freestanding C11 layout pair compiles ordinary pointer/data
metadata, but the equal-storage _Atomic pair fails the actual metadata helper.
Actual os_ref_atomic_t uses _Atomic, and the failed restartable/SMR/analytics
callers provide concrete kernel cases. KRN-009 owns source-backed atomic
analysis with target layout expectations and the compiler regression profile.
Every consuming Sema/AST translation unit must be rebuilt in fresh archives;
do not edit the old helper/compiler prefix or replace signatures with constants.

KRN-010 owns genuine selected MIG sources/headers and matching .defs/component
flags. Conflicting mach_make_memory_entry declarations occur in11 failed source
units, including units with further metadata errors. Coherent generation must
address those actual callers. Additional
parent work covers BSD syscalls, version/assym, missing firehose source exports,
matching selected IIG sources and the remaining source/profile diagnostics.
The existing KRN-004 IIG owner and private ABI limits stay unchanged.

Verify KCONFIG-005/006, HARDEN-002/005, HOSTGEN-002 and IIGABI-013 before reuse.
The selected source is Apple XNU8796.121.2 c54f35ca767986246321eb901baf8f5ff7923f6a
plus E1S donor c8860decc62c6d6180e609036d027a2997972420 and the recorded fixes.
Keep the complete prepared-source/compiler/build witnesses unchanged.

The [pinned Linux donor](https://github.com/oosexgang/hakios-xnu-kernel/blob/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c/xnu-build.sh)
at d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c explicitly
sets ARCH_STRING_FOR_CURRENT_MACHINE_CONFIG=arm64, BUILD_WERROR=0 and BUILD_LTO=0
in xnu-build.sh. Record those source-backed choices. Its old xnu-clang wrapper
also forces a compatibility header/constant fallbacks and blanket warning
suppression; do not execute that wrapper. Use the already qualified actual
source compiler with XNU_NO_TYPE_BUILTINS=0 and retain actual diagnostics.

Generate all eight actual RELEASE/ARM64/E1S/iPhoneOS component configurations
with original doconf and the recorded generator. A standalone Linux command
environment supplies explicit compiler/host/deployment paths for GNU Make
queries; no SDK contents or private declarations are supplied by that adapter.
Read original MakeInc.def/rule/dir and generated component Makefiles through
query-only targets. Never execute upstream install/flash/full-build targets.

SOURCE is the actual component source directory when querying a generated
component Makefile. The independently inventoried prerequisite basename supplies
Make's recipe-only <F context; real GNU Make expands the actual rule variables,
per-file flags and extras. Before execution, the runner rejects a recipe whose
input differs from its inventoried source and refuses zero-exit/no-object output.
The three real full-recipe preflight controls pass before broad execution and
are not compiled twice in the same run.

Derive the complete object/source selection and each actual expanded C/C++/
assembly rule, including per-file flags. Query real export lists recursively
through their MI/ARM64 traversal. Byte-copy genuine existing exports into fresh
paths, recording generated/missing declarations explicitly. No guessed headers.

Keep an explicit status for every selected required object, including missing
generated inputs, absent/shell recipes, assembly dependencies and real failures.
A partial compile set does not complete KRN-008. Capture actual commands/exits,
source/config/tool/dependency/output hashes and exact diagnostics. Further
compiler/generated-header outcomes may need narrow child tasks in new paths.

Actual recursive MI/ARM64 export queries copy976 genuine existing headers
byte-for-byte.75 generated-export declarations remain explicit; this is not a
claim of complete exported-header closure. Additional include roots are the
already witnessed target/IIG/MIG/public source roots, with no new SDK contents.

No phone command, APK, root, SDK/firmware acquisition, reboot/flash, global
package/header/compiler modification or other owner's path change is authorized
by this procedure. Native/device scopes stay unchanged.

## Reproduction and handoff

Register KOBJECT experiments before execution. Fresh runs only:

    python3 tools/build/xnu_kernel_objects.py --run fresh-inventory

Run full current component coverage with mandatory recipe controls:

    python3 tools/build/xnu_kernel_objects.py --run fresh-component-build \
      --compile --preflight --jobs 2

Incomplete coverage returns1 and retains an inconclusive report. Each attempt
has120 seconds; host jobs are limited to1..3. Core dumps are disabled; a timed-out
host process group is terminated. No hardware watchdog/recovery is implied.
For the distinct direct-kernel/archive requirements only:

    python3 tools/build/xnu_kernel_objects.py --run fresh-link-inputs --top-only

## Preserved experiments and current state

| Experiment | Actual result |
|---|---|
| KOBJECT-001 | Inconclusive: all8 configurations,978 component entries,976 source exports and75 generated declarations; no compile qualification |
| KOBJECT-002 | Inconclusive runner failure: Make-query automatic <F context omits source basenames; no genuine compiler coverage can be inferred from its925 zero-exit/no-object attempts |
| KOBJECT-003 | Inconclusive component closure: corrected source context, three preflight controls,925 actual compiler calls,679 ARM64 objects/246 failures/53 absent generated sources |
| KOBJECT-004 | Fail: independent plain metadata passes, actual atomic metadata is unsupported |
| KOBJECT-005 | Pass for partial-coverage audit only: independent headers/symbols/commands/dependency graph; KRN-008 stays incomplete |
| KOBJECT-006 | Inconclusive: four additional direct top-level objects and external link expressions are bound to actual source; no new object compiled |

The original failed source-context run is immutable. Its errors are an owned
runner defect, not evidence of unsupported kernel code. Later runs and checked
object existence correct the measurement. Complete actual argv/exits remain in
hashed local report.json; ledger capsules label their representative command
samples explicitly, avoiding repetition of the full kernel command database.

Use fixtures/public/xnu-kernel-objects/progress-component.json and its compiled/
unresolved manifests to resume. The partial component is not named or treated as
a completed whole-kernel qualification. KOBJECT-007 records final repository and
immutable-input checks; it cannot complete the missing object/link/hardware work.

Before resuming a new build, verify recorded capsules and source/object/dependency
digests. Do not modify compile-session2, overwrite its configs/exports/reports, or
restart an old completed process. Parent work stays owned by
codex-kernel-objects-20261105-s. Independent ready compiler/MIG tasks have new
literal boundaries; no other owner is reclaimed. The full goal stays active and
no external input is needed to start those safe host steps.
