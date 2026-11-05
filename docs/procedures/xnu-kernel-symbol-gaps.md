# Selected cache and platform symbol gaps

KRN-021,owner codex-kernel-symbol-gaps-20261105-af,parent7885ddd.
The previous goal turn made progress: KLINK-012 qualifies genuine link inputs
while retaining full-kernel,SDK,private-ABI,crypto and native limitations.
This task is host-only and preserves original sources/objects/evidence and
KRN-004/KRN-008 ownership. No phone,root,reboot,flash or global installation.

Primary pinned source:
- [Cache assembly](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/arm64/caches_asm.s)
- [Platform producer](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/pexpert/arm/pe_init.c)
- [Panic consumer](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/arm/model_dep.c)

KLINK-009 actual preprocessing shows TARGET_OS_OSX defined as0 in model_dep.c,
but absent in pe_init.c. Both currently test defined(TARGET_OS_OSX),so they
select different branches on iOS. Inspect this actual inclusion difference;
it is not an unconditional upstream consumer. MakeInc.def supplies explicit
XNU_TARGET_OS_IOS/OSX platform selectors;use the real build-target selector
consistently in all five affected guarded declarations/producer/consumers.
Preserve the original macOS-only128-byte firmware producer and both logs.

The clean_mmu_dcache global has no label while genuine CleanPoC_Dcache code
exists. Its legacy extern has no selected actual call,although the exported
undefined name remains in the object. Preserve the public legacy entry with
a same-address label into that real code,not a CPU stub. Compare complete
section bytes to the original and inspect actual generic dc csw instructions.
SleepToken's global currently outlives its conditional definition. Scope the
export to WITH_CLASSIC_S2R,as already done for the matching C declaration and
genassym size. Verify both production-disabled and real enabled storage.

Apply the small APSL-preserving patch only after exact source hash checks in
fresh copied files. Run all four actual current full component recipes with
new sources/objects/dependencies;preserve every original flag and witness.
Register experiments before execution. Controls must use actual target
objects,relocations,preprocessed source and deliberate source mutations.
Enabled S2R assembly must consume genuine freshly generated assym offsets,
not an invented size constant. OS macro variants are explicitly bounded
source controls,not a complete supported macOS-on-E1S profile.

Publish a coherent982-object replacement manifest and independent provider/
consumer audit. Verify all978 untouched original objects and all3152 original
dependency witnesses,with all four replacements separately identified.
All4 acceptance criteria and make check must pass before task completion.
Even a closed direct source-symbol subset is not a successful full link,
Apple ABI match,crypto/runtime or native hardware result. Real pthread,
corecrypto,SDK,full exports/linkage,recovery and hardware gates remain.


## Measured result and integration handoff — 2026-11-05

SGAP-001 passes18 checks. All four genuine full recipes compile actual ARM64
objects with the current CXXST-007 compiler,real allocator metadata enabled,
original component flags and existing qualified header/MIG/generated inputs.
The patch applies only to fresh four-file copies after exact SHA256 checks.
Actual new sources,objects,depfiles and every command/cwd/exit are recorded.
The complete coherent graph has982 objects:four replacements and978 untouched
original objects. All3152 original dependency hashes remain valid;four new
copied source files make3156 witnessed inputs. The public component manifest
links full immutable compiled-object/dependency/provider/consumer manifests.

Independent LLVM and Mach-O nlist maps agree for all982 objects. There are
24070 external provider names,12217 consumer names and zero strong duplicate
providers. Unresolved required names fall from22 to19 by exactly the three
measured source gaps. Remaining names are the same13 measured linker
synthesized boundaries,five matched firehose imports and pthread_start.
These are object-level results,not full link/export/library/crypto closure.

Both cache and start replacement objects retain every original section's
code/data bytes. Cache symbol clean_mmu_dcache is a same-section,same-address
alias of the existing CleanPoC_Dcache code. Real non-Apple generic CLIDR_EL1
and dc csw instructions remain;the current selected code is not an Apple
fully-coherent dsb/ret fallback. This does not qualify that inherited cache
geometry/coherency algorithm on Exynos,or execute EL1 instructions. The original legacy C references are an extern declaration in
pe_identify_machine.c and a CLOSURE string entry in the DTrace FBT blacklist.
Neither is an active call or an additional undefined-object consumer;the
actual graph names only caches_asm.o as the unresolved consumer. The full-tree
inventory is retained in final acceptance. The alias also preserves that
blacklist spelling. No fake cache implementation is introduced.

