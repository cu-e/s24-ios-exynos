# Matched Clang17 ARM resource headers

KRN-015, owner `codex-resource-headers-20261105-z`, parent `1523baa`.
The bounded resource component passes. Work is host-only; no phone command,
SDK acquisition, global installation or original source/build/header mutation
was performed. Android and native scopes remain unchanged.

The current profile produces **957 component objects plus version.o: 958 known
direct ARM64 objects**. All 962 available recipes were repeated; every prior 957
successful direct object remains successful. Genuine bsd/apfs_deflate.o now
compiles. Of 978 component entries, 21 remain unresolved: four compiler failures
and 17 missing IIG sources. Three additional direct objects are unattempted,
leaving 24 of 982 known direct objects unresolved. Archive/link closure remains
separate, and no native iOS/graphics/radio qualification follows from this build.

## Source and actual resource binding

The compiler's public source is
[apple-libtapi](https://github.com/tpoechtrager/apple-libtapi/tree/fa9443738c1a18accef4244732ec6d6ee97a8133)
at `fa9443738c1a18accef4244732ec6d6ee97a8133`, LLVM/Clang17.0.6, with recorded
local experimental XNU allocator/compiler changes. The qualified compiler is
VCOMP-002's artifacts/xnu-compiler-vectors/source-build-session1/clang, SHA256
`3b11f867131e9a22a3671101ffb09dcecaf2b6831e5fd2c384b95075f29008a3`.
Relevant generator and resource files are unchanged pinned public source.
Selected XNU is c54f35ca767986246321eb901baf8f5ff7923f6a with the recorded E1S
patches/source ports; this includes donor APFS/libdeflate integration.

The real bsd/conf/Makefile.arm64 specifies:

```make
apfs_deflate.o_CFLAGS_ADD += -idirafter $(shell $(CC) -print-resource-dir)/include
```

The complete recorded recipe retained an old, nonexistent
artifacts/xnu-compiler-hardening/lib/clang/17/include after compiler relocation.
Only that one -idirafter argument is rebound to the freshly generated matched
prefix. Source/cwd/compiler/per-file flags, all setup/MIG/syscall/firehose roots,
startup source port and actual XNU_NO_TYPE_BUILTINS=0 checks remain unchanged.
All other recipes retain their include arguments. Selected kernel
EXTERNAL_HEADERS/stdint.h remains first; the kernel bundle contains no stdint.h.

The pinned [Clang Headers CMake rules](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Headers/CMakeLists.txt)
generate arm_neon.h and arm_bf16.h through clang-tblgen and provide source
arm_acle.h. The actual APFS ARM feature dispatch includes both NEON and ACLE.
These compiler resources are not an Apple SDK. Current
[Clang command documentation](https://clang.llvm.org/docs/CommandGuide/clang.html)
explains builtin/system include controls; exact selected behavior is established
by pinned source, complete recorded recipes, object output and actual dependencies.

A Reddit MCP search for arm_neon in r/hackios on 2026-11-05 returned no results
(limit 10). This is bounded search coverage, not proof of absence of an existing
implementation. See source-review.json; upstream instructions were reviewed
without executing installers or flash commands.

## Source-built generator and resource provenance

RHDR-002 rebuilds all 21 actual generator translation units using original
CMake compile argv in fresh output paths. Each actual source is verified against
a pinned public Git blob. Read-only Ninja -t commands queries obtain recipes;
no mutating Ninja/CMake runs in an original build prefix. Original compiler
source 10889 files,198 build inputs and 5111 prepared kernel files remain bound
by the recorded source/build witnesses.

The generator relink retains exactly three verified original LLVM archives:
LLVMSupport,LLVMTableGen andLLVMDemangle. All21 actual object paths and link/output
dependency paths point into the new prefix. The original shell-escaped literal
$ORIGIN rpath is converted to the equivalent direct argv value without invoking
a shell. New host compiler/linker/tool/dependency and object/source hashes are
retained. The source-built clang-tblgen SHA256 is
`b7fb3b0f92a0e799c3c41f6f88a871a8435e70f94f1598d3e3800fd5a007b1e3`.

Actual generation argv preserve TableGen action/source/include options and
--write-if-changed, replacing only the executable and output/dependency paths.
The old CMake dependency-file rewrite is unnecessary for the isolated run;
actual generator .d files are retained and audited. Fresh arm_neon.h and
arm_bf16.h reproduce existing source-build headers byte-for-byte. arm_acle.h
is copied unchanged from the matched source. The kernel resource set is exactly:

| Header | SHA256 |
|---|---|
| arm_neon.h | 7e347643c485383098196804b863a01d3ece143d434b83ef8439c2f8bb2fbc0f |
| arm_bf16.h | 87f7bc1cb7aa53a85347bd4e1855cccd45599408bb106e66515519c1033a6a3d |
| arm_acle.h | d16df987c4de19c6cc30bb8bad0674268d96762f41e3c4dfcf6d216b1c63b3e5 |

Retain Clang/LLVM Apache2.0 with LLVM exceptions and all per-file/generated ARM
permission notices. Component attribution lives in patches/kernel-resource-headers.
Original generator/compiler binaries, source, archives and headers stay untouched.

## Actual NEON and APFS controls

Independent Clang17 and Clang19 compile the real intrinsic fixture with their
own matched resources. Both agree on 12 actual target layout values:
8,8,16,16,16,16,16,16,16,2,32,16. These cover narrow/wide integer/floating vectors,
bfloat16 storage and aggregate pointer placement. Mach-O object bytes are read,
not inferred solely from inclusion or static assertions.

Both actual outputs contain uaddlp,umlal,umlal2,addv and vector eor instructions.
Optimized LLVM IR contains real vector addition/reduction and folds a calculation
using vdup/vadd/vget intrinsics to 52. The generated-header C++ metadata control
uses actual uint8x16_t/uint64x2_t aliases and an array-containing record, preserving
bounded vector allocator metadata rather than a synthetic type replacement.

Eight negatives reject an out-of-range lane,a nonconstant immediate,disabled
NEON,polynomial metadata,actual unmatched Clang19 header compilation,foreign
bundle provenance,actual header byte mutation and a missing matched BF16 header.
Header reuse validates exact compiler/source revision, file set and byte hashes.
The Clang19 positive control does not mix its headers into the Clang17 kernel.

The genuine APFS object contains a real _adler32_arm_neon function. Under its
complete kernel flags, the upper-half multiplications use eight ext#8 selections
and 16 umlal operations. It also contains four uadalp,two addv and one uaddlp.
That is legitimate lowering of the unchanged high/low-half intrinsic source.
A first collector incorrectly required umlal2 in this particular full recipe;
RHDR-003 remains an immutable failure. RHDR-005 checks the actual function body
and accepts either direct upper-half umlal2 or the measured ext/umlal sequence.
The independent fixture still emits actual umlal2 in both compilers.

No unlowered NEON builtin symbol remains undefined. The actual APFS object needs
six other symbols: stack-check failure/guard,apfs_deflate_free/malloc,bzero and
memcpy. Their names have definitions among the full 958 measured objects.
This is symbol coverage, not a full link or runtime ABI proof.

All intrinsic/layout/IR/disassembly checks are compile-only evidence. No ARM
execution,Exynos FP/NEON context save,APFS mount or runtime decompression was
measured. BF16 type availability does not establish runtime BF16 instructions.

## Recorded runs and reproduction

| Experiment | Actual outcome |
|---|---|
| RHDR-001 | Fail: genuine full APFS recipe reproduces missing arm_neon.h |
| RHDR-002 | Pass: all 21 generator TUs,source-bound relink,matched NEON/BF16 generation and source ACLE |
| RHDR-003 | Fail: actual APFS and all other controls pass; collector overconstrains one ISA spelling |
| RHDR-004 | Pass for partial closure: all 962 recipes,958 ARM64 objects,zero 957-prior regressions |
| RHDR-005 | Pass: genuine APFS,independent layouts/intrinsics/IR,generated metadata,eight negatives and actual Adler body |
| RHDR-006 | Pass: independent 958-object/exact-recipe/3124-input/dependency audit |
| RHDR-007 | Fail: generator/source/link witnesses pass; collector incorrectly expects the explicit primary .td input inside the include-only .d |
| RHDR-008 | Final bounded acceptance,complete generation dependencies,target replay and repository checks |

Register fresh experiments with lab.py before execution:

```sh
python3 tools/build/xnu_kernel_resource_headers.py --run NEW_GENERATION --mode generate --jobs 2
python3 tools/build/xnu_kernel_resource_headers.py --run NEW_CONTROLS \
  --mode controls --resource-evidence RHDR-002
python3 tools/build/xnu_kernel_resource_headers.py --run NEW_PROFILE \
  --mode kernel --resource-evidence RHDR-002 --jobs 2
python3 tools/build/xnu_kernel_resource_headers.py --run NEW_AUDIT \
  --mode audit --resource-evidence RHDR-002 --profile-evidence RHDR-004
```

Run names must be fresh. Generator/build/target commands, cwd,exit codes and
diagnostics remain in hashed reports. Capsules label representative command
samples. Failed collector outcomes are retained without rewriting their bytes.

## Component handoff and remaining work

The [qualified component](../../fixtures/public/xnu-kernel-resource-headers/qualified-component.json)
binds generator sources/objects/archives/tool,three matched headers,actual APFS
rule,retained firehose component,exact compiler,controls and full audit.
[Compiled objects](../../fixtures/public/xnu-kernel-resource-headers/compiled-objects.json)
include version.o; [unresolved objects](../../fixtures/public/xnu-kernel-resource-headers/unresolved-objects.json)
include all 21 component gaps and three additional direct prerequisites.

Fresh prefixes under artifacts/xnu-kernel-resource-headers:

- generate-session1: source-built clang-tblgen,all 21 objects and resource/lib/clang/17/include.
- controls-session2: genuine APFS object and qualified independent/metadata/negative controls.
- full-profile-session1: all 962 actual complete source recipes.
- object-audit-session1: independent 958 headers,29414 defined code symbols,
  3124 dependency hashes and complete per-object dependency graphs.

The actual APFS dependency graph includes all three generated/source resources
and selected XNU EXTERNAL_HEADERS/stdint.h. No missing-header compiler failure
remains among this 962-source selected profile; this does not qualify an entire
SDK,all dependency archives or private IIG inputs.

KRN-016 is a narrowly scoped follow-up for the real mc_provider printf declaration
conflict and missing proc_pid declaration in user_exception_trace. It reserves
new isolated source-port/tool/patch paths and requires full 958-prior regressions.
Existing crypto callback gaps,including NULL unsupported algorithms,remain
unqualified. MiniIOSurface member-function-pointer and IONVRAM reference-field
metadata failures remain separate. KRN-008 retains full object/archive/link
closure; KRN-004 retains IIG/private ABI. No existing owner was reclaimed.
Full native boot/recovery,iOS userland,GPU,Wi-Fi,SIM/eSIM and crypto operation
remain unqualified,and phone scopes are unchanged.
