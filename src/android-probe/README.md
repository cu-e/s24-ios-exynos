# Android probe — future app

No implementation exists yet. GPU-001/GPU-002 will define the minimal architecture and toolchain.

Target: a separate APK without root, short Vulkan tests, Stop, timeout, JSON/frame export and version/commit in each report. Start with the stock driver, then a separate app-local RADV experiment. Do not add accessibility, device-admin or system library replacement.

The app cannot guarantee protection from a kernel GPU driver failure. Installing it requires android-app scope, which is not currently authorized.
