# NAT-142: native run of loader-diag-xnu-scC-md1: a finger on the S24 screen produces touch events in XNU and in iOS's event server

Evidence kind: native-device. Outcome: **pass**. Decision 0057, one attempt, consumed
(artifacts/nat-142/native-attempt-loader-diag-xnu-scC-md1-used.json).

The owner was at the phone, answered "Я у телефона, запускай", and was told the touch window (01:30:35–01:33:20 local, i.e. +1:45 to
+4:30 after the reboot at 20:28:51Z).

## What ran

The NAT-141 scC image:
- RECOVERY 15b2d177…b617 written to sda18, with a full readback, then one reboot;
- kernel 9213cff4…5914, which adds Samsung's STM screen-on start sequence and a polled 0x87 event thread that posts to
  /dev/hakios-touch.

Session: `python3 -I docs/procedures/nat-141/session_nat142.py --out artifacts/nat-142/run-001 --image loader-diag-xnu-scC-md1 --execute`, rc 0.

## Results

| Item | Result |
| --- | --- |
| Delivery | 2475720704 B in 66.433 s = 37.266 MB/s |
| USB | loader on bus 7 at +20.4 s, left at +492.5 s (deadline); Download Mode bus 8 dev 12 at +496.6 s |
| Power | P2-both-rails-verified (log kept) |
| ID | T2-chip-answers, as NAT-140 |
| Start | **S3-sense-on**. `ready after 1 read(s)` with READY event `49 00 10 …`; scan `echo of a0 after 3 read(s)`; sense on at 107.10 s. Five status events follow (`43 15 01`, `43 01 10`, `43 11 01`, `43 05 11`, `43 15 01`) |
| Events | **E1-coordinates**: 7380 coordinate events, 91 presses / 90 releases over 108.2 s to 243.9 s (summaries every 1000 polls). First: `coord 1: finger 0 action 1 x 2695 y 1203` at 108.233 s, followed by smooth move tracks (x 2695→2732, y 1203→1210 …) |
| Kernel posting | `redwood-touch: sample N type 1/2/3 finger 0 at X Y` (DOWN/MOVE/UP, 0..65535 scale) for each posted event |
| IRQ line | gpa1-2 was low in 3847 of 10000 polls (pull NONE). Its level follows the event activity, which is what an IRQ step needs |
| iOS reader | R1: `redwood-touch: opened by pid 16` (backboardd) at 119.9 s |
| iOS event server | backboardd's HakiOS input layer logged `hakios: input: touch screen service 0x115d3f080, buttons 0x115d3ff40` and `hakios: input: sample type 2 finger 0 at 20852 34455` (4 sample lines kept in the log; NAT-140, without touches, has none) |
| Window / display / iOS | W-ok / D2-refreshing / F1; panel P1 |
| Restore | restore_stock rc 0 (PIT 8192, 100663296 B acknowledged, 0x67/0 and 0x67/1), check_android pass (boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, stock RECOVERY hash, user-data dirs), assess **pass** |

## What this establishes

- Touch input works from the panel to iOS's HID event server on this S24, with the controller started by the XNU kernel itself:
  - The STM accepts Samsung's screen-on sequence from XNU (reset/READY, clear, scan echo, sense on).
  - A finger produces coordinate events, read by the XNU kernel over bit-banged SPI9.
  - The kernel posts them to /dev/redwood-touch / hakios-touch.
  - backboardd's input layer receives them as touch-screen samples.
- No IRQ was needed. The gpa1-2 level is usable for the next step.

## Not established

- **That SpringBoard acted on a touch.** Recorded frames change in both NAT-140 (no touch) and NAT-142, so a frame change is not
  attributable to input. This needs either a touch-correlated UI change or the owner's observation.
- The coordinate orientation and scale in iOS. Raw 12-bit x 2695 / y 1203 against Samsung's `sec,max_coords = <4096 4096>`; whether
  iOS maps them to the right on-screen point is unverified.
- Interrupt-driven input, latency, acceleration and FPS.

## After the run: owner observation and log timeline (added 2026-11-14)

The owner was asked what the screen did while they touched it. Their answer: "я тыкал но мне кажется ios была без реакции, я уверен на
процентов 70 не на 100 потому что там кадров 2 в секунду и мб ни ничего не произашло но я тыкал долго но ничего не помеялось".
They saw no reaction, at about 70% confidence, at about 2 frames per second.

A re-read of `artifacts/nat-142/analysis/kernel-text.txt` explains this without a fault in the input path. The UI accepted touches
only in the last ~14 s of the kernel's 150 s window:

| Kernel time (os_log clock ≈ kernel clock) | Event |
| --- | --- |
| 107.1 s | STM sense on; touch coordinates from 108.2 s |
| 119.9 s | backboardd opens /dev/redwood-touch |
| ~123 s | HakiOS input layer has its touch screen service; first samples dispatched |
| 157.9 s | first window-server frame (software renderer); recording starts |
| 158.6 s | backboardd sets `TouchDetectionMode` 0xff (no touches) |
| 228.7 s | mode 0xfe (display off, tap to wake: the input layer turns a touch-down into a lock-button press) |
| 238.2 s | mode 0x1 (touches reported), lock screen |
| 242.0 s | `hakios: unlock: asked, answer 1` — the donor's automatic 10 s unlock (inject_sb.c), not a swipe; mode 0 |
| 243.7–252.3 s | recorded frames 6–27: the home screen (the final panel thumbnail is the home screen) |
| ~252 s | timed return (`loader_return_after=150`) |

Most presses (84 of 91 by 229.7 s) came before the UI was taking touches. The 0xfe → 0x1 wake at 238 s may have been a touch, but the
input layer does not log its wake press, so this is not established. The panel ends on the iOS home screen.

## Next

1. Correlate a touch with a UI change. This needs a window in which the home screen is up for minutes, not seconds: a longer
   `loader_return_after` with the fed watchdog, every press/release logged with its time, and the owner tapping app icons. The test
   is a launchd `UIKitApplication:` spawn other than the automatic Spotlight one (NAT-143/144).
2. Attach the IRQ on gpa1-2 (EINT, level-low, as Android) instead of 10 ms polling.
3. Check orientation/scale against the panel's 1080×2340.
