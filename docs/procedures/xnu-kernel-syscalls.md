# Genuine selected BSD syscall generation

KRN-012, owner `codex-kernel-syscalls-20261105-v`, main at parent `1d6f492`.
The bounded selected syscall component passes; full kernel/native iOS support
remains incomplete. No phone command, SDK acquisition, global installation or
original source/build/header-prefix mutation was performed.

The full direct recompile produces **939 real arm64 objects** from 961 actual
source attempts. All 864 prior successes remain successful; 73 formerly missing
sysproto/syscall consumers and both generated syscall C sources now compile.
The 978 selected component entries still have 39 unresolved items: 22 compile
failures and 17 missing IIG-generated sources. Four additional top-level direct
objects remain unattempted, so 43 of 982 known direct objects are unresolved.
Archive members, link metadata and the final kernel link remain separate.

## Actual source and generator rules

The selected [XNU8796.121.2 source](https://github.com/apple-oss-distributions/xnu/tree/c54f35ca767986246321eb901baf8f5ff7923f6a)
is pinned to `c54f35ca767986246321eb901baf8f5ff7923f6a`, with recorded E1S
patches/fixes. Read actual `bsd/kern/makesyscalls.sh`, `bsd/kern/syscalls.master`,
`bsd/sys/Makefile`, generated BSD RELEASE configuration and `MakeInc.rule`.
See [attribution](../../patches/kernel-syscalls/README.md).

The actual master-selection rule invokes qualified unifdef with **SEED_DEFINES
only**, retaining other conditionals for later C compilation. In this profile,
SEED_DEFINES is `-DXNU_NO_TYPE_BUILTINS=0`; the selected master retains its
configuration conditionals. Replacing this with a master preprocessed under
all CONFIG_DEFINES would change the original generator contract.

Real Make dry-runs identify four invocations of the original generator:
`table` creates `init_sysent.c`, `names` creates `syscalls.c`, `header` creates
`sys/syscall.h`, and `proto` creates `sys/sysproto.h`. Source/header outputs use
the same selected `bsd.syscalls.master`. Query-only metadata/cscope side effects
are retained in recorded recipes but are not executed in an old prefix.
The original Linux sh/sed/awk pipeline needs no source portability patch.

Two selected missing source objects map to these outputs. The already generated
`ioconf.c` is recorded separately and retained unchanged. The initial owned
mapping check included ioconf incorrectly; KSYSC-001 preserves that failure and
all four actually generated outputs. KSYSC-002 corrects the mapping and records
the syscall-specific caption/provenance without rewriting the first report.

## Compiler and recipe provenance

The compiler is `artifacts/xnu-compiler-atomics/atomic-arrays-session1/clang`,
SHA256 `c218fede38b771ead34b9cad47a4a79e53dc742f8864bb6bade2e0041bcc4dbe`.
Coherent internal/exported MIG roots remain the immutable KMIG-003 inputs.
Original input verification covers the 10889-file compiler source witness,
198 build inputs, 5111 prepared kernel files, HOSTGEN/KOBJECT/ATCOMP inputs and
KMIG-003/007/009/010. Existing owners and prefixes are preserved.

The previous KMIG-007 full recipes are reused exactly with new object/dependency
outputs and a new generated BSD include root. The two new syscall source recipes
come from their original selected KOBJECT-003 Make expansions and use the same
compiler/MIG/include profile. Type checks stay enabled with
`-DXNU_NO_TYPE_BUILTINS=0`; no compatibility constant header or blanket `-w`
is introduced. All available sources are rebuilt under the new header profile,
rather than reusing counts from a different include tree.

Register KSYSC experiments before execution; use fresh run names:

```sh
python3 tools/build/xnu_kernel_syscalls.py --run NEW_GENERATION --mode generate
python3 tools/build/xnu_kernel_syscalls.py --run NEW_REPRESENTATIVES \
  --mode compile --syscalls-evidence KSYSC-002 --selection representatives --jobs 2
python3 tools/build/xnu_kernel_syscalls.py --run NEW_FULL_PROFILE \
  --mode compile --syscalls-evidence KSYSC-002 --selection all --jobs 2
python3 tools/build/xnu_kernel_syscalls.py --run NEW_CONTRACT \
  --mode contract --syscalls-evidence KSYSC-002
python3 tools/build/xnu_kernel_syscalls.py --run NEW_AUDIT \
  --mode audit --syscalls-evidence KSYSC-002 --compilation-evidence KSYSC-004
```

A new generator run must be recorded before its own experiment ID can replace
KSYSC-002. `--generation-evidence` defaults to KMIG-003 and verifies those
immutable mode-separated files. Every actual argv/cwd/exit and full diagnostic
remains in the hashed report. Evidence labels any command sample explicitly.
Processes have bounded groups/timeouts; host jobs are limited to 1..3. This
provides no phone watchdog or measured native recovery.

## Actual controls and results

| Experiment | Result |
|---|---|
| KSYSC-001 | Fail: all four genuine outputs exist; owned mapping wrongly includes already generated ioconf.c |
| KSYSC-002 | Pass: original generator/master/SEED_DEFINES and exact two-source mapping, with conditionals preserved |
| KSYSC-003 | Pass: seven real full-recipe representatives including both generated C sources |
| KSYSC-004 | Pass for partial closure: all 961 available recipes, 939 arm64 objects, zero prior-864 regressions |
| KSYSC-005 | Pass: target layout/prototypes, actual dispatch/name/handler bytes, real mutations and malformed-source controls |
| KSYSC-006 | Pass: independent headers/symbols, all 961 recipe associations and 3054 actual dependency files |

Representatives are `bsd_arm64`, `vfs_syscalls`, `audit_syscalls`, `init_sysent`,
`kern_descrip`, `kern_exec` and `syscalls`. All 73 actual missing-header consumers
now compile. The independent full audit checks every arm64 header and finds
16927 external plus 11821 local code definitions. No compiler crashes/timeouts
or previous-success regressions occurred.

The source-backed target contract uses genuine generated declarations. With
selected CONFIG_REQUIRES_U32_MUNGING, read/open arguments occupy three 8-byte
slots. The real sysent record occupies 24 bytes; return type/argument-count/
32-bit argument-byte fields are at offsets 16/20/22. A real object exports these
layout values and SYS_MAXSYSCALL=556. The generated dispatch object's nsysent
agrees, and both tables contain storage for all 556 entries.

The bounded Mach-O reader resolves actual handler relocations and name strings
for read/write/open/close, checks their return classification and argument
slots/32-bit byte counts, and rejects a real count-byte mutation and a real
handler-relocation mutation. The layout compiler rejects a deliberately wrong
16-byte argument expectation. The original generator rejects a numbering gap
and a missing semicolon; real unifdef rejects an unterminated conditional with
exit2. Failed or partial output is never qualified. These selected checks do
not establish live syscall dispatch, munger execution, complete syscall semantics
or an Apple userspace/private ABI oracle.

## Component and next work

The [component manifest](../../fixtures/public/xnu-kernel-syscalls/qualified-component.json)
binds original generator/rule/tool hashes, selected master, generated outputs,
compiler/MIG parents, full compile and audit. Local prefixes are:

- `artifacts/xnu-kernel-syscalls/generate-session2`: selected master and four outputs.
- `artifacts/xnu-kernel-syscalls/full-profile-session1`: all 961 actual compile attempts.
- `artifacts/xnu-kernel-syscalls/object-audit-session1`: 939-object command/dependency audit.

Public [compiled objects](../../fixtures/public/xnu-kernel-syscalls/compiled-objects.json)
and [residual entries](../../fixtures/public/xnu-kernel-syscalls/unresolved-objects.json)
are new manifests; prior KRN-008/009/010 manifests remain immutable.
The actual dependency graph binds 3054 files. Reuse requires unchanged compiler,
command, header and dependency bytes; a source hash alone is insufficient.

The remaining 22 failed attempts comprise 17 missing headers, 3 deliberately
unsupported metadata types and 2 other source/profile errors. Missing headers
are `assym.s`8, `libkern/version.h`5, `os/firehose_buffer_private.h`3 and
`arm_neon.h`1. Fixed NEON vectors, C++ member pointers and reference fields remain
explicit metadata limits. mc_provider's printf macro/declaration conflict and
undeclared proc_pid in user_exception_trace remain separate source issues.
Seventeen selected IIG C++ sources still need full-recipe integration and matching
private ABI qualification under their existing owner.

KRN-013 owns actual assembly offsets and local version metadata next. KRN-011
covers bounded fixed-vector metadata. Compiler resource headers, firehose exports,
IIG integration, direct/archive/link closure, native boot/recovery, Apple userland,
GPU, Wi-Fi and SIM/eSIM acceptance remain separate. Device scopes are unchanged.
Final repository and bounded task acceptance are recorded as KSYSC-007.
