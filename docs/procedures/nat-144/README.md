# NAT-144: native run of loader-diag-xnu-scD-md1: a finger on the S24 screen opens iOS applications

Evidence kind: native-device. Outcome: **pass**, **U2-app-launched-after-press**. Decision 0058, one attempt, consumed
(artifacts/nat-144/native-attempt-loader-diag-xnu-scD-md1-used.json).

The owner was at the phone. They answered "Я у телефона, запускай" and were given the window: home screen at about 02:09:30
local, end at about 02:11:40. The reboot was at 21:05:13Z (02:05:13 local).

## What ran

The NAT-143 scD image:
- RECOVERY da5c03c2…1cda was written to sda18 with a full readback, followed by one reboot;
- kernel 6aa8b6eb…d100 (NAT-142's plus press/release log lines);
- `loader_return_after=270` with the fed watchdog;
- loader deadline 595 s;
- `rec_secs=270`.

Session: `python3 -I docs/procedures/nat-143/session_nat144.py --out artifacts/nat-144/run-001 --image loader-diag-xnu-scD-md1 --execute`, rc 0.

## Results

| Item | Result |
| --- | --- |
| Delivery | 2475720704 B in 64.25 s = 38.53 MB/s (sha256 4377e988…62f6) |
| USB | loader on bus 7 at +23.4 s, left at +615.4 s (deadline); Download Mode bus 8 dev 14 at +619.5 s |
| Watchdog | `e1s_wdt: fed every 10 s for 275 s`; `--- loader_return_after expired ---`; the kernel ran to 378.6 s |
| Start | S3-sense-on: READY after 1 read, scan echo after 3 reads, sense on at 109.49 s; backboardd opened the node at 119.57 s |
| UI timeline | TouchDetectionMode 0xff at 157.9 s, 0xfe at 215.6 s, 0x1 at ~226 s; automatic unlock (home screen) at 227.2 s |
| Presses | 20 presses / 19 releases, all after the home screen (251.6 s to 378.6 s) |
| Clock check | 55 launchd-spawn / kernel-memorystatus pid pairs, median wall − kernel = −0.007 s: ok |
| **App launches** | `com.apple.mobiletimer` (Clock), pid 90, at 286.66 s, **0.35 s after press 5** at raw x 2452 y 1928 (0.60, 0.47 of 4096). `com.apple.Preferences` (Settings), pid 98, at 310.46 s, **0.30 s after press 7** at x 2556 y 2920 (0.62, 0.71). Spotlight, which starts by itself, was excluded |
| Position check | On the NAT-142 home-screen panel thumbnail, Clock is at row 3 / column 3 (≈0.62, 0.47) and Settings at row 4 / column 3 (≈0.62, 0.71). Both presses land on the icon that opened. The raw STM coordinates map to iOS without a flip: x left→right, y top→bottom, 0..4095 per axis |
| Panel at the end | the iOS **Settings** app (P1, `artifacts/nat-144/analysis/panel-thumb.ppm`) |
| Swipes | presses 6 and 8–19 start at y 3876–4082 (the bottom edge) and end at y 1043–3253: swipes up. After Clock, press 6 was followed by the Settings tap on the home screen at 310 s. After Settings opened, 12 swipes followed, yet the final panel is still Settings, so the home gesture from Settings did not leave the app (not explained yet) |
| Frames | recording 66 frame changes; the kernel's frame statistics show half the frame intervals under 57 ms, 95% under 65 ms, longest 68 ms (when frames are produced) |
| Log | KL dump why=2, 532529 B (head 8 KiB + tail 512 KiB): the kernel ring and the home-screen console part were received |
| Restore | restore_stock rc 0 (PIT 8192, 100663296 B acknowledged, 0x67/0 and 0x67/1), check_android pass (boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, stock RECOVERY hash, user-data dirs), assess **pass** |

`analyze144.py` verdict line: W-ok, D2-refreshing, P2-both-rails-verified, T2-chip-answers, S3-sense-on, E1-coordinates (1568),
R1-open pid 16, U2-app-launched-after-press, W0, physical_input **ui-action**.

## What this establishes

On this S24, a finger tap on an iOS home-screen icon makes iOS open that application. The application then draws on the physical
panel. The path is:
1. STM controller (started by XNU);
2. bit-banged SPI9 poll in the XNU kernel;
3. /dev/redwood-touch;
4. backboardd's HID event system (HakiOS virtual digitizer);
5. SpringBoard hit-testing;
6. launchd spawns `UIKitApplication:com.apple.mobiletimer` / `com.apple.Preferences`.

The coordinate mapping is right without a flip.

## Owner observation (added 2026-11-14, after the run)

Asked what the screen did, the owner answered: «Открылись приложения, Свайп вверх работал» ("The apps opened, the swipe up worked").
This is the owner's account and is not re-derived from the log. It agrees with the Clock case (Settings was tapped on the home screen
after Clock, so the swipe up left Clock). The final recorded panel is Settings. The log alone does not say which swipe returned
to the home screen, or whether Settings was opened again after one.

## Not established

- From the log alone: which swipe made the home gesture. The owner reports that the swipe up worked (above).
- Interrupt-driven input (still 10 ms polling), latency, GPU acceleration, sustained FPS (frames reached the panel at about
  16–17 per second during continuous activity: `docs/procedures/nat-145/analyze146.py` on this run's text).

## Next

1. Frame rate: the software display path is about 16–17 frames per second on one Cortex-A520 (`cpus=1`). NAT-145 is the ten-CPU
   image, and NAT-146 is its native run, which needs an owner decision. After that come the framebuffer scaling cost and the GPU
   (GPU-017/018).
2. IRQ on gpa1-2 instead of polling.
