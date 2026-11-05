# Target atomic metadata and selected object coverage

KRN-009, owner `codex-compiler-atomics-20261105-t`, main at parent `ad1b90b`.
The bounded compiler component passes; the full kernel/native goal is incomplete.
No phone command, SDK acquisition, global installation or original build-prefix
mutation was performed. Reports and maintained text are English.

The new compiler directly recompiles **756 of 925 existing-source recipes**,
including all 679 prior successes and 77 previously failing genuine units.
The 978 selected component objects still have 222 unresolved entries: 169 compile
failures and 53 missing generated sources/recipes. Four additional top-level
objects remain unattempted, so 226 of 982 known direct objects are unresolved.
External archive-member closure and final linking remain separate.

## Source and actual defects

Public LLVM/Clang 17.0.6 is pinned to
[`fa9443738c1a18accef4244732ec6d6ee97a8133`](https://github.com/tpoechtrager/apple-libtapi/tree/fa9443738c1a18accef4244732ec6d6ee97a8133).
The selected XNU 8796.121.2 base is
[`c54f35ca767986246321eb901baf8f5ff7923f6a`](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a),
with E1S donor patches at
[`c8860decc62c6d6180e609036d027a2997972420`](https://github.com/RNDMBG/iOS-On-S24/tree/c8860decc62c6d6180e609036d027a2997972420).
The actual public source and all parent compiler fixes remain intact.

`AtomicType::getValueType()` supplies the value type. `ASTContext.cpp` starts
atomic type info from value width/alignment and can promote storage to a power
of two. `CodeGenTypes.cpp` lowers the value at offset 0 with extra tail padding.
A 12-byte three-word record occupies 16 bytes atomically; a subsequent pointer
starts at 16. Clang 19 independently agrees with these target sizes/alignments,
including packed/misaligned cases. The source files are in the pinned local
compiler tree and listed in `research/sources.json`.

Patch0001 unwraps atomic values while checking actual storage extents. It
preserves target field offsets and classifies extra storage as padding. Typedef
and field annotations survive sugar/atomic wrappers; an explicit field annotation
wins over the underlying typedef. Unsupported categories stay rejected.

Two further defects emerged through actual compiles:

- The custom Parser branch returned before the ordinary postfix-expression
  path. Direct `__builtin_xnu_type_signature(T)[0]` failed. Patch0002 joins the
  existing postfix parser; fixtures retain direct builtin expressions.
- ARM locks contain `uintptr_t opaque[2] __kernel_data_semantics`. The old helper
  rejected annotated arrays. Patch0003 propagates explicit scalar semantics
  through constant-array elements, including nested arrays and atomic scalars.
  Annotated records remain rejected.

These experimental public-source allocator rules have no private Apple compiler
oracle. See [patch attribution](../../patches/compiler-atomics/README.md).

## Build and provenance

`tools/build/xnu_compiler_atomics.py` verifies the 10889-file compiler source
witness, 198 original build inputs, 5111-file prepared kernel tree, and
HARDEN-002/005, KCONFIG-005/006, KOBJECT-003/004 evidence. Register an experiment
before each execution and use a fresh run name. Preserve original prefixes.

The successful ATCOMP-004 prefix is
`artifacts/xnu-compiler-atomics/atomic-arrays-session1/`.
Its `clang` SHA256 is
`c218fede38b771ead34b9cad47a4a79e53dc742f8864bb6bade2e0041bcc4dbe`.
The [component manifest](../../fixtures/public/xnu-compiler-atomics/qualified-component.json)
binds compiler, patches, copied archives and actual source consumers.

All 3 actual helper consumers were rebuilt with their original CMake argv:
`SemaExpr.cpp`, `SemaExprCXX.cpp`, `ExprConstant.cpp`. GNU unevaluated-void and
AST constant-evaluator fixes were retained. `ParseExpr.cpp` was also rebuilt
with the retained type-only builtin parser and new postfix fix. Objects were
inserted into copied Sema/AST/Parse archives; extracted member hashes match.
The recorded relink retains the AST mangler and other archive inputs. No
mutating Ninja was run in an original build prefix.

After registering a new experiment, use a fresh run:

```sh
python3 tools/build/xnu_compiler_atomics.py --run NEW_BUILD \
  --mode build --array-semantics --postfix --kernel-cases --jobs 2
```

Fixtures are copied into each new run. Reports retain actual argv/cwd/exits,
diagnostics, source/object/dependency hashes and compiler identity. Evidence
capsules explicitly label command samples; the hashed report retains every
execution. Failed evidence retains its original bytes/fixture snapshots.

## Measurements and regression controls

| Experiment | Result and scope |
|---|---|
| ATCOMP-001 | Fail: independent target layouts agree; original plain/atomic metadata discrepancy reproduced |
| ATCOMP-002 | Fail: all 3 helper consumers rebuilt; direct builtin postfix defect and incomplete owned allocator fixture exposed |
| ATCOMP-003 | Fail: Parser corrected, actual allocator metadata passes,17/80 genuine units compile; old PCH whole-file comparison rejects legal function reordering |
| ATCOMP-004 | Pass: fresh atomic/array/Parser rebuild;77/80 formerly failing units compile; all atomic controls pass |
| ATCOMP-005 | Pass: retained seven profile cases, six negatives, three actual allocator records plus mutations,17 selected IIG source compiles |
| ATCOMP-006 | Pass: retained C/C++ PCH, SFINAE, separate-TU symbol agreement, wrong-target/truncated/foreign-PCH rejection |
| ATCOMP-007 | Pass for partial coverage: all 925 genuine full recipes retried; 756 ARM64 objects, zero prior 679 regressions |
| ATCOMP-008 | Pass: actual selected filtered ASTs and isolated negatives confirm vector/member-pointer/reference limits |
| ATCOMP-009 | Pass: independent LLVM headers/symbols and exact 925 recipe audit; 2702 current dependency files hashed |

Atomic controls distinguish pointer/data/mixed granules, promoted aggregate
storage, padding, packed records, arrays, unions and annotation precedence.
The genuine selected `kern/kalloc.h` object has 16-byte records with signatures
`12`, empty(data-only), `11` and flags `0x61`, `0x69`, `0xe1` respectively;
strict layout/relocation validation remains enabled. The host raw-AST harness
exercises actual atomic summary 2/4 and signature 1/2 through newly linked
archives, without ARM execution.

The atomic PCH fixture serializes annotated types and dependent template
expressions, then instantiates new types after loading. Textual/PCH objects
legitimately place functions in a different order. The fixture-specific check
requires exactly one nonempty text section and three code definitions, compares
exact bytes per named function and normalized call relocations, and rejects a
real code-byte mutation and a real relocation-target mutation. Whole-file
inequality remains recorded. Ordinary retained PCH controls independently stay
byte-identical. The vendor expression demangles and retained separate-TU
symbols agree; private Apple mangling/foreign AST schemas remain unqualified.

## Recompile and audit handoff

The full 925-recipe prefix is
`artifacts/xnu-compiler-atomics/full-existing-profile-session1/`.
Only compiler, object and dependency-output paths change from KOBJECT-003
argv/cwd. Type checks remain enabled with `-DXNU_NO_TYPE_BUILTINS=0`; no constant
compatibility header or blanket `-w` is introduced. Genuine restartable, SMR
and CoreAnalytics now compile.

Register fresh experiments before these commands:

```sh
python3 tools/build/xnu_compiler_atomics.py --run NEW_FULL_PROFILE \
  --mode audit --compiler "$PWD/artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang" \
  --compiler-evidence ATCOMP-004 --kernel-cases --all-existing --jobs 2
python3 tools/build/xnu_compiler_atomics.py --run NEW_TYPE_DIAGNOSIS \
  --mode diagnose --compiler "$PWD/artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang" \
  --compiler-evidence ATCOMP-004
python3 tools/build/xnu_compiler_atomics.py --run NEW_COVERAGE_AUDIT \
  --mode coverage --compiler "$PWD/artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang" \
  --compiler-evidence ATCOMP-004 --coverage-evidence ATCOMP-007
```

The independent audit prefix is
`artifacts/xnu-compiler-atomics/object-audit-session1/`.
`dependency-files.json` binds 2702 actual inputs; `object-dependencies.json`
maps each object to them. LLVM verifies all 756 arm64 headers and finds 12414
external plus 9344 local code symbols. No crashes, timeouts or prior-success
regressions occurred. Reuse requires exact compiler/header/command/dependency
bytes; source SHA alone is insufficient after changing compiler/include roots.
Public [compiled objects](../../fixtures/public/xnu-compiler-atomics/compiled-objects.json)
and [unresolved entries](../../fixtures/public/xnu-compiler-atomics/unresolved-objects.json)
are separate from immutable parent KRN-008 manifests.

## Remaining causes and next work

Of 169 failed attempts, 155 encounter missing headers, 3 unsupported metadata,
and 11 other errors. Another 53 generated sources/recipes are absent.
Selected ASTs and source review establish these remaining metadata paths:

| Object | Remaining cause |
|---|---|
| `osfmk/status.o` | `arm_act_context.ns.uns.ns_64.v` includes fixed `ext_vector_type(2/4)` arrays; fixed vectors lack helper support |
| `iokit/MiniIOSurface.cpo` | `IOSurfaceRootUserClient.fTraps[].func` is `IOTrap`, a C++ member function pointer; deliberately rejected |
| `iokit/IONVRAM.cpo` | Both `IONVRAMCHRPHandler._varDict` and `IONVRAMV3Handler._varDict` are reference fields; deliberately rejected |

Other errors include nine `mach_make_memory_entry` declaration conflicts,
`mc_provider`'s `printf` macro/declaration conflict and undeclared `proc_pid` in
`user_exception_trace`. Missing headers are led by `sys/sysproto.h` 69,
`mach/resource_notify.h` 31, `mach/mach_host_server.h` 8, `assym.s` 8.
Full errors remain in bound logs and the residual inventory.

Continue KRN-010 with genuine selected MIG generation and ABI/header tracing.
New vector/reference/member-pointer support needs separate target-layout,
semantics and negative controls before further qualification. Preserve the 1 MiB,
131072-element and 128-depth bounds and PAC/arm64e, virtual-base, VLA/scalable
and annotated-aggregate limits. This component establishes no final kernel
link, native boot/recovery, Apple userland, GPU, Wi-Fi or SIM/eSIM support.
Final repository validation and acceptance are recorded as ATCOMP-010.
