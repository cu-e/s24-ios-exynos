# Native kernel link with qualified compiler-runtime lookup

KRN-030; owner `codex-team-kernel-runtime-link-20261105-bk`. Host only; own outputs in `worktrees/krn-030-20261105`. Preserve all accepted primary/shared sources, objects, headers, tools, staging, resources and evidence. No phone, MMIO, SDK acquisition, global install, provider stub, weakened exports or forced archive loading.

Register KRUNLINK-001 before execution. Digest-verify accepted KRN-024's current 982-source/object graph, 3,156 dependencies, native staging/filelists/section transforms/aliases/layout/FHDR/PTHP, plus accepted KRN-025's corrected compiler-runtime descriptor, 287-member archive and exact arithmetic patch provenance. The resource root is link-only; do not use it for kernel recompilation. The qualified runtime SHA256 is `67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5`.

Rebind the original native frontend command to a fresh output and explicit qualified `-resource-dir`. Keep outer `-lcc_kext` and every native object, library, export and layout flag. Capture `-###` and the actual transparent-journal backend execution, checking that native Clang reserved-option handling inserts exactly the genuine absolute `libclang_rt.cc_kext_ios.a` path. Never restore literal backend `-lcc_kext`, rename that archive, add force_load/all_load, skip a required input or create providers.

Execute one full link with one linker job, a 120-second maximum deadline, finite owned process-group TERM/KILL cleanup and sampled aggregate owned process RSS below 1 GiB. Defer if MemAvailable is below 4 GiB. Record actual command/tool/input/output hashes and diagnostics. Inspect any genuinely produced image before claiming one. A failed link is not a full-kernel pass.

Check real wrong descriptor, stale input, archive and driver-command controls without another full link. Record remaining diagnosed symbols separately from the whole runtime archive's 47 imports: normal lazy member loading does not select every member. Preserve all missing ARM-provider, private ABI, crypto, runtime and native gates. Save dated evidence and a scoped commit/handoff; retain in_progress for coordinator review, integration and common checks. KRN-003/004/008 and blocked KRN-026 ownership remain untouched.

## Measured result — 2026-11-05

**The native runtime lookup works; the full kernel link fails.** Clang's actual backend contains the qualified absolute compiler-rt archive, no literal backend `-lcc_kext`, and the unchanged genuine FHDR/current pthread/native export and layout inputs. The actual link exits **1** on the same **37 ARM export-list symbols**, produces no image and diagnoses no new missing name. No image was created or inspected as a kernel.

| Experiment | Actual result |
| --- | --- |
| KRUNLINK-001, native-session1 | 12 checks and six real input controls pass. Two driver dry-runs and exactly one full link execute. A transparent Python journal immediately `execv`s the original ld64; its captured argv equals the actual Clang `-###` expansion. Full link exit 1, no image. |
| KRUNLINK-002, acceptance-session1 | 28 independent retained-byte checks pass: six registered capsules rehashed, original frontend/backend deltas checked, original staging/providers/source patch bound, actual backend journal verified, same 37 export requirements and false system qualifications confirmed. No additional linker executes. |

The revalidated inputs are the accepted **982 current source/object identities**, including the exact four SGAP replacements and 978 unchanged objects; **3,156 dependencies**; immutable native 978-entry filelist, 14 HIB/one KLD transformations, 981-member input archive and direct version/last/nonlto tail; genuine FHDR/PTHP archives; 83 aliases and original export/symbolset/layout bytes. These inputs are reused read-only from KRN-024. No archive, native helper or compiler is rebuilt in KRN-030.

The runtime is the accepted **287-member** archive from KRN-025, SHA256 `67304a15d82a6213d1ab2c10ff75181eaccc7cba251ed67beb168ad005bebed5`, selected by the explicit LINK-ONLY resource root:

`worktrees/krn-025-20261105/artifacts/xnu-cc-kext/controls-session2/resource-positive`

Its actual path ends in `lib/darwin/libclang_rt.cc_kext_ios.a`. It is compiler support, **not corecrypto**. KRN-025/independent CCREV-002 source/header/member/arithmetic controls remain the provenance for this component; these observations do not establish behavior of all 287 runtime functions.

