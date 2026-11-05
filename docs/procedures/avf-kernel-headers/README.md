# VM-008: coherent public QEMU guest header route

Owner codex-team-avf-kernel-headers-20261105-cd; branch/worktree
team/vm-008-20261105 / worktrees/vm-008-20261105. AVFHEAD-001 was registered in
the sole MAIN registry before execution. Keep VM-008 in progress for review.

The bounded public source/header/representative route passes. It does not qualify
a complete SDK, selected Apple private DriverKit/RPC ABI, full kernel build/link,
AVF XNU execution, owned PID1/termination, native E1S or any S24 hardware. Existing
VM-002/native reservations and exports remain unchanged.

## Explicit guest inputs

The accepted complete-source descriptor is
fixtures/public/avf-kernel-source/qualified-source.json (SHA256
6eb1afcc895ecbb852ecea5331c3818e398302ca1bd5701b8609a35ba8a62ec4).
The selected genuine QEMU profile has canonical tree
6a955269a8f4e17d21239f75cef9fbe66cffc56c and config SHA256
1571c785ae12ed79858fb9c81ebfce4ecd5414e4ce6af906820f6b9d61f68394:
ARM64/DEVELOPMENT/BCM2837, eight selected drivers and the recorded residual
physical surfaces. No E1S generated header/object/archive is a guest product.
Complete file/mode/blob snapshots bind the original frozen source and new owned
prepare-2/source copies; final verification rechecks both. The native RELEASE
export contract is preserved. This guest source/board profile has its own
selection and still requires a coherent full object build and link assessment.

The new genuine Scion doconf ran for all eight components. Its board-neutral
config producer reuses a qualified public host binary only after all C/header/
lexer/parser/Makefile inputs match; the newer guest doconf itself runs separately.
Qualified tcsh, unifdef, MIG/migcom and the real XNU builtin-capable public Clang17
are hash-bound. Make variables are expanded by genuine GNU Make source rules.
A Linux command shim retains real platform/logging definitions and explicit host
utilities; it supplies no SDK metadata, target types or declarations. Upstream's
SDKROOT variable names only a recorded public source include context.

The public TargetConditionals contribution is PureDarwin/PureDarwin
6982ddbfca1047c86680ec7c66da152789746efd plus the recorded source target-port
patch de3faeb4e5a5661be57ab76ecbaf9dcc7b46e09e44c3acf2140915419e0a4b66,
replayed fresh. AvailabilityVersions115.4 is pinned at
5d9baee345b3bc72b26c71adc65f94f2d5e9ced2. Source licenses accompany the owned
public source inputs. No Apple SDK/archive/binary acquisition occurred.

## Actual bounded results

| Phase | Actual result |
| --- | --- |
| prepare-2 | Eight genuine guest component configurations |
| generate-1 | 98 source Make directories; 975 raw source exports; 75 declared generated exports |
| foundation-2 | Fresh genuine symbol-aliasing and POSIX availability headers |
| mig-1 | 80 real recipes; 127 nonempty internal/export files; 53 real preprocessor dependencies |
| syscalls-1/2 | Actual unifdef-selected master, table/names/header/proto and selected systrace source |
| setup-7 | Genuine three-input sanitizer ignorelist+validator, local public version templates, real ARM64 genassym compile and 270 extracted definitions |
| iig-1 | 17 genuine guest IDLs regenerated into 34 nonempty public candidate files |
| headers-2 + headers-final-1 | All 1,905 selected entries: 1,869 read-only installed headers, 36 genuine empty-body filters |
| representatives-2 | Eight real ARM64 Mach-O objects, 1,062 unique actual dependencies |
| allocator-1 / metadata-1 | Real kalloc.c object; real OSData.cpp emits a 192-byte __DATA_CONST,__kalloc_type section |
| controls-5 | Four genuine wrong-profile/input/metadata rejection cases |
| handoff-1 | All 1,080 guest object slots bound to genuine source and expanded recipes, including 55 generated C/C++ sources and all 75 generated raw exports; no full build executed |

The eight initial objects are board pe_init, IRQ gic_v3_irq, arm_init,
mockfs_vfsops, startup, libkern OSObject C++, actual generated OSObject.iig.cpp,
and start assembly consuming fresh assym.s. Metadata builtins remain enabled;
there is no constant allocator fallback. OSData is the explicit emission witness;
startup/OSObject alone do not demonstrate emitted allocation records. The failed
OSNumber emission expectation is retained: its genuine WithZone constructor does
not emit a kalloc-view section. kalloc.c and OSData provide two further actual
representatives, for ten accepted distinct guest object identities.

