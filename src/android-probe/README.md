# Android Vulkan probe

A native Android utility with Start test, Stop and Save report. The shared C++ core clears a 256 × 256 RGBA8 image to opaque red, reads it back and compares all 65,536 pixels exactly. This first test measures transfer/clear/readback; it does not exercise shaders, Metal or display presentation. See [SPEC.md](SPEC.md).

## Build

```sh
python3 src/android-probe/build.py --run unique-build
```

Uses installed SDK/platform 35, build-tools 35.0.0, NDK 28.2.13676358 and javac 25.0.1. Builds ARM64 and x86_64 JNI libraries, aligns and signs the APK with a local development key. It downloads nothing and never invokes ADB. APK, key and build report remain under ignored `artifacts/android-probe/unique-build/`. The report records actual tool commands, source commit, build-time source digest, APK digest and size. The application embeds the same source identity in its JSON reports. Source changes after a build require a new build for a matching identity.

The current local APK is `artifacts/android-probe/apk-session7/s24-vulkan-probe.apk`, 11,461,156 bytes; SHA-256 `1187f632f1b1bd20d4e8ce0c29d21959b4f51760de3e17e55064fe2d8f23afd6`. The report hashes each compiled source/manifest/build-script input; documentation, instrumentation and emulator helpers are excluded from this identity. The app verifies committed report bytes because AtomicFile can log some commit failures without throwing. It preserves genuine measured JSON and shows the existing storage warning when readback fails; this is not a power-loss durability guarantee.

EMULATOR-016 ran this exact installed digest and source digest `ff4e24ce95373fd1ad05fc3e0a52cc67195bc2ad04e00df8ff1ea6b622ddf99b` on a fresh API36/SwiftShader guest. All16 expanded cases passed in both themes with font scale1.3. APK5's earlier basic pass and all failed attempts remain separately retained. See [runtime evidence and limits](../../research/notes/TST-002-runtime-qualification.md). System status/navigation icons now follow the actual theme, correcting the independent APK6 review finding. No physical S24 or ARM64 JNI execution occurred.

## Host checks

```sh
python3 -m unittest discover -s tests -p test_vulkan_probe.py -v
python3 -m unittest discover -s tests -p test_probe_lifecycle.py -v
```

Requires a C++ compiler, Vulkan headers/loader and Mesa Lavapipe at `/usr/share/vulkan/icd.d/lvp_icd.x86_64.json`; the lifecycle check uses javac/java. Tests execute the actual core, compare all pixels, cancel before submission and inject a non-completing host fence with a finite deadline. A separate process-wide admission test rejects overlapping workers and retains a sticky restart requirement. These checks never issue ADB commands or simulate a successful S24 result.

## Isolated emulator

```sh
python3 src/android-probe/emulator_check.py \
  --apk artifacts/android-probe/unique-build/s24-vulkan-probe.apk --run unique-emulator
```

Requires the installed Android36 Google Play x86_64 revision7 extension17 image and emulator36.4.9.0. Creates a fresh task-owned AVD, copies only the host public ADB key into its configuration directory, and uses a private loopback ADB server with USB exclusion and automatic emulator/mDNS discovery disabled. The sole transport and AVD name must match before any guest mutation. It uses a720x1560/280dpi viewport, two CPUs and2GiB guest RAM. Diagnostic failures and exact helper bytes are retained; only its own process groups are terminated. It never restarts the shared server or adopts another emulator.

The basic command above checks genuine pixels/restoration/themes. Add the separately built [qualification APK](qualification/README.md) for actual export, commit/startWrite errors, lifecycle, restart UI, live theme recreation and live AX/control metrics. [Procedure](../../docs/procedures/emulator-qualification.md) explains preregistration, controlled fault origins, cleanup and unavailable Android15 coverage. Test instrumentation never becomes part of the production APK.

## Phone and stop limits

GPU-003 remains the primary-S24 installation and measurement gate; that scope is not currently authorized. No primary-phone install command is part of this procedure. The APK needs no root, network, accessibility, device-admin or broad storage permission. Save report uses Android's document picker; results otherwise remain in app-private storage.

Stop is cooperative. One submission runs at a time; fence polling has a four-second budget. Activity changes request cancellation and cannot start a second worker while the first runs. In-flight resources are retained on timeout/error and further runs require process termination. Calls inside a GPU driver can still block; app termination cannot guarantee kernel GPU recovery. RADV loading belongs to GPU-005 and native XNU GPU support to later tasks.

The earlier [source review](../../fixtures/public/host-lab/ui-review.json) retained a recapture verdict. Fresh APK7 runtime captures now cover initial/result/storage/restart states in both themes, genuine document-picker export and real worker/Activity recreation. The initial independent review returned fix; the bounded APK7 confirmation returned disposition: ship for those two fixes and introduced regressions. Review evidence is retained separately; spoken TalkBack remains unqualified. Keep the physical S24 gate separate.
