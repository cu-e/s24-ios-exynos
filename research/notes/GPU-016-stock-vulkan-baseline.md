# GPU-016: stock Vulkan baseline on the S24 inside Android (for GPU-003)

Evidence class: android-userland, measured 2026-11-10 04:47:46–04:48:47 UTC on SM-S921B, firmware
S921BXXS9BYH3, through already-authorized ADB as the shell user. Authority: decision 0002, item 4
(`android-app`). No su, no settings change, no reboot. This is the Android baseline with the vendor
driver. It says nothing about a GPU under XNU.

GPU-016 is a child of GPU-003. GPU-003 could not be claimed because its broad paths (`artifacts/`,
`research/notes/`, `devices/`) overlap reservations held by NAT-001, KRN-003 and KRN-041.

## What ran

- APK: the exact TST-002-qualified bytes `artifacts/android-probe/apk-session7/s24-vulkan-probe.apk`,
  11,461,156 bytes, SHA-256 `1187f632f1b1bd20d4e8ce0c29d21959b4f51760de3e17e55064fe2d8f23afd6`. EMULATOR-016
  ran this digest. The current compiled-input digest, recomputed with build.py's algorithm, is still
  `ff4e24ce95373fd1ad05fc3e0a52cc67195bc2ad04e00df8ff1ea6b622ddf99b`, so nothing was rebuilt. A rebuild
  would not be byte-identical anyway, because build.py generates a fresh signing key and embeds the
  commit. Every app report carried `source_sha256` `ff4e24ce…` and `source_commit` `27451a28…`.
- Driver: `docs/procedures/gpu-016/run_probe.py --run session-001`, exit 0, 60.8 s of device time,
  96 ADB commands, each with a timeout. Output: Git-ignored `artifacts/gpu-016/session-001/report.json`.
- Install: `adb install --user 0` (no `-r`/`-d`). `pm list packages` without `--user` fails here with a
  SecurityException for user 150, so the install and every package query were limited to user 0. The
  package record showed user 150 `installed=false`.
- Fixture: one 256 × 256 RGBA8 optimal image, cleared to opaque red, copied to a host-visible buffer and
  compared exactly. This is offscreen transfer, clear and readback. No shader, no swapchain, nothing
  presented on screen.

## Renderer

| Field | App report (10 runs, all identical) | GPU-014 `cmd gpu vkjson` |
|---|---|---|
| deviceName | Samsung Xclipse 940 | Samsung Xclipse 940 |
| apiVersion | 4206871 = 1.3.279 | 1.3.279 |
| driverVersion raw | 100675593 (24.3.9 under VK_MAKE_VERSION) | 100675593 |
| vendorID / deviceID | 5197 = 0x144d / 39846400 = 0x2600200 | 0x144d / 0x2600200 |

The app does not enumerate extensions. The identity matches GPU-014 on every field, on the same
firmware on the same day, so the 153 device extensions in `artifacts/gpu-014/session-002/report.json`
describe this driver. They were not enumerated again. The app instance requests API 1.1. The probe
process's own HWUI uses the Vulkan render engine (`will use render engine as VK` in its logcat), so the
vendor driver is already loaded before the first probe run.

## Image results

Ten single-submission runs, every one with outcome `pass`, 65,536 pixels compared, 0 mismatched and
`requires_process_restart=false`:

| Run | Context | elapsed_ms |
|---|---|---|
| 1 | first run after install, first process | 17.789 |
| 2–5 | same process, about 1 s apart | 9.967, 19.478, 9.991, 13.593 |
| 6 | fresh process, Stop raced 10 ms after Start | 10.201 |
| 7 | fresh process, Stop raced 5 ms after Start | 11.763 |
| 8 | after run 7, same process | 10.436 |
| 9 | force-stop raced 50 ms after Start (the run finished first) | 8.446 |
| 10 | after relaunch following force-stop | 9.524 |

Min 8.446 ms, median 10.319 ms, mean 12.119 ms, max 19.478 ms, about 121 ms in total. `elapsed_ms` is
the app's wall time from vkCreateInstance to teardown. It includes device creation, allocation, one
submit, a fence wait and the CPU comparison. It is not GPU execution time, because there are no
timestamp queries, and it is not a frame rate.