MIG internal/server and exported interfaces occupy separate namespaces and keep
component-specific include ordering. Actual temporary preprocessor bytes are
bound to the selected .defs input; compiler dependencies and output hashes are
retained. The public IIG producer is the existing source-qualified
Nyktis/iig-port ea6d147d668ca15d490da638012243fcd705f30d candidate with its
explicit-target/selected legacy IORPC/Invoke-guard source ports. Its binary,
libclang/LLVM and matched Clang19 resource headers are rehashed. Fresh guest
setup/MIG/source context is used, not old generated pairs. All17 generation exits
and one genuine generated implementation compile do not establish selected Apple
RPC IDs/private ABI or all17 full-object interoperability.

The installed namespace uses the genuine selection, unifdef, decomment and
replacecontents rules, with GNU install -c -m0444 replacing only BSD's unsupported
-S flag. XNU/Mach/BSD private implementation bodies are removed as upstream
requires; installed kern/thread.h is checked for that distinction. Source GEN_LIST
asm.h entries are resolved by real source Make VPATH, not invented generation.
The continuation rehashes/copies the prior passing namespace into new storage and
executes only two missing VPATH rules. All prior artifacts remain immutable.
The literal backslash in the donor bsd/skywalk/nexus INSTINC_SUBDIRS is retained
as a missing-recursion-Makefile fact; it selects no missing header entries.

## Controls, resources and retained failures

Wrong guest profile and changed .config fail before any generator/compiler starts.
A deliberately absent forced include makes the actual preprocessor and MIG exit1.
MIG may still leave plausible partial C/header files; these are quarantined and
hashed, while the production exit gate rejects the invocation and publishes no
positive component. The stock Clang19 control fails on actual XNU metadata
builtins in the same OSData source/context. Only Clang19's removed transitional
auto-init acknowledgement spelling is omitted for that negative control;
-ftrivial-auto-var-init=zero and all target/type defines remain.

Retain every failure/inconclusive report. prepare-1 lacked unifdef on PATH;
subsequent runs explicitly select qualified host tools. foundation-1, setup-2/6,
headers-1/3 and controls-4 record actual low-memory admission/stop boundaries.
The first genassym invocation exposed the missing genuine DEVELOPMENT sanitizer
ignorelist. setup-3/4/5 retain Linux logging-shim errors before its genuine logging
definitions were completed. representatives-1 records a driver-output option
handling error before source compilation. allocator-1 retains the unsupported
OSNumber emission expectation. controls-1/2/3 retain the separate-argument MIG
option error, incorrect no-files-on-failure expectation and stockClang19 obsolete
flag rejection; corrected controls preserve the actual failure boundaries.

All Git reads use GIT_NO_LAZY_FETCH=1, GIT_OPTIONAL_LOCKS=0 and no interactive
fetch. Missing public blobs are acquired only into owned storage with exact full
pin/blob hashes; shared promisor references are never hydrated. HAKIOS_VERSION_SUFFIX
and Git ceiling prevent upward shared metadata writes. Inherited recursive Make
settings are removed. Compiler/generator admission requires >=4 GiB MemAvailable;
owned process sessions are sampled every25ms, stopped on floor/deadline/RSS and
checked for live survivors. One compiler job, <=256 MiB total owned sampled RSS,
90/120s command deadlines; no heavy/full build. Largest measured accepted
representative peak is 140.25 MiB. A 2GiB virtual mapping cap is separate from RSS.
No unrelated process termination, swap/cache changes, phone/ADB/MMIO/device,
firmware loading or global install occurred.

## Next executor

Use the qualified component descriptor and its indexed handoff component. The
next-full-object-manifest binds all1,080 genuine DEVELOPMENT/BCM2837 sources and
primary compiler recipes to current source/config/setup/MIG/raw export/installed
header/public IIG inputs. Generated products are fresh guest products, including
new doconf ioconf.c and the genuine systrace source. Compiler argv templates have
explicit NEXT_OBJECT_DIR/NEXT_DEPENDENCY_DIR placeholders and require a new owned
output directory, new registered experiment and coordinator resource lease before
execution. Keep published inputs read-only. Do not reuse E1S objects under this
profile. Do not execute the entire donor build/install scripts.

No full object set or link has run. Fresh provider/tool/header requirements,
experimental IIG/private ABI, residual board/driver interfaces and actual selected
link symbols must be assessed from this guest graph; native missing37 are not
silently inherited, removed or declared resolved. A real linked XNU image, actual
AVF board/PSCI behavior, owned PID1 and bounded stop remain separate VM-002 gates.
A source manifest, successful representative compile or synthetic fixture cannot
substitute for that execution. Full SDK/DriverKit identity, selected private ABI,
full kernel/provider/link correctness, kernel image and guest/reference/boot all
remain unqualified.
