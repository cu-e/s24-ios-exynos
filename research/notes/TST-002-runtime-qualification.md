# TST-002: Android probe runtime qualification

Date: 2026-11-05. Owner: `codex-emulator-qualification-20261105-h`.
Evidence category: **host-test**, using an actual Android guest and genuine JNI Vulkan work. No primary S24 command, installation, ARM64 execution or native XNU qualification is part of this task.

## Target and changes

The current APK7 is `artifacts/android-probe/apk-session7/s24-vulkan-probe.apk`, 11,461,156 bytes, SHA256 `1187f632f1b1bd20d4e8ce0c29d21959b4f51760de3e17e55064fe2d8f23afd6`. Its compiled-input SHA256 is `ff4e24ce95373fd1ad05fc3e0a52cc67195bc2ad04e00df8ff1ea6b622ddf99b`. Build reports and snapshots identify the actual working-tree inputs against parent commit `27451a28ff21e4ab69aa6305cb0ffd94ccd2aed4`; the parent commit alone does not describe the changed APK.

The production changes verify committed report bytes after AtomicFile.finishWrite and select system status/navigation icon appearance for the actual theme at creation/focus. The existing layout, native framework controls, fixture and cooperative Stop contract remain the design authority.

The [AOSP AtomicFile implementation](https://android.googlesource.com/platform/frameworks/base/+/HEAD/core/java/android/util/AtomicFile.java) can log sync/rename failures without throwing. The app now checks that the committed file actually equals its genuine measured JSON. Failure retains that JSON in process memory and presents the existing export warning. This verifies readable bytes, not power-loss durability. The correction was source-based: the old APK5 run failed its earlier export check before reaching the commit-fault case. Do not claim a reproduced pre-fix commit failure.

## Reproduction and isolation

```sh
python3 src/android-probe/build.py --run unique-target-build
python3 src/android-probe/qualification/build.py --run unique-qualifier-build \
  --target-build artifacts/android-probe/unique-target-build
python3 src/android-probe/emulator_check.py \
  --apk artifacts/android-probe/unique-target-build/s24-vulkan-probe.apk \
  --qualifier-apk artifacts/android-probe/unique-qualifier-build/qualifier.apk \
  --run unique-guest-run --port 5582 --adb-server-port 5482
```

Register a new experiment first. Run names must be new. Builders use installed SDK/platform35, build-tools35.0.0, NDK28.2.13676358 and javac25.0.1; no SDK download or upstream setup execution occurs. APKs, development keys and full logs remain ignored. The production build identity excludes documentation, the emulator helper and the separate qualifier; these have their own snapshots and hashes.

The guest uses installed emulator36.4.9.0 and Android36 Google Play x86_64 revision7 extension17, SwiftShader, 720x1560/280dpi, two CPUs and2GiB RAM. Font scale is1.3. Installed Android15 coverage is unavailable. Official Google repository range reconstruction found an API35 Google APIs x86_64 revision9 candidate (1,738,815,903 bytes); local license acceptance could not be established, so neither new terms nor the archive were fetched. See [environment follow-up](../../fixtures/public/android-ui/environment-followup.json). This is a bounded environment survey, not proof that no other SDK exists anywhere on the machine.

Every launcher command selects the owned emulator serial. A separately launched private ADB server filters USB to an unused task selector, disables automatic emulator-port scanning and mDNS auto-connect, and must expose exactly the owned transport. The AVD name is checked before mutations. Shared ADB and unrelated AVDs are never reset, adopted or terminated. Cleanup targets only the process groups launched for this run and records their termination.

A transient offline response permits at most30seconds of observation while those same processes remain live, followed by AVD-name and guest-boot-ID verification. Only reads and allowlisted idempotent removal of fixed test-owned files may be retried once. Native work, instrumentation, installs, input and settings are never replayed. No automatic new guest or shared-server reset is hidden in recovery. Successful runs without an offline event do not qualify this recovery branch at runtime.

## Runtime matrix and origins

The separate qualifier verifies the installed target APK digest and source identity in genuine JNI JSON. Each theme covers initial, run, storage, commit, lifecycle, restart, export and theme cases. The 256x256 opaque-red fixture compares65,536 pixels exactly; this measures transfer/clear/readback, not shaders, Metal, presentation or Xclipse.

- Ordinary Run and export use actual pointer events; export traverses the actual system document picker and compares the saved JSON with the genuine report.
- Storage and commit faults create nonempty directories at fixed app-private test paths. The app must retain real measured data across Activity recreation. These are controlled filesystem faults, not full-disk or crash tests.
- Lifecycle invokes the real Start listener on the main thread, observes the actual busy RunGate, requests real Activity recreation, waits for worker retirement/report display, then runs another genuine fixture. The trigger is explicitly programmatic.
- Restart injects an idle RunGate poison through reflection and checks disabled Start and truthful Force stop/reopen guidance. It does not induce a GPU hang or demonstrate phone recovery.
- Theme changes actual system night mode and observes Activity recreation, retained report and correct system-bar appearance. Native screenshots are separate visual evidence; controller flags alone do not establish legibility.
- Real accessibility nodes, labels, enabled states and48dp button heights are captured. Spoken TalkBack/gesture behavior remains unqualified.

## Immutable experiment history

| Experiment | Actual outcome and limit |
|---|---|
| EMULATOR-001 through007 | Historical guest/runtime failures retained in their original evidence; host-core success did not qualify the APK |
| EMULATOR-008 | Python indentation error before guest launch |
| EMULATOR-009 | APK5 basic real pixels, restoration and theme captures pass; broader cases and visual review still pending; internal emulator adb-e attempts observed failing with multiple AVDs |
| EMULATOR-010 | Unsupported private-listener syntax; no emulator launched |
| EMULATOR-011 | Delayed pointer did not observe busy overlap; no lifecycle pass |
| EMULATOR-012 | Actual result/AX passed; fixed picker delay exposed no usable Save control; no export or commit-fault qualification |
| EMULATOR-013 | APK6 all16 runtime cases pass; independent native review separately returned **fix** for light status-icon contrast and stale verification prose |
| EMULATOR-014 | APK7 early light cases pass; ADB disconnect during cleanup caused a retained failure, followed by owned-process termination; disconnect cause unknown |
| EMULATOR-015 | APK7 light set and early dark cases pass; qualifier raced an off-main-thread report read. Retained status/screenshot show the actual cancelled result; this does not prove application data loss |
| EMULATOR-016 | **Pass:** exact APK7/qualifier9 all16 cases, genuine pixels/export, main-thread lifecycle observation, both storage faults and theme-correct bar flags. Both owned processes exited and ports5582/5482 closed; no offline recovery exercised |

Original evidence and source-labeled captures are never overwritten. Public sanitized JSON lives in `fixtures/public/android-ui/`; full run artifacts and source snapshots remain under `artifacts/android-probe/`. The first review packet and its **fix** verdict remain separate from the post-fix confirmation in [review-packet-apk7.json](../../fixtures/public/android-ui/review-packet-apk7.json), with an explicit old-to-new capture mapping.

## Completed host acceptance and remaining gates

TST-002 acceptance is met for the host guest: EMULATOR-016 passes all16 current-APK cases, `make check` passes108 tests, and the [bounded independent verdict](../../fixtures/public/android-ui/review-apk7.json) is **disposition: ship** for the two original findings and introduced regressions. The original APK6 **fix** verdict remains immutable. This is not a new whole-surface review or phone qualification. GPU-003 is the separately authorized primary-phone stock-Vulkan gate. Native SGPU, iOS Metal/presentation, panel/DSC/touch and full-system reliability remain their own tasks. There is no working native iOS support from this host result.

RES-008 follows with exact donor build-tool/sysroot analysis. The selected iOS16.5 runtime, Apple's official SDK release number and a custom Theos sysroot label must be distinguished before changing any full-kernel prerequisite. KRN-001's existing owner/reservation and immutable evidence remain intact.
