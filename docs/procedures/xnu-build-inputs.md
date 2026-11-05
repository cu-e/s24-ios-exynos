# E1S kernel inputs: inspect components before building

The first runtime target remains iOS16.5 / XNU8796.121.2 / E1S. A public SDK release number, a Theos directory name and the donor's compiler target are different inputs. Do not rename SDK metadata or replace the selected runtime to make a presence check pass.

```sh
python3 tools/sources.py fetch hakios-e1s-tools theos-sdk-metadata
python3 tools/build/describe_kernel_inputs.py \
  --prepared-run artifacts/xnu-prepare/corrected-touch-xnu-session1
```

The second command currently exits2 with an actual missing-component inventory. It is read-only: no donor script, SDK installer, compiler, device command or dependency build is run. The first command fetches only the named source text and two SDK-metadata/README files, not an SDK. Use `tools/sources.py verify` instead when checkouts already exist.

When explicit local inputs are supplied, add:

```sh
python3 tools/build/describe_kernel_inputs.py \
  --sdk /path/to/local/base.sdk --theos /path/to/local/theos \
  --overlay /path/to/generated/iPhoneOS16.5.xnu.sdk \
  --driverkit-headers /path/to/Kernel.framework/Headers \
  --prepared-run artifacts/xnu-prepare/corrected-touch-xnu-session1
```

Paths are examples, not claims that those inputs exist. The tool records source pins/hashes, expected absolute compiler paths, Theos Mach-O tools, generated MIG/unifdef/tcsh tools, kernel SDK overlay files,17 DriverKit header names and the prepared E1S report/required-file digests. It reports missing and unresolved components, never a successful kernel build. SDK metadata matching only identifies that metadata file. Archive architecture, actual compiler/linker behavior, whole-SDK provenance and symbol/export ABI still require real build checks.

## What changed in the prerequisite interpretation

[Apple's iOS16.5 release notes](https://developer.apple.com/documentation/ios-ipados-release-notes/ios-ipados-16_5-release-notes) identify the iOS16.4 SDK in Xcode14.3. The pinned [Theos metadata](https://github.com/theos/sdks/blob/0222fd5413cf4b9af096f37b4621afa2688572f7/iPhoneOS16.5.sdk/SDKSettings.json) inside `iPhoneOS16.5.sdk` likewise reports Version16.4, CanonicalName iphoneos16.4. Its README describes patched private-symbol stubs. These facts do not prove a stock public SDK supplies all private/kernel inputs.

The embedded-compatible donor [xnu-env.sh](https://github.com/oosexgang/hakios-xnu-kernel/blob/d82c64a3a31cd27a0a0afbf6e213e467e44b1b4c/xnu-env.sh) sets XNU_SDK_VERSION=16.5; its xcrun reports that value without parsing SDKSettings. Its compiler wrapper targets arm64-apple-ios16.5. Preserve that runtime/build profile while qualifying actual inputs. The old `kernel_preflight.py` literal Version16.5 check would reject the reviewed Theos metadata; its earlier blocked result remains historical evidence. This new component inventory supersedes that numeric assumption for input analysis without editing KRN-001's reserved files or completing its claim.

## Concrete build sequence

1. Use `hakios-e1s-tools` at d82c64a3..., matching the S24 embedded base. The newer independent `hakios` pin changes REDWOOD_OBJECTS to HAKIOS_OBJECTS and other build behavior; it is not a drop-in replacement.
2. Build/qualify host MIG, unifdef, tcsh and Mach-O tooling from reviewed pinned open source in a private artifacts prefix (KRN-002). Do not install global compiler symlinks or run Theos's rolling network installer. Record compiler provenance and actual behavior with source fixtures.
3. Review explicit locally supplied base SDK and macOS13.3 Kernel.framework headers. No SDK or Apple userspace has been acquired by this task. The donor setup downloads an unhash-pinned macOS SDK archive and trusts any pre-existing dependency Git checkout; do not execute it as a reproducible installer.
4. Build an owned SDK overlay: pinned AvailabilityVersions script, libdispatch firehose private header/types, then export the **E1S** kernel's headers and compile libfirehose_kernel.a and libpthread_kext.a against them. The donor hardcodes ARM64_BOARD_CONFIG_BCM2837 in both library paths. Audit/repair this and select the actual host compiler explicitly in KRN-003. Main-kernel MACHINE=E1S alone does not change those library defines.
5. Check real arm64 Mach-O objects/archive members, target flags, required symbols and layout compatibility. The BCM2837 and E1S profiles differ (eight/one versus ten/four CPU/cluster limits); actual affected ABI requires measurement. Never infer a proven corruption from the define mismatch alone.
6. The KRN-001 owner can consume qualified inputs and run the actual kernel build. Preserve compile/link and check_all_exports/symbolset exit statuses. Donor documentation accepts make exit2 after linking; this project does not call that a clean full build. Partial iig implementations and no-op codesign are separately recorded limitations, not functional DriverKit or iPhone security.
7. Hardware boot remains behind NAT recovery/control authorization and measurement. A kernel binary, including a clean build, does not qualify graphics, radios or a return to Android.

See [RES-008 findings](../../research/notes/RES-008-xnu-build-inputs.md), [input profile](../../fixtures/public/xnu-build-inputs/profile.json) and [actual inventory](../../fixtures/public/xnu-build-inputs/input-inventory-session1.json). No primary-phone operation is part of this procedure.
