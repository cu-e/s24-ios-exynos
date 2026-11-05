# KRN-026 selected export gap audit

Owner: codex-team-export-gaps-20261105-ba. Host-only; no device, MMIO, SDK installation, global changes or heavy build. One compiler process at a time and512MiB maximum observed child RSS. Main references and artifacts are immutable inputs. Git reads use GIT_NO_LAZY_FETCH=1 and GIT_OPTIONAL_LOCKS=0.

Procedure (register experiment first): run `python3 tools/build/xnu_kernel_export_gaps.py --main-root /home/egor/dev/pet/s24-ios-exynos --run NEW_NAME`. It binds KRN024's actual37-name diagnostic and SGAP982 graph, hashes every graph object/source/dependency, replays native export selection and generation into a fresh local capsule, inventories exact pinned public source occurrences, and reruns the actual full pmap_cs/pmap_iommu recipes with owned source/output/depfiles. Actual preprocessing captures effective feature macros. Independent native nm records emitted providers. Wrong architecture export selection, the donor's prohibited export deletion, stale source bytes and a feature-disable recipe are negative controls only, never production replacements.

Required source/profile/ABI input remains unavailable if public placeholders and export-only class names provide no implementations. A successful diagnostic checker is not a closed kernel graph or successful full link. The report/evidence must preserve that distinction. KRN025 separately owns compiler runtime support; KRN004/008/003 scopes remain unchanged. Integration and task acceptance remain with the coordinator.

## Source-backed diagnosis and handoff

The selected sources are pinned to Apple XNU `c54f35ca767986246321eb901baf8f5ff7923f6a` and S24 donor `c8860decc62c6d6180e609036d027a2997972420`. The exact current SGAP982 graph and KRN024 native-session2/session3 reports are digest-bound in `fixtures/public/kernel-export-gaps/inputs.json`. The37-name observation belongs to the actual native-session2 linker attempt whose Clang driver omitted cc_kext; corrected session3 restores the genuine backend argument and stops at missing cc runtime. These export names are a separately established remaining gate, not a prediction of a successful corrected full link. KRN025 owns runtime work.

`config/Makefile` always includes Private.exports and Private.arm64.exports for the selected release/ARM64/E1S/iPhoneOS export selection. `generate_linker_exports.sh` only splits aliases and sorts; it never preprocesses feature flags. Fresh generation produces byte-identical output SHA256 `bef85c1548ac18338f469de1479416c558925f1ae5e409e11db47ae215d3cd58`. Native export locations are Private.arm64.exports lines78–95/97/103–119 (35 names) and Private.exports lines776/780 (two names). No required export was removed and no native profile flag changed.

The entire exact pinned public source tree was searched with network/lazy fetch disabled. The17 IOUnifiedAddressTranslator exports have no public class declaration, `.iig` definition or implementation at this pin. Seven pmap_iommu exports and11 DART/SART/UAT/NVMe PPL names likewise have no public target implementation. The two pmap query functions have declarations in osfmk/vm/pmap.h and unsupported-return definitions in osfmk/x86_64/pmap.c. Those x86 bodies neither establish ARM64 semantics nor justify security capability results on E1S.

Genuine public `osfmk/arm/pmap/pmap_cs.c` and `pmap_iommu.c` are explicit placeholder files. Both are already included by the current `nos_arm_pmap` configuration and compiled in the982 graph. Fresh copies compile under their exact original full current component recipes (only source/output/depfile paths change), and independent llvm-nm finds no external providers in either object. Actual preprocessing reports CONFIG_PMAP_PPL=1, NOS_ARM_PMAP=1, XNU_TARGET_OS_IOS=1, ARM64_BOARD_CONFIG_E1S=1, XNU_NO_TYPE_BUILTINS=0; XNU_MONITOR/CONFIG_SPTM are absent in these two TUs. No absence of runtime PPL support is inferred from an absent macro alone.

Existing donor `osfmk/conf/files.arm64` differs from the public base by previously applied AMCC exclusions and genuine donor file additions. The checker binds its exact prepared hash and proves all six pmap selection lines remain byte-identical to the public base. The first audit intentionally failed an overly strict whole-file equality assumption here; EXPGAP-001 preserves that failure. EXPGAP-002 corrects this provenance distinction and completes63 diagnosis checks with no provider correction, hence outcome inconclusive. Its child peak is80348KiB and post-exec `/proc/self/status` VmHWM64200KiB; resource.getrusage reports a larger inherited harness maximum, retained separately rather than presented as fresh allocation. The final run additionally compiles the genuine x86 source under the unchanged ARM64 recipe as a wrong-source negative control.

The pinned legacy sweet patch `xnu/legacy-sweet-patches/0009-sweet-drop-apple-soc-only-exports.patch` deletes exactly these37 exports for a different board. It is inspected as an actual negative control only. Applying its deletion to owned diagnostic export copies makes all37 disappear, and the native-byte/required-export guard rejects that output. Wrong export architecture similarly hides35 and is rejected; a CONFIG_PMAP_PPL=0 preprocessing control actually changes the macro and is rejected against the selected profile. None of these outputs is proposed for integration.

