# Genuine kernel firehose header exports

KRN-014, owner `codex-firehose-headers-20261105-y`, parent `545cfb9`.
The bounded header component passes. Work is host-only; Android and native
scopes remain unchanged, and no phone command was issued.

The complete current profile now produces **956 component objects plus version.o:
957 known direct ARM64 objects**. All 962 available source recipes were retried,
retaining every prior 954 successful direct object. The genuine full recipes for
bsd/subr_log.o, libkern/OSKext.cpo and libkern/log.o now compile. Twenty-two of
978 component entries remain unresolved: five compiler failures and seventeen
missing IIG sources. Three additional direct objects are unattempted, leaving
25 of 982 known direct objects unresolved. Archive/link closure is separate.

## Genuine source and export rules

Selected XNU is `c54f35ca767986246321eb901baf8f5ff7923f6a`, with recorded E1S
patches and source ports preserved. The libdispatch kernel dependency is
1415.100.11 at `a641558f447659d90ad002ef0ee6f0212273fbfc`.

The actual three source files include os/firehose_buffer_private.h alongside
selected XNU firehose types/chunk/tracepoint declarations. The pinned libdispatch
[project's kernel target](https://github.com/apple-oss-distributions/libdispatch/blob/a641558f447659d90ad002ef0ee6f0212273fbfc/libdispatch.xcodeproj/project.pbxproj)
exports only that private header in its Headers build phase.
Its [kernel configuration](https://github.com/apple-oss-distributions/libdispatch/blob/a641558f447659d90ad002ef0ee6f0212273fbfc/xcodeconfig/libfirehose_kernel.xcconfig)
enables COPY_HEADERS_RUN_UNIFDEF and specifies:

```text
-DKERNEL=1 -DOS_FIREHOSE_SPI=1 -DOS_VOUCHER_ACTIVITY_SPI_TYPES=1 -UOS_VOUCHER_ACTIVITY_SPI
```

The userspace libfirehose configuration instead undefines KERNEL. Exporting the
kernel header with genuine flags exposes the selected declarations and removes
the userspace dispatch branch. The SPI version constant remains 20180226.
No authored replacement declarations, SDK stand-ins or source patches are used.
The qualified host unifdef is HOSTGEN-002's local binary, with its exact hash
recorded. Exit 0/1 means successful unchanged/changed output; malformed input
must return 2. The runner does not ignore arbitrary unifdef errors.

Nine actual source/config/project files are checked against pinned Git blobs;
registered E1SDEPS-003 review-file hashes, original archives and all prior
compiler/source/build/kernel witnesses are verified. Component Apache2.0 and
per-file notices are retained in patches/kernel-firehose-headers. Original
source, build, archive and header prefixes remain unchanged.

A read-only Reddit MCP search for "firehose" scoped to r/hackios on 2026-11-05
returned no results. This is bounded search coverage, not proof of absence of
implementations. See the attributed source-review.json. No upstream installer
or flash command was executed.

## Actual compilation and contracts

The exact source compiler is VCOMP-002's
artifacts/xnu-compiler-vectors/source-build-session1/clang, SHA256
`3b11f867131e9a22a3671101ffb09dcecaf2b6831e5fd2c384b95075f29008a3`.
Full current VCOMP-004 recipes retain source/cwd/per-file flags, setup offsets,
local version, coherent MIG, syscalls and startup source port. Only the new
export include root and object/dependency outputs change. Actual allocator
checks remain enabled with XNU_NO_TYPE_BUILTINS=0, without the old compatibility
wrapper or blanket warning suppression. Every source is rebuilt after adding
the include root; no source-only cache is used.

The C contract checks nine genuine function prototypes, the two one-byte global
configuration declarations, SPI version and actual selected target structures.
Eleven emitted values are read from real arm64 Mach-O object bytes:
20180226,24,24,4096,16,4,8,16,16,64,8. Nine actual pointer relocations must name the
expected functions in order. Selected tracepoint data starts at byte 24; chunk
data starts at byte 16 in a 4096-byte chunk. Layout is measured, not inferred from
successful inclusion alone.

FHDR-006 separately compiles unchanged pinned firehose_buffer.c with the current
full recorded BSD consumer target/config recipe, the explicit three libdispatch
backend definitions and narrow source/selected-kernel firehose include roots.
Its fresh archive contains only the actual unmodified provider object; extracted
member bytes match. A separate translation unit includes the unchanged provider
and emits nine layout constants. Those agree with the historical genuine E1S
measurements: MAX_CPUS=10, MAX_CPU_CLUSTERS=4, pointer=8, buffer-header=4096,
buffer=262144, stream=128, tracepoint=24, data-offset=24 and header-unused-offset=1584.
The measurement record is excluded from the pure provider archive.

Both historical and current archives define the five functions required by the
three consumers. In the reverse direction, all six provider callbacks/global
references bind to actual compiled log/subr_log definitions. The other five
platform references are bzero, current_thread, mach_continuous_time, panic and
thread_tid; their names have definitions among the full 957 measured objects.
This is symbol coverage, without a full kernel link or complete ABI proof.

The old E1SDEPS-003 archive used a minimal Clang19 compatibility profile with
XNU_KERNEL_PRIVATE=0. That profile remains distinct from the new full compiler
profile. Selected layout/symbol agreement does not establish complete profile
or private Apple equivalence. The old archive and owner are preserved.

Meaningful negatives alter actual outputs or declarations: a layout value,
a real function relocation target, a real reservation parameter type, a
truncated object and a malformed conditional header. Each mismatch is detected.
Existing reference/member-pointer/PAC/arm64e/scalable/vector annotation limits
remain unchanged in the qualified source compiler.

## Measured runs and reproduction

| Experiment | Actual outcome |
|---|---|
| FHDR-001 | Fail: all three complete original recipes reproduce the missing header |
| FHDR-002 | Fail: three real compiles succeed; an overbroad collector check incorrectly rejects SPI_VERSION |
| FHDR-003 | Pass: precise conditional-directive check, genuine kernel export and all three consumers |
| FHDR-004 | Pass: initial prototypes/layout/symbol/mutation contracts with separate measurement archive |
| FHDR-005 | Pass for partial closure: all 962 recipes retried,957 real objects,zero regressions among 954 prior objects regressions |
| FHDR-006 | Pass: pure unchanged provider/archive, separate measurement, reverse callbacks and all retained contracts |
| FHDR-007 | Pass: independent full command/object/dependency/residual audit |
| FHDR-008 | Final bounded acceptance and repository checks |

The erroneous FHDR-002 collector and its outputs remain immutable. FHDR-003 uses
fresh paths and distinguishes the removed conditional from the retained version
constant. FHDR-004's initial archive contains its layout probe; reuse FHDR-006's
pure archive instead. No failed result was overwritten or reclassified.

Register fresh experiments with lab.py before invoking:

```sh
python3 tools/build/xnu_kernel_firehose_headers.py --run NEW_EXPORT --mode export
python3 tools/build/xnu_kernel_firehose_headers.py --run NEW_CONTRACTS \
  --mode contracts --header-evidence FHDR-003
python3 tools/build/xnu_kernel_firehose_headers.py --run NEW_PROFILE \
  --mode kernel --header-evidence FHDR-003 --jobs 2
python3 tools/build/xnu_kernel_firehose_headers.py --run NEW_AUDIT \
  --mode audit --header-evidence FHDR-003 --profile-evidence FHDR-005
```

Run names must be fresh. The runner preserves exact argv/cwd/exits/diagnostics
and hashes in report.json; capsules explicitly label representative command
samples. Reuse requires recorded passing evidence and exact output hashes.

## Component handoff and remaining work

The [qualified component](../../fixtures/public/xnu-kernel-firehose-headers/qualified-component.json)
binds genuine sources/export flags, exact compiler, old and new provider
profiles, real contracts, full regression and independent dependency audit.
[Compiled objects](../../fixtures/public/xnu-kernel-firehose-headers/compiled-objects.json)
include version.o; [unresolved objects](../../fixtures/public/xnu-kernel-firehose-headers/unresolved-objects.json)
include all 22 component gaps and three additional direct prerequisites.

Fresh prefixes under artifacts/xnu-kernel-firehose-headers:

- export-session2/export/include/kernel: qualified genuine exported header.
- contracts-session2: real type/layout/mutation controls and pure current provider/archive.
- full-profile-session1: all 962 actual complete source recipe attempts.
- object-audit-session1: independent 957 headers,29402 defined code symbols,
  3110 dependency-file hashes and actual per-object dependency graphs.

All three consumers' actual dependency files include the genuine export.
The independent audit allows only the declared include-root/output substitution
against VCOMP-004; all original source/hash/cwd/target/allocator checks remain.

KRN-015 can now address the matched Clang17 arm_neon.h resource header for APFS.
The other four failures remain: mc_provider printf/declaration conflict,
user_exception_trace undeclared proc_pid, MiniIOSurface member-function-pointer
metadata and IONVRAM reference-field metadata. Seventeen IIG sources, remaining
direct objects and full archive/link closure remain under existing owners.
Apple private ABI/userland and native boot/recovery/logging/GPU/Wi-Fi/SIM/eSIM
operation remain unqualified. Phone permissions and other owners are unchanged.
