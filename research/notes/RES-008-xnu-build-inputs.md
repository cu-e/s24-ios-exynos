# RES-008: actual XNU build inputs

2026-11-05. Owner: `codex-xnu-inputs-20261105-i`. Category: source-review, with separately recorded checker regression tests. No full kernel, SDK installation, upstream setup or device operation occurred.

## Established result

The earlier Version16.5 prerequisite is an incorrect proxy for the donor's actual SDK metadata. Apple documents SDK16.4 for apps running iOS16.5; Theos's pinned `iPhoneOS16.5.sdk/SDKSettings.json` has Version16.4, DisplayName iOS16.4 and CanonicalName iphoneos16.4. The same donor's xcrun/build wrapper reports/targets16.5 independently. **The iOS16.5 runtime target remains unchanged.** Neither a number match nor a public SDK proves kernel/private ABI completeness.

Primary sources:

- [Apple iOS16.5 release notes](https://developer.apple.com/documentation/ios-ipados-release-notes/ios-ipados-16_5-release-notes) and [Xcode14.3 release notes](https://developer.apple.com/documentation/xcode-release-notes/xcode-14_3-release-notes). Their offered Markdown representations were fetched after the browsing tool could not handle text/markdown. Original responses remain ignored under artifacts/xnu-build-inputs/session1; only hashes/paraphrases are published.
- [Pinned Theos README](https://github.com/theos/sdks/blob/0222fd5413cf4b9af096f37b4621afa2688572f7/README.md) and [SDKSettings](https://github.com/theos/sdks/blob/0222fd5413cf4b9af096f37b4621afa2688572f7/iPhoneOS16.5.sdk/SDKSettings.json). Only these two metadata/text files were fetched, not SDK headers/libraries/binaries. Theos describes private-symbol stubs generated from device-support/IPSW material. Its current metadata pin cannot reconstruct the exact unpinned SDK used by the old donor.
- [S24 embedded base attribution](https://github.com/RNDMBG/iOS-On-S24/blob/c8860decc62c6d6180e609036d027a2997972420/xnu/hackios/README.md): HakiOS d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c, Apple XNU8796.121.2 c54f35ca767986246321eb901baf8f5ff7923f6a. The upstream S24 label “builds” is not a local build result.
- [Exact build scripts](https://github.com/oosexgang/hakios-xnu-kernel/tree/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c/xnu-deps), [environment](https://github.com/oosexgang/hakios-xnu-kernel/blob/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c/xnu-env.sh), [build entry](https://github.com/oosexgang/hakios-xnu-kernel/blob/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c/xnu-build.sh) and [kernel README](https://github.com/oosexgang/hakios-xnu-kernel/blob/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c/xnu/README.md).
- [Theos installation documentation](https://theos.dev/docs/installation-linux) and [cctools-port](https://github.com/tpoechtrager/cctools-port) establish possible Linux tooling paths. They are research leads, not pinned/built local toolchains; no rolling installer ran. cctools-port notes TAPI for SDK text stubs. Its current version is not presumed compatible with this donor.

## Exact script boundaries

New source `hakios-e1s-tools` pins the embedded-era d82c64a3 revision separately from the newer `hakios`87bf4851 driver-research checkout. Kernel archives are appended through REDWOOD_OBJECTS in the actual embedded patch; newer tooling passes HAKIOS_OBJECTS. Reusing the newer entry would not prove the optional object was linked. Both old and new pins remain intact.

The donor configures SDKROOT=iphoneos, ARM64, DEVELOPMENT and MACHINE_CONFIGS=${MACHINE:-BCM2837}, disables LTO/CTF merging, and supplies host compatibility includes. Its target compiler wrapper calls `/usr/bin/clang` or clang++ directly, drops selected diagnostics/Apple-only flags and targets arm64-apple-ios16.5. Its xcrun resolves SDK/platform through environment and searches host/bin then /usr/bin. A working PATH clang does not satisfy that absolute path. No-op codesign/plutil wrappers do not establish code-signing enforcement or plist conversion.

Stage1 requires external base SDK, Mach-O cctools, MIG, unifdef and tcsh. It links a kernel SDK overlay to the base SDK, adds AvailabilityVersions and libdispatch firehose headers/types, and copies pre-generated DriverKit headers from macOS13.3 Kernel.framework for a partial iig substitute. The generator emits some direct wrappers and unsupported stubs; linking them does not establish working DriverKit RPC. The SDK archive URL lacks a recorded content digest. The dependency fetch helper returns early for any existing standalone checkout without checking its revision. These are reproducibility gaps; do not run the installer to discover them again.

Stage2 exports kernel headers, then compiles firehose and the pthread kext into static kernel archives. **Both compilation paths hardcode ARM64_BOARD_CONFIG_BCM2837.** The actual E1S board defines MAX_CPUS10/MAX_CPU_CLUSTERS4, while BCM2837 defines8/1. This is a source-proven profile mismatch; which compiled layouts/symbols are affected remains unmeasured. Stage2 must use an explicitly qualified E1S profile before its archives feed the full kernel.

The donor documents make exit2 from check_all_exports and symbolsets after linking. Apple config/Makefile checks export lists against actual NM-generated allsymbols and invokes kext symbol-set generation. Preserve the failure and actual missing names. A linked Mach-O is a useful intermediate artifact, not a full-build pass or functional iOS hardware proof.

## External source declarations

The exact setup script declares these source pins. Fetch/build/license checks for these components belong to KRN-002/003; declaration is not a completed checkout or build:

| Component | Declared revision | Role |
|---|---|---|
| apple-oss-distributions/AvailabilityVersions | 5d9baee345b3bc72b26c71adc65f94f2d5e9ced2 | availability.pl, release115.4 |
| apple-oss-distributions/libdispatch | a641558f447659d90ad002ef0ee6f0212273fbfc | private firehose header/types and kernel archive,1415.100.11 |
| apple-oss-distributions/libpthread | a6c70ca0e544347a0377babf748f831577ec24f9 | pthread kernel archive,514.100.2 |
| markmentovai/bootstrap_cmds | f337e600741638896fb6056ce87c6479f74b89a3 | Linux-buildable MIG source declared by donor |
| tcsh-org/tcsh | b7db07931546178c4cb2542b5fc850c483628ed5 | host csh for XNU configuration |
| fanf2/unifdef | 08d12cd3059fe072929ea001ad9833f5487fd355 | host conditional-header generator |

Actual SDK/kernel DriverKit headers and full input provenance remain unavailable locally. Existing Android/loader/LLVM tools are not replacements for them. No Apple SDK or userspace was downloaded to close these gaps.

## Local inventory and implementation

`tools/build/describe_kernel_inputs.py` implements the [component profile](../../fixtures/public/xnu-build-inputs/profile.json). It does not execute donor wrappers or build scripts. It checks the local tool root/origin/exact pin/cleanliness/file hashes, explicit SDK metadata and directories, actual absolute compiler requirements, Mach-O tool paths, generated host tools, overlay files,17 header names and prepared E1S source report/file digests. Empty archives do not count as inputs. Complete SDK provenance/ABI and kernel compilation always remain unverified by this inventory.

The [actual session1 inventory](../../fixtures/public/xnu-build-inputs/input-inventory-session1.json) exits2: exact embedded tools and previous corrected E1S source preparation verify, while complete SDK, overlay, DriverKit headers, cctools, generated host tools, /usr/bin/clang and clang++ are absent at the checked paths. PATH clang exists; PATH clang++, autoreconf and automake do not. This is a bounded configured-path survey, not a whole-machine absence claim. No installed package/global environment or phone state changed.

Five checker regressions cover the real16.5-label/16.4-metadata distinction, bounded malformed metadata/empty archives, stale prepared-source hashes, PATH versus absolute compiler paths, and proof that supplied donor scripts are never sourced. `make check` passed113 tests, including the five new input diagnostics; [check evidence](../../fixtures/public/xnu-build-inputs/checks.json) records the actual inventory exit2 separately from the passing source audit. The earlier KRN-001/NAT-001 task bytes and their owner's reservations remain unchanged.

## Next concrete work

Follow [the build-input procedure](../../docs/procedures/xnu-build-inputs.md). KRN-002 can build/qualify open-source host generators and Mach-O tooling independently of Apple userspace. KRN-003 isolates explicit host compiler selection, real E1S dependency compilation/layout checks and reproducible input provenance. Qualified artifacts can then be consumed by the original KRN-001 owner; no automatic ownership transfer or full-build claim occurs here. This source review removes a false numeric SDK obstacle while exposing the real missing inputs and unresolved contracts.