Exact missing inputs: provenance-qualified selected ARM64 IOUnifiedAddressTranslator declaration, layout/vtable/type/dispatch ABI and real method implementations; real selected ARM64 pmap_iommu and DART/SART/UAT/NVMe PPL implementation inputs and their hardware/ABI dependencies; real selected ARM64 pmap_has_iofilter_protected_write and pmap_cs_configuration semantics/implementations. The mangled export spellings do not specify class layout, return types or a private ABI. No matching supplied component/implementation is known in these inputs. KRN004 retains private Apple ABI qualification; this audit does not equate missing ordinary C++ providers with an IIG generation fix. No SDK, Apple binary or incompatible historical driver is imported.

Acceptance: criterion1 is met for diagnosis; criterion2 has no supported source/profile/object correction to apply; criterion3 has genuine output/source/config controls and exact unavailable facts, but no coherent provider replacement exists. Task acceptance remains incomplete. Keep KRN026 owned/in progress for coordinator review, then block through the original owner only when the coordinator accepts this exact missing-input reason. Do not mark done from inconclusive evidence. Existing982 source/object bytes and3156 dependencies are immutable and unchanged. No common main check, device or full link is rerun by this worker.

Authoritative source links: [native export selection](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/config/Makefile), [generator](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/config/generate_linker_exports.sh), [pmap IOMMU placeholder](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/arm/pmap/pmap_iommu.c), [pmap CS placeholder](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/osfmk/arm/pmap/pmap_cs.c), [legacy deletion patch](https://github.com/RNDMBG/iOS-On-S24/blob/c8860decc62c6d6180e609036d027a2997972420/xnu/legacy-sweet-patches/0009-sweet-drop-apple-soc-only-exports.patch). Existing source licenses/notices govern each source; the owned diagnostic helper adds no license grant for unavailable implementation inputs.

Exact observed names, also held machine-readably in inputs.json:

```
__ZN26IOUnifiedAddressTranslator10gMetaClassE
__ZN26IOUnifiedAddressTranslator10superClassE
__ZN26IOUnifiedAddressTranslator12commitUnmapsEv
__ZN26IOUnifiedAddressTranslator14prepareFWUnmapEyy
__ZN26IOUnifiedAddressTranslator17getPageTableEntryEy
__ZN26IOUnifiedAddressTranslator18setClientContextIDEjb
__ZN26IOUnifiedAddressTranslator19isPageFaultExpectedEyj
__ZN26IOUnifiedAddressTranslator21removeClientContextIDEv
__ZN26IOUnifiedAddressTranslator22registerTaskForServiceEP4taskP9IOService
__ZN26IOUnifiedAddressTranslator23createMappingInApertureEjP18IOMemoryDescriptorjym
__ZN26IOUnifiedAddressTranslator23getTotalPageTableMemoryEv
__ZN26IOUnifiedAddressTranslator3mapEP11IOMemoryMapj
__ZN26IOUnifiedAddressTranslator5doMapEP18IOMemoryDescriptoryyj
__ZN26IOUnifiedAddressTranslator5unmapEP11IOMemoryMap
__ZN26IOUnifiedAddressTranslator7doUnmapEP18IOMemoryDescriptoryy
__ZN26IOUnifiedAddressTranslator8taskDiedEv
__ZTV26IOUnifiedAddressTranslator
_nvme_ppl_get_desc
_pmap_cs_configuration
_pmap_has_iofilter_protected_write
_pmap_iommu_alloc_contiguous_pages
_pmap_iommu_init
_pmap_iommu_ioctl
_pmap_iommu_iovmalloc
_pmap_iommu_iovmfree
_pmap_iommu_map
_pmap_iommu_unmap
_sart_get_desc
_t6000dart_get_desc
_t6000dart_vo_tte
_t8020dart_get_desc
_t8020dart_vo_tte
_t8110dart_get_desc
_t8110dart_max_translation_levels
_t8110dart_vo_tt_index
_t8110dart_vo_tte
_uat_get_desc
```

Final checkpoint: EXPGAP-003 at implementation commit `d1d53a31ff0b69024a6b0e6640e958667425cf89` completed64 diagnostic checks and24 actual commands, preserving inconclusive outcome. All81 existing artifact hashes were independently reread and matched. The genuine wrong-source compile exits1 with explicit `Wrong architecture - this file is meant for x86_64`, unknown x86 debug state types and invalid x86 assembly constraints under the unchanged ARM64 recipe; no object is emitted. Final child peak80768KiB, actual `/proc/self/status` VmHWM64284KiB. The inherited getrusage maximum is already995980KiB at harness entry while entry VmHWM is20912KiB; both values remain in evidence to avoid confusing inherited lifetime accounting with this run's fresh footprint.

Final evidence: `worktrees/krn-026-20261105/artifacts/kernel-export-gaps/audit-session3/evidence.json`. Human-readable report: matching `report.json`. `fixtures/public/kernel-export-gaps/assessment.json` binds their digests and criterion-by-criterion assessment. EXPGAP-001 failure and EXPGAP-002/003 inconclusive outcomes are recorded in the main ledger. The only proposed integration is this diagnostic helper, exact input/assessment fixtures and documentation. No provider replacement, export deletion or source patch is proposed. Next step: coordinator review these bytes and approve the original owner recording a blocked task with the precise unavailable-input reason above; no new compile or device operation is needed.
