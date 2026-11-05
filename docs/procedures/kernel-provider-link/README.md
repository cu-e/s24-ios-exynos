# Coherent selected kernel provider link measurement

KRN-024; owner `codex-team-kernel-link-20261105-ax`. Host only. Preserve all original source/object/header/tool/provider evidence and KRN-003/004/008 ownership. Worktree-local outputs only; no phone, global install, shared source/artifact mutations, heavy rebuild or SDK acquisition.

Register KPROV-001 before executing the harness. Verify accepted SGAP-001's exact current 982-object graph including all four replacements, all 3,156 dependency hashes and coherent symbol inventory; verify PTHP-007 source-qualified pthread archive, PTHP-012 acceptance, independent REV-006 and matched FHDR-006 firehose. Pin all source/recipe/helper/tool/capsule bytes and retain compiler/profile/namespace/alias witnesses.

Reuse KRN-020's genuine native filelist/staging/section-transform/archive helpers read-only, explicitly rebinding their compiled-object input to SGAP-001. Generate fresh native exports/aliases/symbolsets from real selected XNU scripts on owned outputs. Preserve BUILD_LTO=0 and native layout flags, direct version/last/nonlto object order, aliases and every required library including `-lcc_kext`. Supply only the exact genuine matched firehose and current pthread archive in an isolated library directory. Do not supply empty archives, historical pthread, stubs, skip flags or disabled-feature substitutions.

Run one actual full native link with process-group ownership, wall timeout at most 120 seconds and monitored aggregate process-group RSS at most 1 GiB. Defer execution when MemAvailable is below 4 GiB. One linker job; no concurrent compiler build. Preserve actual diagnostics and output existence/digests. An unavailable required cc_kext is a measured link failure, not successful kernel construction. Inspect only a genuinely produced Mach-O as an image; no placeholder/fake-image inspection.

Execute real wrong-input controls against the exact manifest/archive/filelist/alias/required-library invariants. Record actual commands, exits, timestamps, source/object/dependency/tool/command/output hashes, compiler/profile provenance, resource measurements, provider import/definition inventories, remaining requirements and handoff. Host assessment can pass checks of truthful measurement while full link/runtime/Apple ABI/crypto/native qualification remains false. Coordinator owns independent review, integration and common checks; retain in_progress for that review.

The first two runs are retained. KPROV-001 stopped before linking because an option guard incorrectly matched `-rename_section` as `-r`; KPROV-002 corrected exact-token matching and executed the original Clang driver command. Independent inspection of its `-###` expansion then revealed that the driver silently omitted the reserved `-lcc_kext` library. Its export-only symbol failure is diagnostic evidence, not acceptance of an intact required-library command.

KPROV-003 pins actual Clang Driver.cpp/ToolChain.cpp/Darwin.cpp at `fa9443738c1a18accef4244732ec6d6ee97a8133`, compares them to the compiler source lineage and measures its resource directory. Driver.cpp unconditionally rewrites `cc_kext`; Darwin.cpp selects compiler-rt `libclang_rt.cc_kext_ios.a` and silently adds nothing if unavailable. This is compiler support; the name alone does not establish a corecrypto/KEC provider. For the required literal native-library measurement, capture the exact expanded ld64 argv and restore only `-lcc_kext` immediately before the native archive-library arguments, leaving every other backend argument unchanged. Validate all three libraries in the command actually executed, not only in the outer compiler argv. Run one bounded direct ld64 attempt and preserve missing-library failure. The extra real negative control rejects the previously observed backend omission.

## Measured result — 2026-11-05

The bounded measurement passes; the intact full kernel link fails. No kernel image, ARM execution, SDK/private ABI/crypto qualification or hardware result is established.

| Experiment | Result |
| --- | --- |
| KPROV-001, native-session1 | Retained failure before linking: option-guard prefix bug. Real native staging, archive and provider inventory completed. |
| KPROV-002, native-session2 | Outer Clang invocation actually linked and failed on 37 export-only symbols. Its captured backend omits cc_kext, so this is not the required intact-library link. |
| KPROV-003, native-session3 | 32 measurement checks pass; 45 real commands. Fresh current graph/native metadata/providers; exact expanded ld64 command plus only restored native cc_kext fails with missing library, exit 1, no image. |
| KPROV-004, acceptance-session1 | 23 independent retained-byte checks pass; all three capsules and 1,128 artifacts in the final link capsule rehashed; current sources/objects/dependencies, exact backend delta and remaining export inputs independently checked. No additional link executed. |

All **982 current SGAP-001 objects** are rebound, including four replacements and 978 untouched objects; all **3,156 dependencies** are reverified. Genuine KRN-020 helper code stages 978 native filelist entries, performs 14 HIB and one KLD/KLDDATA transforms with exact byte comparisons, and builds a 981-member native `-ca` archive with ordinal/member digests. Direct version/last/nonlto objects remain in the original command order. The final archive SHA256 is `c45275f18b04b5b3ded98fd0b425a688db0003a66d8a77f8b1a35274ee6a4213`; this is an input archive, not a linked image. Native archive container metadata may vary between fresh runs; member payloads/order are verified separately.

The genuine matched FHDR-006 archive supplies eight definitions and has 11 external imports. The accepted PTHP-007 archive supplies 39 definitions and 61 external imports; its SHA256 is `d5f047488be1806e7e30af166312173b08f56bbbcff85340c1c5f3d28514b0d1`. Neither has unresolved imports or overlapping definitions against the current graph after the **83 freshly generated native aliases**. This includes the three genuine external VM aliases. The five prior direct firehose requirements and pthread_start are supplied; the remaining object/provider subset has only the 13 previously measured linker-boundary names. These counts do not establish export closure, compiler runtime, crypto or full-image success.