Runtime source is [LLVM17.0.6](https://github.com/llvm/llvm-project/tree/6009708b4367171ccdbf4b5905cb6a803753fe18/compiler-rt), full SHA `6009708b4367171ccdbf4b5905cb6a803753fe18`, Apache-2.0 WITH LLVM-exception. The accepted one-source `ashrti3.c` correction is preserved explicitly: base SHA256 `628bba0922683d59af5cff1c0b1dd66efffa7bb61fa636ff4e69d7cf34298d3b`, corrected SHA256 `0a3b30723d87b84a4b3cd3d45db3a102bdf65c5cd3e41d2a3820c5c0ebce1a0b`, patch SHA256 `03bd504f95f5c6bc316ddf47ef372db6b074316c197c4eb53dbe5a3025d23a33`. The source converts the cross-word left-shift input to unsigned; original/corrected native object bytes and archive bytes happen to match under the measured compiler. This is not an unmodified-upstream source claim or a full UB-free-runtime claim.

The six controls reject a wrong accepted archive digest, a stale pre-SGAP filelist, literal backend cc restoration, a skipped native export list, forced all-member loading, and actual native driver output from a missing resource directory. The missing-resource control is a **dry-run only**; it genuinely reproduces the driver's reserved-library omission. No negative full link or fake archive/provider is supplied.

## Lazy archive and remaining limits

The runtime archive inventory has **318 definitions and 47 external imports**, including profiling/libc/unwind surfaces. Those are **whole-archive inventory**, not 47 mandatory unresolved symbols for this link. No `-force_load`, `-all_load` or equivalent is used. The preserved native command uses normal lazy archive handling. None of those 47 imports is diagnosed as a missing name in this failed link; the prior object-provider subset has no runtime-definition intersection. The number of runtime members actually selected is **unobserved** because no trace-only linker flag was added. This is not all-member closure or a claim that every runtime component executed or was selected.

The actual 37 errors are exactly the previous selected export requirements, with no new diagnosed name. Their original line/hash mappings remain in `worktrees/krn-024-20261105/artifacts/kernel-provider-link/acceptance-session1/remaining-export-inputs.json`: 35 in [Private.arm64.exports](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/config/Private.arm64.exports#L78) and two in [Private.exports](https://github.com/apple-oss-distributions/xnu/blob/c54f35ca767986246321eb901baf8f5ff7923f6a/config/Private.exports#L776). They cover the IOUnifiedAddressTranslator, pmap/IOMMU and DART/SART/UAT/NVMe/PPL surfaces. KRN-026 remains owned/blocked on genuine providers; KRN-030 changes no export, selector or provider implementation and does not complete that task.

The resource-lookup gate measured by KRN-024 is advanced: the actual native driver now inserts the real qualified archive without literal-library restoration or global installation. Complete link/export closure, all-member runtime behavior, SDK/private Apple ABI, corecrypto/callback security, kernel startup, hardware/recovery and iOS userland remain unqualified. A failed link cannot establish a kernel image, boot, native execution or Apple interoperability. Do not relink merely to manufacture success; genuine new provider inputs and their own task/acceptance are required.

## Commands, resources and handoff

The actual full-link process ran **0.679519 seconds**. Maximum sampled owned process-group plus harness RSS was **289,360 KiB**, with minimum observed MemAvailable **8,704,616 KiB**. The inherited, source-hashed KRN-024 runner caps each subprocess at 120 seconds and 1 GiB aggregate sampled RSS, owns a separate process group and uses finite TERM/KILL escalation. All three subprocesses ended naturally without a stop reason. No compiler build, second full link, SDK/global install, phone, root, MMIO or boot action occurred.

Reproduce only after registering a fresh experiment and preserving accepted parent capsules:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/build/xnu_kernel_runtime_link.py \
  --root /home/egor/dev/pet/s24-ios-exynos --run FRESH_NATIVE --experiment FRESH_REGISTERED_ID
PYTHONDONTWRITEBYTECODE=1 python3 docs/procedures/kernel-runtime-link/verify.py \
  --root /home/egor/dev/pet/s24-ios-exynos --run FRESH_VERIFICATION
```

The independent verifier deliberately checks the original named KRUNLINK-001 capsule. New full-link attempts require their own named acceptance context. Python shared-import bytecode writes and Git lazy fetch/optional locks are disabled. Committed files contain authored harness/docs and metadata only, not Apple/vendor headers, SDKs, firmware or binary archives. Preserve all original LLVM and other component notices.

Owner `codex-team-kernel-runtime-link-20261105-bk`; branch/worktree `team/krn-030-20261105` / `worktrees/krn-030-20261105`; base main `9dc7f35`. All three criteria are ready for coordinator review: coherent immutable native/runtime/patch inputs; actual original frontend/native reserved-resource behavior; actual failed result, controls, hashes and precise unchanged gates. Keep KRN-030 in progress until independent review, integration and common checks. No KRN-003/004/008 or blocked KRN-026 ownership/prefix changed.

Main-relative evidence:

- `worktrees/krn-030-20261105/artifacts/kernel-runtime-link/native-session1/evidence.json`, SHA256 `d618f61fcaa65b7cf638c1fb68ad6300c87c8e669d3078e474ac098e0ba70973`.
- `worktrees/krn-030-20261105/artifacts/kernel-runtime-link/acceptance-session1/evidence.json`.

The native report retains every frontend/expanded/executed backend argv, command/cwd/exit/time/input/tool/output hash, runtime descriptor/member/patch provenance, immutable native input bindings, resources, actual diagnostics and false qualification flags. The acceptance capsule retains independent verifier source and results. Coordinator next: inspect and review this bounded measurement, integrate the scoped commit and run common `make check`; decide completion without promoting it to a full-kernel pass.
