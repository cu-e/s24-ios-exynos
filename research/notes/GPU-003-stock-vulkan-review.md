# GPU-003 — independent review of the stock Vulkan baseline (GPU-016)

Date: 2026-11-10. Reviewer: `claude-takeover-20261110-6c8f`, who did not run the measurement. Evidence category: **android-userland**, using the Android vendor driver. This is not GPU under XNU and not native evidence. Nothing was rerun on the phone for this review.

## What was reviewed

- `docs/procedures/gpu-016/evidence.json`, measured by `claude-gpu-stock-20261110-g3` on 2026-11-10 between 04:47:46 and 04:48:47 UTC.
- The eight artifacts it lists. All eight SHA-256 values were recomputed on 2026-11-10 and match:
  - `artifacts/gpu-016/session-001/report.json`;
  - `artifacts/gpu-016/session-001/cooldown.json` and `cooldown-2.json`;
  - the APK `artifacts/android-probe/apk-session7/s24-vulkan-probe.apk`;
  - the GPU-014 inventory `artifacts/gpu-014/session-002/report.json`;
  - the GPU-016 note, handoff and run script.

## GPU-003 criteria

| Criterion | Assessment |
|---|---|
| Dated inventory and the APK hash are available. | **Met.** Device inventory `devices/local-2026-11-10-session1.json` (SM-S921B, S921BXXS9BYH3). APK SHA-256 `1187f632…afd6`, the TST-002/EMULATOR-016-qualified bytes. Its source digest `ff4e24ce…f6ce` was recomputed and matches the in-app reports. |
| Renderer, extensions, frame results and temperature observations are saved. | **Met.** Renderer: Samsung Xclipse 940, Vulkan 1.3.279, driver raw 100675593, identical in all runs and equal to GPU-014. Extensions: 153 device extensions from GPU-014 (not re-enumerated by the app, as the evidence states). Frame results: 10 offscreen 256×256 clear/readback runs, all 65 536/65 536 pixels matching, 8.45–19.48 ms app wall time, median 10.32 ms. Temperatures: thermal HAL readings at four points, AP 33.9 → 44.8 °C, thermal status 0 throughout. `/sys/class/thermal` was not readable by the shell user, which the evidence records. |
| Stop is tested without rebooting; negative cases are documented. | **Met, with the limitation stated.** Force-stop was exercised 4 times and the driver stayed usable afterwards. The in-app Stop was exercised twice (raced 10 ms and 5 ms after Start), but the ~10 ms run finished first, so cooperative cancellation of submitted GPU work was **not observed** on the phone. No reboot; uptime increased; the package was uninstalled and its absence verified. Observed and untested negative cases are listed. Untested: GPU hang/fence timeout, interrupting submitted work, storage failure, shaders, presentation, sustained load. |

## Limits carried forward

- One offscreen transfer/clear/readback fixture. No shaders, no swapchain, no GPU timestamps, no GPU temperature.
- App wall time only. The host-side timings include ADB polling.
- The original measurement had no independent reviewer. This note is that review; it adds no new measurement.
