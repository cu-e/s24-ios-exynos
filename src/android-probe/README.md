# Android Vulkan probe

A native Android utility with Start test, Stop and Save report. The shared C++ core clears a 256 × 256 RGBA8 image to opaque red, reads it back and compares all 65,536 pixels exactly. This first test measures transfer/clear/readback; it does not exercise shaders, Metal or display presentation. See [SPEC.md](SPEC.md).

## Build

```sh
python3 src/android-probe/build.py --run unique-build
```

Uses installed SDK/platform 35, build-tools 35.0.0, NDK 28.2.13676358 and javac 25.0.1. Builds ARM64 and x86_64 JNI libraries, aligns and signs the APK with a local development key. It downloads nothing and never invokes ADB. APK, key and build report remain under ignored `artifacts/android-probe/unique-build/`. The report records actual tool commands, source commit, build-time source digest, APK digest and size. The application embeds the same source identity in its JSON reports. Source changes after a build require a new build for a matching identity.

The current local APK is `artifacts/android-probe/apk-session5/s24-vulkan-probe.apk`, 11,444,772 bytes; SHA-256 `6e5bbc75f3c76db45c8c826de2e42a3f7f488ee217050e7e93200db7498c3943`. The report hashes each compiled source/manifest/build-script input; documentation and emulator helpers are excluded from this identity. This APK includes the reviewed theme/restart/storage fixes. It has not completed an emulator fixture run. TST-002 tracks the remaining UI/runtime qualification.

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

Requires the existing Android 36 Google Play x86_64 system image and emulator. Creates a fresh task-owned AVD on a dedicated port, copies only the host public ADB key into its configuration directory, and addresses every ADB command to that explicit emulator serial. It installs only on this emulator, exercises the real fixture, checks saved-result restoration, and captures light/dark layouts with larger fonts. Diagnostic failures are retained. It terminates only the process it launched, and never restarts the shared ADB server or adopts another emulator.

## Phone and stop limits

GPU-003 remains the primary-S24 installation and measurement gate; that scope is not currently authorized. No primary-phone install command is part of this procedure. The APK needs no root, network, accessibility, device-admin or broad storage permission. Save report uses Android's document picker; results otherwise remain in app-private storage.

Stop is cooperative. One submission runs at a time; fence polling has a four-second budget. Activity changes request cancellation and cannot start a second worker while the first runs. In-flight resources are retained on timeout/error and further runs require process termination. Calls inside a GPU driver can still block; app termination cannot guarantee kernel GPU recovery. RADV loading belongs to GPU-005 and native XNU GPU support to later tasks.

The initial light-screen review found no clipping. Three source findings were corrected and reviewed: system theme changes recreate the Activity, restart guidance names Android Force stop, and private-storage failures retain the actual in-memory report for export instead of becoming false GPU failures. The review disposition remains **recapture**, with dark/large-font/result/error/export/lifecycle qualification pending. See [review](../../fixtures/public/host-lab/ui-review.json).