SleepToken is absent from the production-disabled object,as required by the
already conditional C declaration and genassym definition. SGAP-003 passes
20 controls:original-source reversions reintroduce all three actual undefined
symbols;a deliberately compiled no-op cache body differs from qualified code;
explicit WITH_CLASSIC_S2R=0 emits no SleepToken. The enabled branch uses genuine
fresh target genassym plus the original sed extraction,not a supplied numeric
substitute. That emits stSize_NUM=8 from the real uint8_t SleepToken[8]
declaration,and the actual start object contains the real eight zero bytes.
The exact .space directive is also verified after actual preprocessing.
No suspend/resume or native storage behavior is inferred.

Four full-source preprocessing cases exercise default iOS,public OSX macro
zero,public OSX macro one,and the canonical macOS build selector. Actual macros
from each TU are recorded rather than assuming command-line overrides survive
headers. All five stage2 branches remain absent for iOS and present together
for the macOS selector,including the128-byte declaration,both log consumers,
extern and real system-firmware-version DT producer. This preserves the
original intended macOS-only behavior. It does not support a new macOS/E1S
build profile or manufacture an iBoot firmware version on Samsung.

SGAP-004 passes seven checks. A separate real full ARM64 producer TU exercises
the enabled branch with an appended sizeof measurement. Independent object
decoding observes128 bytes,real zero-fill storage and DT-copy references.
Changing FW_VERS_LEN to129 causes the actual compiler's size assertion to
fail. That control intentionally changes only OS selection for source-branch
coverage;it is not a complete macOS kernel profile or an Apple runtime test.

SGAP-002 retains one harness failure:actual assembly preprocessing legally
emits whitespace between _SleepToken and its colon. Its original verifier
assumed an adjacent colon. SGAP-003 accepts that syntax and retains every
actual size/storage/source/machine-code control. No kernel patch was changed
to obtain the corrected check. The failed original capsule is immutable.

SGAP-005 passes the initial acceptance. Its complete source inventory also
exposes the DTrace blacklist string reference,which is included in this final
source-review handoff. SGAP-006 repeats acceptance against the corrected
maintained documentation and performs final acceptance over all982 exact sources/objects and3156
dependencies,original witnesses,exact full commands,patches,enabled controls,
19-name closure and make check,assessing all four task criteria. Its passing
capsule is the task evidence;qualified-component.json is the integration map.

### Remaining work and replay

KRN-008 retains complete archive/link integration ownership. Replace objects
by stable id using this manifest;do not silently mix old/new source or header
profiles. Apply genuine HIB/KLD postprocessing only to owned staged copies as
measured by KLINK-007. KRN-004 retains the private Apple IIG/type ABI/oracle
scope;KRN-003 retains SDK/library dependency work. None of their original
reserved prefixes or owners was changed.

At this symbol-gap measurement, pthread/profile integration was queued as
KRN-022. The historical archive used fake allocator metadata; its three VM
imports were absent by their direct public names. KRN-022 subsequently built
the genuine component and verified native aliases to the existing external
VM providers, callback types/layouts and real allocator metadata. Use its
[qualified archive and witnesses](xnu-kernel-pthread-profile.md), not the
historical archive or the earlier failed header profiles.

KRN-024 also corrected the cc_kext identity. The selected Clang driver source
at `fa9443738c1a18accef4244732ec6d6ee97a8133` rewrites `-lcc_kext` to a reserved
option selecting compiler-rt `libclang_rt.cc_kext_ios.a`; if the resource file
is absent it silently adds nothing to the backend command. This is compiler
support, not evidence of a corecrypto/KEC provider. KRN-025 qualifies that
runtime; KRN-023 independently audits missing crypto callbacks and startup,
and KRN-026 investigates the later export-only gaps. The pinned driver paths
and primary links are in the pthread procedure's handoff. The qualified
source-built firehose archive remains distinct
from unavailable SDK binaries. Full exports/aliases,symbolsets,segment layout,
full kernel link,SDK and Apple-private ABI,crypto/runtime,userland,recovery,
native GPU/Wi-Fi/SIM/eSIM remain unqualified. No phone scope is added.

The current r/hackios pthread search (limit5) timed out in Arctic Shift.
reddit-search.json retains the tool error;the result is inconclusive and does
not establish absence of another implementation. Primary pinned source and
actual local target commands support this result.

Register fresh experiment IDs before running these examples;names must be new:

```sh
python3 tools/build/xnu_kernel_symbol_gaps.py --run fresh-production --mode production
python3 tools/build/xnu_kernel_symbol_gaps.py --run fresh-controls --mode controls
python3 tools/build/xnu_kernel_symbol_gaps.py --run fresh-storage --mode storage
python3 tools/build/xnu_kernel_symbol_gaps.py --run fresh-acceptance --mode acceptance
```

The builder intentionally consumes the pinned existing qualified parents and
registered evidence. It does not fetch SDKs,install globally or touch a phone.
Every run retains provenance,actual commands/exits,commit,source/header/tool/
object hashes and existing artifact paths. Maintained project text is English.
