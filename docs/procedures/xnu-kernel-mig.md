# Selected kernel MIG generation

KRN-010; owner `codex-kernel-mig-20261105-u`, main at parent `b5d3953`.
The bounded selected MIG component passes. Full kernel/native iOS support is
incomplete. No phone command, SDK acquisition, global installation or old
source/build-prefix modification was performed.

The direct full recompile produces **864 actual arm64 objects**, including all
756 previous successes, 74 newly successful existing sources and all 34 selected
MIG sources. All 959 available source recipes were attempted. The 978 selected
component objects still have 114 unresolved entries: 95 compile failures and
19 missing non-MIG generated sources. Four additional top-level objects remain
unattempted, so 118 of 982 known direct objects remain unresolved. External
archive-member closure, symbolsets and final linking remain separate.

## Source and profile

Use the immutable KOBJECT-003 configuration/recipe inventory and
ATCOMP-004/007/009/010 compiler/object witnesses. The actual compiler is
`artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang`, SHA256
`c218fede38b771ead34b9cad47a4a79e53dc742f8864bb6bade2e0041bcc4dbe`.
All original allocator checks and compiler fixes are retained.

The public [MIG source](https://github.com/markmentovai/bootstrap_cmds/tree/f337e600741638896fb6056ce87c6479f74b89a3)
is pinned to `f337e600741638896fb6056ce87c6479f74b89a3` and built in HOSTGEN-002.
The selected [XNU source](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a)
is XNU8796.121.2 at `c54f35ca767986246321eb901baf8f5ff7923f6a`, with recorded
E1S donor patches and fixes. See [attribution](../../patches/kernel-mig/README.md).

The runner reads genuine `osfmk/conf/Makefile.template`, the generated
RELEASE/ARM64/E1S/iPhoneOS component Makefile, `MakeInc.def/rule/dir`, and all
eight actual `COMP_SUBDIRS` Makefiles. GNU Make expands their real MIG variable
lists and dry-runs each individual generation goal. No recursive build, installer
or full-build target is executed. Actual `CONFIG_DEFINES` is inherited from the
component's exported definition. The standalone host command shim replaces
macOS tool discovery with explicit recorded paths and an empty SDK path.

There are 80 distinct genuine invocations: 47 internal source/header pairs and
33 exported headers. They emit 94 internal and 33 exported files. All 34 selected
generated object sources map to these rules; the other 13 generated C sources
are explicitly unselected by this configuration and receive no compile claim.
The generated-input manifest retains every original goal/command association.

## Defects found and corrected

Kernel/internal and export headers can share a filename with different content.
A single generation directory overwrote these variants; KMIG-002 establishes
successful invocations, without qualifying a coherent final header set.
KMIG-003 uses separate `internal/osfmk` and `export/osfmk` trees and verifies all
127 output hashes after generation. Their preprocessing traces bind 53 actual
inputs, all inside this project. Original source/header/output prefixes remain
unchanged.

The generated Mach VM declaration conflict came from missing
`XNU_KERNEL_PRIVATE` during earlier generation. Genuine `mach_vm.defs` selects
`_mach_make_memory_entry` for this profile; `vm_map.defs` retains
`mach_make_memory_entry`. Their size pointer types are distinct C types even
when target widths agree. Regenerating the actual header with
`-UXNU_KERNEL_PRIVATE` reproduces the conflict; no hand-written declaration or
conditional suppression is used.

Include precedence also follows component visibility. `osfmk` uses its local
internal generated tree before exports. Importing components use exports first,
then the internal fallback. Placing internal `exc_server.h` first in IOKit
imports private IPC conversion headers without `MACH_KERNEL_PRIVATE`, producing
unknown IPC types. The corrected order retains each component's actual macros
and makes the real IOMemoryDescriptor source compile. Adding private defines
globally would not establish the original selected profile.

## Runner and reproduction

`tools/build/xnu_kernel_mig.py` verifies the full 10889-file compiler source,
198 original build inputs and 5111-file prepared kernel tree plus registered
HOSTGEN-002, KOBJECT-003, ATCOMP-004/007/009/010 and IIGABI-013 inputs. Original
KRN-004 headers/IDL and every prior owner's path remain intact.
Register a new KMIG experiment before execution and use a fresh run name:

```sh
python3 tools/build/xnu_kernel_mig.py --run NEW_GENERATION --mode generate
python3 tools/build/xnu_kernel_mig.py --run NEW_REPRESENTATIVES \
  --mode compile --generation-evidence KMIG-003 --selection representatives --jobs 2
python3 tools/build/xnu_kernel_mig.py --run NEW_FULL_PROFILE \
  --mode compile --generation-evidence KMIG-003 --selection all --jobs 2
python3 tools/build/xnu_kernel_mig.py --run NEW_HEADER_CONTRACT \
  --mode contract --generation-evidence KMIG-003
python3 tools/build/xnu_kernel_mig.py --run NEW_OBJECT_AUDIT \
  --mode audit --generation-evidence KMIG-003 --compilation-evidence KMIG-007
```

A newly generated run must be recorded under its own experiment ID before its
outputs can replace `KMIG-003` above. Old run directories cannot be overwritten.
Compile processes have 120-second timeouts and bounded groups; jobs are limited
to 1..3. This is host process control, not a phone watchdog/recovery guarantee.

`preprocess.py` executes the actual recorded source compiler, retaining its
full argv/cwd/exit, temporary input, preprocessed output and real dependency
hashes. The temporary input must exactly match MIG's `#line` plus the selected
.defs bytes. The only added preprocessing options collect dependencies.
The genuine MIG pipeline preserves preprocessor failure propagation. Any partial
output of a failed pipeline remains unqualified.

The full compile copies original expanded per-file recipes. Changes are limited
to the qualified compiler, explicit output/dependency paths, the mapped genuine
generated source when applicable, and mode-correct include roots. Old mixed-mode
MIG include roots are removed. Type checks stay enabled with
`-DXNU_NO_TYPE_BUILTINS=0`, with no compatibility constant header or blanket `-w`.
Every actual argv and exit is retained in the hashed full report; capsules label
any command sample explicitly.

## Evidence

| Experiment | Actual result |
|---|---|
| KMIG-001 | Fail: owned query reader initially failed to fold genuine multiline Make dry-run output; no generated ABI claim |
| KMIG-002 | Pass for invocation execution: all 80 commands run, but shared-mode overwrite makes this output tree unsuitable for coherent reuse |
| KMIG-003 | Pass: 80 genuine invocations, mode-separated 127 outputs, all 34 selected sources mapped, 53 real preprocessing dependencies |
| KMIG-004 | Fail: owned generated-source runner assumed implicit `-o` was explicit; some actual processes completed and remain recorded |
| KMIG-005 | Fail: six of seven representatives compile; internal server header precedence exposes private-type visibility errors in IOKit |
| KMIG-006 | Pass: all seven real representatives compile with component-correct include order |
| KMIG-007 | Pass for partial closure: all 959 recipes, 864 arm64 outputs, all 34 selected MIG sources, zero prior-756 regressions |
| KMIG-008 | Pass: actual declaration types/names; wrong size type, real regenerated missing-private-define header, and real CPP failure rejected |
| KMIG-009 | Pass: independent headers/symbols, all 959 exact recipe transformations and 2889 actual dependency files audited |

The seven representatives are `gssd_mach`, `host`, `task`, `mach_vm_server`,
`resource_notify_user`, `device_server`, `IOMemoryDescriptor`. All eleven original
units containing the Mach entry declaration conflict are retried by the complete
profile and no such conflict remains. All prior 756 successful objects are
rebuilt under the new header profile, rather than added to new counts.

The independent LLVM audit checks all 864 Mach-O arm64 headers and finds 15374
external plus 10696 local code definitions. It reconstructs the permitted
transformations of each original command, verifies exact selected source bytes,
associates each object with its actual dependency file, and rejects any consumed
header from the obsolete mixed-mode MIG roots. No compiler crashes/timeouts or
prior-success regressions occurred. Reuse requires matching compiler, command,
header and dependency bytes; a source SHA alone is insufficient.

## Published component and remaining work

The [generated-input component](../../fixtures/public/xnu-kernel-mig/qualified-component.json)
binds prefixes, tools, generator commands, per-mode file hashes and include
precedence. Full local prefixes are:

- `artifacts/xnu-kernel-mig/coherent-session1`: immutable generated input set.
- `artifacts/xnu-kernel-mig/full-profile-session1`: genuine full source compile.
- `artifacts/xnu-kernel-mig/object-audit-session1`: exact recipe/object/dependency audit.

The public [compiled objects](../../fixtures/public/xnu-kernel-mig/compiled-objects.json)
and [residual inventory](../../fixtures/public/xnu-kernel-mig/unresolved-objects.json)
are new manifests; parent KRN-008/009 manifests remain immutable.
The audit's `dependency-files.json` and `object-dependencies.json` bind all 2889
current input files and their object associations.

Remaining failed attempts are 90 missing headers, 3 deliberately unsupported
metadata layouts and 2 other source/profile errors. Missing headers are
`sys/sysproto.h`69, `assym.s`8, `libkern/version.h`5, `sys/syscall.h`4,
`os/firehose_buffer_private.h`3, `arm_neon.h`1. Metadata failures remain fixed
NEON vectors in status, C++ member pointers in MiniIOSurface, and reference
fields in IONVRAM. The other errors are mc_provider's printf macro/declaration
conflict and undeclared proc_pid in user_exception_trace. Two selected BSD
syscall C sources and seventeen selected IIG C++ sources remain unmapped in the
parent component build; existing separate IIG compile results do not qualify
that full recipe integration or private Apple ABI.

KRN-012 owns genuine BSD syscall generation next; KRN-011 owns bounded vector
metadata. Assym/version, compiler resource headers, firehose exports, selected
IIG integration, direct top-level objects and archive/link closure remain
separate work. This task establishes no live IPC correctness, full Apple compiler
or private ABI equivalence, native boot/recovery, iOS userland, GPU, Wi-Fi or
SIM/eSIM operation. Device scopes stay unchanged. Final repository validation
and bounded acceptance are recorded as KMIG-010.