Six real wrong-input controls reject the old pre-SGAP object graph, missing required cc library, a wrong alias to another genuine VM provider, reversed native object order, the genuine historical pthread archive substituted for the accepted current one, and the actual observed backend library omission. Historical archive substitution is confined to validation and restored before any linker execution. No empty archive or fake provider is supplied.

The actual direct full-link attempt took **0.033157 seconds**, exit 1. Every subprocess has a deadline capped at 120 seconds, its own process group and TERM/KILL cleanup, with sampled aggregate group-plus-harness RSS enforcement. Minimum observed MemAvailable was **14,076,500 KiB**. Maximum sampled owned-group plus harness RSS was **306,264 KiB**; recorded maximum child RSS **282,996 KiB**, harness `ru_maxrss` **967,320 KiB**, all below 1 GiB. One linker job; no full source/compiler rebuild. A tiny genuine host replacecontents helper is compiled for native filelist generation. No phone, ADB, root, MMIO, flash, reboot or external app messaging occurred.

## Exact remaining requirements

1. **Compiler-support runtime.** The required literal `-lcc_kext` is absent from the available native search paths. The selected public Clang's compiler-rt candidate is also absent: `artifacts/xnu-compiler-cxx-storage/lib/clang/17/lib/darwin/libclang_rt.cc_kext_ios.a`. [Driver.cpp](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/Driver.cpp#L482) rewrites the reserved name unconditionally; [Darwin.cpp](https://github.com/tpoechtrager/apple-libtapi/blob/fa9443738c1a18accef4244732ec6d6ee97a8133/src/clang/lib/Driver/ToolChains/Darwin.cpp#L2839) selects the iOS compiler runtime and allows missing resource libraries. This does not identify cc_kext as corecrypto. KRN-025 owns genuine compiler-runtime source/provider qualification. Merely adding an empty library cannot satisfy it.
2. **Selected exported providers.** The earlier driver-omitted attempt exposes **37 actual export-list-only missing names**: 35 in [Private.arm64.exports](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/config/Private.arm64.exports#L78), and `_pmap_has_iofilter_protected_write`/`_pmap_cs_configuration` in [Private.exports](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/config/Private.exports#L776). They cover IOUnifiedAddressTranslator, IOMMU, DART/SART/UAT/NVMe/PPL and pmap configuration surfaces. Exact per-name source lines and hashes are in `acceptance-session1/remaining-export-inputs.json`. The public pmap_iommu.c/pmap_cs.c are placeholders; no provider body is invented here. KRN-026 owns source/configuration-consistent corrections. Do not delete required exports or claim those errors disappeared: the intact-library attempt stops earlier at cc_kext.
3. **Full linkage and runtime.** After genuine missing inputs are qualified, rerun the intact native command, then inspect a genuinely produced Mach-O for complete exports/aliases, all remaining undefined/duplicate names, relocations, segment capacities/protections, section/constructor order and runtime startup. Current symbols/layout evidence is not execution. Full SDK/header/library profile, DriverKit/private Apple ABI, separate corecrypto/callback security requirements, source-built runtime support and native/recovery/userland gates remain open. KRN-003/004/008 and blocked owners are untouched.

The exact current link-source/object/provider/dependency/tool/header/profile/capsule identities and each actual argv/cwd/exit/time/stdout/stderr/command/output hash are retained in the final report/evidence. The compiler/backend delta is explicit: direct argv equals the captured backend plus `-lcc_kext` immediately before `-lfirehose_kernel`; no other backend argument changes. Native plist serialization remains Python binary1 with semantic roundtrip, without an Apple plutil oracle.

## Reproduce and handoff

Run fresh experiments through the **primary** lab CLI before these commands. The harness requires accepted parent capsules and an owned in-progress KRN-024 claim. It imports existing KRN-020 helpers read-only from the primary checkout, but creates outputs only in its separate worktree.

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/build/xnu_kernel_provider_link.py \
  --root /home/egor/dev/pet/s24-ios-exynos --run fresh-native --experiment FRESH_REGISTERED_ID
PYTHONDONTWRITEBYTECODE=1 python3 docs/procedures/kernel-provider-link/verify.py \
  --root /home/egor/dev/pet/s24-ios-exynos --run fresh-verification
```

The verifier intentionally checks the immutable named original KPROV-001/002/003 capsules; replayed new full-link runs need their own named acceptance inputs before promotion. All Git reads disable lazy fetch and optional locks, and Python bytecode writes are disabled for shared imports. Apple/vendor code, firmware, SDKs, headers and binary archives are not redistributed in the committed fixture; only authored harness/docs and provenance metadata are committed.

Owner: `codex-team-kernel-link-20261105-ax`; branch/worktree `team/krn-024-20261105` / `worktrees/krn-024-20261105`; parent main `8a469ab`. Keep KRN-024 in progress for coordinator review, integration and common `make check`. The three criteria are ready for review: current coherent graph/native/provider validation; genuine bounded intact-library measurement with explicit failure; and complete input/output evidence plus truthful next gates. No additional full-link attempt is required for this bounded task.

Main-relative final evidence:
`worktrees/krn-024-20261105/artifacts/kernel-provider-link/native-session3/evidence.json`
(SHA256 `101f247f13600e6c2219540cdc79008099ee15af76c6f8a19790cf6ea23c41ea`).
Independent retained-byte evidence:
`worktrees/krn-024-20261105/artifacts/kernel-provider-link/acceptance-session1/evidence.json`.
