# Android Vulkan probe contract

Package: dev.egor.s24probe. Minimum API 29; build/target SDK 35. Build ARM64 for the S24 and x86_64 for host emulators. First backend is the stock Vulkan loader. No custom driver replacement, networking, root or privileged permissions.

## First fixture

Create one 256x256 RGBA8_UNORM optimal image, clear to opaque red, copy into a host-visible staging buffer and compare every byte against (255,0,0,255). Pixel tolerance is zero. Report the actual pixel mismatch count. This validates transfer/clear/readback, not shaders, Metal or display scanout. Memory allocation is capped at 128 MiB in total and geometry is fixed.

## Execution and stop

One worker and one submission at a time; Start is disabled while running. Stop sets a cooperative cancellation flag checked before submission and during finite fence polling. Before submission it cancels immediately. After submission the engine must wait for completion before releasing resources. Fence polling has a four-second upper budget; no vkDeviceWaitIdle with an unbounded wait. Vulkan calls themselves can still block inside a driver. On a GPU timeout/error, stop further submissions and require a new process/session. Retain in-flight resources instead of freeing memory still in use by a GPU. A separate host process deadline can terminate the app process; it cannot guarantee kernel GPU recovery.

Backgrounding/destroying the Activity requests cancellation. Rotation does not launch another worker. Report cancellation separately from failure/pass; unsupported Vulkan is a measured error, not a synthetic success.

## Interface and export

One native screen, title and concise task instructions, Start test, Stop, Save report, and selectable measured result. Use standard Android controls with 48 dp minimum targets, system insets, light/dark themes and scalable text. Status is announced for accessibility. No decorative animation, fake progress, external service or marketing copy. The approved task is narrow; there is no visual identity tournament or additional user preference needed.

Write JSON atomically under the app's files directory after actual execution. Export through Android's document picker, requiring no broad storage permission. Include schema version, fixture, environment, application/source version, device name, vendor/device/driver API values, outcome, error, elapsed time and compared/mismatched pixels. Exclude UUID/LUID, serials, MAC, IMEI, accounts, subscriptions and personal content. A probe report is an artifact, not automatically task-completing evidence.

## Host/emulator acceptance

Compile the shared measurement core as a host Vulkan executable. Exercise normal readback, cancellation before submit and deadline handling. Build and sign the APK locally; keep the key and APK outside Git. If an emulator is available, use a fresh dedicated emulator instance and explicit emulator serial for every ADB action. Never let a host test select the attached physical phone. Capture UI and lifecycle observations from that emulator and label them accordingly.

Actual S24 measurements and later RADV comparison belong to GPU-003/GPU-005 and require their device scope. Shader rendering and Metal translation remain GPU-004 and later tasks.
