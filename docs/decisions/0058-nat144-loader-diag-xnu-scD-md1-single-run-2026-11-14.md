# Decision 0058: one NAT-144 run of loader-diag-xnu-scD-md1 (home screen up ~2 minutes, touch input)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052.

## Owner consent

Decision 0052 (2026-11-13) is the owner's standing permission. It covers prepared single native experiments with touch, display,
GPIO, interrupts and watchdog. It also covers temporary peripheral power through PMIC/ACPM on confirmed stock parameters, naming
LDO9/LDO18. The owner directed the work to touch and GPU on 2026-11-14: "2 задача тач и гпу перейди к ней". The rails are unchanged
from decisions 0055 to 0057: LDO18 0x3d := 0xd8 (1.8 V) and LDO9 0x34 := 0xf0 (3.0 V), read back exactly on this phone in NAT-124,
NAT-140 and NAT-142.

## New verifiable reason

NAT-142 passed for controller → kernel → backboardd. The owner saw no iOS reaction, at about 70% confidence. Its log shows the UI took
touches only from 238 s, and the home screen was up only from ~243 s to the timed return at ~252 s (docs/procedures/nat-142/README.md,
"After the run"). NAT-142 therefore could not test a UI action. scD keeps the same system up 120 s longer and logs every press with
its time, so the question "does a touch make iOS do something" becomes testable.

## Image

Image loader-diag-xnu-scD-md1, built by NAT-143:
- RECOVERY artifacts/nat-143/package-001/loader-diag-xnu-scD-md1/recovery.img,
  SHA-256 da5c03c2c41af74332a054062de2a7e7de3e3bc987bc93e55ea2aafd68dc1cda (100663296 bytes).
- Image.payload SHA-256 55ad4eea5cf069c6fa4d826825b4259862e6e28761a621dbcc5a8ae69f39d963 (26199248 bytes at offset 2048).
- Loader Image 02ede202c61547565df9fcec25ee35fa8f84004e8f89df1fa74668a0ba879354. The engine is NAT-130's. Only the deadline
  define differs from scC's loader.
- Kernel 6aa8b6eb27009e16d0e7a618c5e4becca6f36561ac5b632912bdda13078fd100. Only e1s_touch.o differs from NAT-142's kernel, and it
  adds press/release log lines.
- Cmdline (246 bytes) is scC's except `nat_attempt=NAT143-scD`, `loader_return_after=270` and `rec_secs=270`.
- Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
  (docs/procedures/nat-143/session_nat144.py, 17b86433…1010).
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
- Root artifacts/nat-083/system-padded.apfs, SHA-256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6.

## Changes against scC (NAT-142)

- The kernel's timed return comes after 270 s instead of 150 s. The kernel feeds the S5E9945 watchdog every 10 s until then plus 5 s.
  If the feed is not proven, the kernel itself cuts the window to 63 s (NAT-115 rule).
- The loader deadline is 595 s instead of 475 s: receive cap 240 + 270 + 60 + 25 ≤ 595 ≤ 600. The loader feeds the watchdog until
  the deadline (NAT-074 rule), then enters Download Mode as before.
- The screen recording stays on for 270 s.
- Every STM press/release is printed (a log line only; nothing different is sent to the controller).

The STM commands, rails, GPIO settings and the root are NAT-142's.

## Risk

The electrical and controller actions are exactly NAT-142's. They are volatile, and Android re-powers and re-probes the touch
controller after the restore. The difference is time: iOS and the touch controller run 120 s longer on the same rails and settings,
with the watchdog fed, as they did for 150 s in NAT-142. No partition other than RECOVERY is written. iOS runs from RAM, and
NAT-084..142 showed no write path to UFS (`e1sufs=0`, ufs_write absent).

## Time limit, stop mechanism, restore

- delivery cap 225 s;
- loader receive cap 240 s;
- kernel timed return 270 s with watchdog feed (fail-safe 63 s);
- loader deadline 595 s, then Download Mode (expected at about +620 s after the reboot);
- watcher and collector 720 s.

The touch event thread ends with the kernel's timed return.

Restore:
1. Run nat-012 restore_stock.py with the venv python.
2. Run check_android.py, then nat-013 assess.
3. Require boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, the stock RECOVERY hash and user-data directories.
4. Run `task done`/`update`, then close the permission.

One attempt only, with no retry without a new verifiable reason.

## Physical action asked of the owner

Timing is counted from the reboot, the moment the USB connection to Android drops:
- The home screen with app icons is expected at about +4 min 15 s.
- The run ends at about +6 min 20 s.

In that window:
1. Tap one app icon (for example Settings, Clock or Notes).
2. Wait about 10 s. The screen updates slowly, about 2 frames per second.
3. Swipe up from the bottom edge to go home.
4. Tap another icon.

Before +4 min 15 s, a tap may wake the screen. Afterwards, tell what the screen did.

## Interpretation registered before the run

`docs/procedures/nat-143/analyze144.py` reports every analyze142 verdict, plus ui, wake, clock_check, presses and app launches.

What follows from each outcome:
- **U2** (an app other than Spotlight launched within 20 s after a home-screen press, clocks verified) means a touch made iOS launch
  an application.
- **U1** means presses reached the home screen without an app launch. The reason is then open: coordinates, hit-testing or delivery.
- **U0** means no press came on the home screen.
- The owner's report is recorded as an observation, separate from the log verdict.
