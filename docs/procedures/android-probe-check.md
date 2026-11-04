# Stock Vulkan probe host and emulator checks

Build with `python3 src/android-probe/build.py --run UNIQUE`. The script uses installed SDK 35, build-tools 35.0.0, NDK 28.2.13676358 and javac 25.0.1. It neither downloads dependencies nor invokes ADB. Build reports record actual commands and source hashes. Development keys and APKs remain ignored local artifacts. A build pass does not establish a phone test.

Run `python3 -m unittest discover -s tests -p test_vulkan_probe.py -v` for shared native-core checks. Host Vulkan results use a selected Mesa software ICD and are never presented as Xclipse measurements. Test fault injection only overrides host fence polling; it does not hang a GPU.

Emulator checks use a fresh task-owned AVD and explicit emulator serial for every ADB operation. Install only on that emulator, open the app, run the image check, read the app-owned report, background/reopen and verify state, inspect readable layout with system insets and larger fonts. Stop the task-owned emulator after checking it. Never use unqualified `adb install`, `adb shell` or the owner's phone for these checks.

GPU-003 remains the primary-S24 installation/measurement gate. Later app-local RADV loading is separate GPU-005 work. Device permission changes, su, root, production subscription access and native boot are outside this procedure.

Cold Google Play emulator images may report boot completion before System UI settles. The harness uses four guest cores, 3 GiB RAM and a bounded 20-second settling period. UI dump failures retain raw output and screenshots. An optional explicitly reviewed Start coordinate is a diagnostic fallback for unavailable semantic automation, never accessibility acceptance. System UI ANRs or missing app reports remain failed/inconclusive emulator results; host Vulkan passes do not override them.