## Temperatures

Source: the thermal HAL through `dumpsys thermalservice`. Only temperatures and thermal status were
kept. `/sys/class/thermal/thermal_zone*/type` and `temp` read back empty for the shell user.

| Point (UTC) | Status | AP | SKIN | BAT | CP | PA | USB |
|---|---|---|---|---|---|---|---|
| 04:47:47 before install | 0 | 33.9 | 32.9 | 31.7 | 33.4 | 33.7 | 30.4 |
| 04:48:22 after runs 1–5 | 0 | 38.9 | 34.7 | 33.1 | 37.6 | 37.7 | 30.6 |
| 04:48:46 after stop tests | 0 | 44.8 | 35.4 | 33.2 | 39.0 | 38.5 | 30.9 |
| 04:48:47 after uninstall | 0 | 48.5 | 36.2 | 33.6 | 41.0 | 40.3 | 31.1 |
| 04:49:44 read-only follow-up | 0 | 47.0 | 37.3 | 35.3 | 42.4 | 41.7 | 30.9 |
| 04:51:15 read-only follow-up | 0 | 38.5 | 36.2 | 35.0 | 38.0 | 38.2 | 31.1 |

Thermal status stayed 0 (none) throughout. AP rose about 15 °C during the 60-second session and fell
back to 38.5 °C about 2.5 minutes after it. The probe's GPU work totalled about 121 ms. In the same
window the host drove an install, three cold app launches with JIT compilation and 18 uiautomator
hierarchy dumps. A read-only pre-check about 3.6 minutes earlier showed AP 35.6 °C, with a cached AP
value of 44.9 °C. The rise therefore can't be attributed to the Vulkan fixture. The HAL lists no
GPU-specific sensor. The follow-up readings are in
`artifacts/gpu-016/session-001/cooldown.json` and `cooldown-2.json`.

## Stop tests (no reboot: uptime 417602.68 s → 417663.26 s → 417720.75 s → 417811.73 s)

- **Process termination** (`am force-stop dev.egor.s24probe`): ran 4 times. `pidof` was empty every
  time. Each relaunch showed `Previous result: pass` from the saved report and started no GPU job, because
  `recorded_at` was unchanged. The run that followed passed. A force-stop sent 50 ms after Start landed
  after that run had already finished and committed its report, so it ended an idle process, not GPU work
  in flight.
- **In-app Stop**: the Stop tap was raced 10 ms and then 5 ms after the Start tap. Both shell commands
  returned in about 0.13 s. Both runs finished with `pass`, so the stop request arrived after a run of
  about 10 ms. The Stop button was disabled after every completed run. The app's `cancelled` outcome was
  **not observed on the phone**. A workload this short cannot be pre-empted by UI injection. Host tests
  (`tests/test_vulkan_probe.py`) and EMULATOR-016 cover cancellation and lifecycle.
- Final cleanup: force-stop, then `pm uninstall --user 0`, which returned `Success`. `pm list packages
  --user 0` was empty, `dumpsys package` held 0 records for the package, and the UI dump file was absent
  from `/data/local/tmp`.

## Negative cases

Observed: the package was absent before install (the script refuses to touch a package that is already
present). Relaunching the app does not start GPU work. Stop is disabled while idle. In-app Stop can't
pre-empt a run of about 10 ms. Force-stop leaves the driver usable for the next process. The unscoped `pm`
query is denied for user 150. Thermal sysfs can't be read without root.

Not tested on the phone, on purpose:
- A fence-deadline timeout or GPU hang. That needs a workload that hangs, which a short baseline avoids;
  host fault injection covers the app logic.
- Interrupting in-flight GPU work, by either stop path. The run window is shorter than the input latency.
- A private-storage failure, and export through the document picker, which would use the owner's
  document provider.
- Shaders, presentation, sustained load and frame pacing.

## Not established

- GPU execution time, clocks and a GPU temperature.
- Behaviour on a GPU hang, or when a stop interrupts work that has already been submitted.
- Anything about Xclipse RADV (GPU-005) or the kernel sgpu interface, and anything under XNU.
