# Genuine top-level direct objects and LAST processing

KRN-018, owner `codex-direct-tail-20261105-ac`, parent `0c93936`.
Host-only work. Preserve every original source/compiler/build/object/evidence
prefix and the existing KRN-008 object/link and KRN-004 private IIG ABI owners.
No phone, SDK acquisition, installation, root, hardware or native boot command.

The current qualified CXXST-007 compiler and CXXST-010/006/011 evidence bind
962 actual ARM64 objects, all962 exact current recipes,3131 dependencies and
29740 code definitions. Of982 known direct objects,17 IIG sources and three
top-level direct objects remain unresolved. The three sources already exist:
libsa/nonlto.c,libsa/lastkerneldataconst.c,libsa/lastkernelconstructor.c.

Read the pinned public [MakeInc.kernel](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.kernel),
[MakeInc.def](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.def),
[MakeInc.rule](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/makedefs/MakeInc.rule)
and [setsegname](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/SETUP/setsegname/setsegname.c).
Expand actual target recipes against the same recorded current configuration,
including BUILD_LTO=0 and XNU_NO_TYPE_BUILTINS=0. Explicit LTO/profile variants
are separate controls, not a replacement for the selected profile.

nonlto.o forces a real Mach-O input during LTO linking. lastkerneldataconst.o
supplies a PAGE_MAX_SIZE all-FF padding array and pointer/size markers for
read-only data boundaries. lastkernelconstructor.o calls
iokit_post_constructor_init from an init-function pointer and emits the zero-size
last symbol. Its genuine rule removes profiling instrumentation, appends the
selected no-LTO flag and invokes setsegname to change eligible __DATA section
segment names to __LASTDATA_CONST. The linker subsequently renames that segment
to __LAST. Successful compilation alone does not qualify that processing.

Build the unchanged genuine host source with the pinned cctools public headers
and the documented Linux diagnostic/type include glue. Validate inputs before
invoking the legacy utility. Compare actual output bytes, code, symbols,
relocations and section attributes against an independent bounded reader.
Exercise data/name/debug/ignore behavior and negative/mutation detection.
An owned provider may support an explicitly labelled link-only fixture for the
rename_segment option; it does not supply a real kernel/iOS runtime.

Every run uses a fresh artifacts/xnu-kernel-direct-tail prefix. Register a new
experiment before executing source/tool/compile/control/audit modes. Capsules
retain actual commands, exit codes, source/tool/input/output hashes, parent
commit and failed/inconclusive attempts. Final acceptance requires all four task
criteria, unchanged962 parents, complete982 accounting and make check. Full
kernel archives/link closure,17 missing IIG sources,private ABI,complete SDK,
crypto/runtime/recovery and native graphics/radios remain unqualified.

## Actual results and reuse

KTAIL-003 builds the unchanged genuine tool and all three sources against the
current selected Clang17/E1S profile. The genuine Make loop renames exactly the
constructor __mod_init_func section segment-name bytes. Its eight-byte pointer,
branch relocation and zero-size last marker remain intact. The padding object
contains exactly16384 FF bytes, a correctly relocated pointer and matching size.
All three actual sources independently compile with stock Clang19 and agree on
these representations. The Clang19 control removes only an obsolete Clang17
permission option, retaining zero-initialization and every selected type check.

KTAIL-007 passes **40 actual controls**: independent genuine objects, pointer/
branch/page data, source-based rename/debug/ignore/name-length cases, code/call/
name mutations, six malformed-input guards, genuine CLI errors and explicit
LTO/profiling policy. Under BUILD_LTO1, nonlto.o and lastkernelconstructor.o keep
actual Mach-O output through the genuine trailing -fno-lto option; constructor
profiling is removed by the actual per-target filter. Current production inputs
remain BUILD_LTO0. No allocator/type-check bypass or target source patch is used.

The final link-only fixture is **static**, with an explicitly owned provider of
iokit_post_constructor_init. It uses the previously qualified host linker mode,
requires no SDK/system dylib and verifies the real rename_segment flag. With the
flag, __mod_init_func resides in __LAST; without it, __LASTDATA_CONST remains.
The init pointer still addresses the real compiled constructor. This fixture
proves the selected name/relocation transformation, not full XNU linkage,
Apple runtime compatibility, boot or actual execution on ARM.

KTAIL-005 independently accounts for **965 of982 known direct objects**, retaining
all962 prior objects by their exact source/compiler/recipe/object/dependency
provenance, without recompiling or silently substituting them. The current
manifest contains961 component objects and four top-level objects. Exactly17
missing IIG component sources remain unresolved. The graph binds **3134 unique
input files**; LLVM independently reads all965 ARM64 headers and **29744 defined
code symbols** (17655 T,12089 t). New objects include data-only markers as well
as constructor code; successful objects are not all functions or a linked kernel.

Reuse qualified-component.json and the complete compiled/unresolved manifests.
The ignored audit artifacts also contain every object depfile/input digest.
KRN-008 retains object/archive/link integration, and KRN-004 retains private IIG
ABI ownership. These source/tool/object results do not satisfy their remaining
acceptance criteria. Full archives/link order/export closure,17 genuine IIG
sources with matching header/RPC ABI,complete SDK/dependencies,crypto/runtime,
recovery and all native GPU/Wi-Fi/SIM/eSIM results remain outstanding.

## Preserved failed attempts and research access

KTAIL-001 incorrectly assumed every prepared Makefile byte matched public XNU.
The existing5111-file witness actually includes prior Linux/E1S changes; explicit
public-to-selected diffs now retain them. All four relevant target/tool sources
and MakeInc.kernel/MakeInc.rule remain public-exact. The prepared MakeInc.def
adds E1S/PAN and existing library inputs; Makefile/MakeInc.cmd change host tool
and CPU discovery. This task changes none of those files.

KTAIL-002 retains the foreign-strings/glibc include-order conflict. Final tool
compilation searches real host headers first and pinned foreign fallbacks last.
KTAIL-004 retains Clang19's rejection of the removed Clang17 permission flag.
KTAIL-006 retains the dynamic fixture's genuine libSystem requirement; no fake
libSystem/SDK is introduced. Their prefixes, commands and results stay unchanged.

The current r/hackios Exynos search (limit5) timed out in Arctic Shift and is
inconclusive. No statement about absence of a port follows from that failure.
Pinned primary source contents and recorded host results support this component.

Fresh run examples, after registering new experiment IDs:

```sh
python3 tools/build/xnu_kernel_direct_tail.py --run fresh-tail --mode build
python3 tools/build/xnu_kernel_direct_tail.py --run fresh-controls --mode controls --object-evidence KTAIL-003
python3 tools/build/xnu_kernel_direct_tail.py --run fresh-audit --mode audit --object-evidence KTAIL-003
```
