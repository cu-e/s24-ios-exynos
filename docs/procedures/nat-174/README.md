# NAT-174: scR, synthetic home-screen swipes for a frame-capacity measurement (host)

## Why

NAT-173 raised cpu0 (Cortex-A520) from 960 to 1958.4 MHz with one stock ACPM FREQ_REQ and halved the framebuffer driver time
(17.9 to 8.9 ms per frame). The frame rate stayed at ~9.6 fps because on the idle home screen userland hands over a frame every
~105 ms (NAT-164: content cadence, not capacity). To find out what the system can render at the new clock, something has to be
animating. Nobody presses the screen during a native run, so the kernel generates the gesture itself.

## What changed (one object, one command-line token)

- `bsd/e1s_touch.o` is built from `e1s_touch_combined.patch` = NAT-169's patch (GPP9 DAT shadow, poll gated on gpa1-2) plus
  `e1s_uptime_us()` and `e1s_swipe_thread()`. The thread is started at the end of `e1s_touch_init()` after the event thread and is
  switched off by boot-arg `e1stouch_swipe=0`. From 215 s to 375 s of uptime it posts one swipe every 3 s through
  `redwood_touch_post`, which is the path real samples take. Each swipe is finger 9 (a real finger starts at 0): a DOWN at 0.8 (or
  0.2) of the width at mid-height, 12 MOVEs 16 ms apart, then an UP at 0.2 (or 0.8). The direction alternates, so the home screen
  pages left and right. The window end was moved from 360 s (task title) to 375 s before the build. The delivered log is a fixed
  532529-byte tail (NAT-164 and NAT-173 had identical sizes; NAT-164's touch_lat lines covered only 312.8–384.3 s) and the log
  ends at ~383 s, so swipes up to 375 s land in the part that is kept.
- Command line = scQ's with `cpuload=1000` replaced by `touch_lat=1`, which logs `tl: s/v/p` lines (NAT-163). It stays 254 B.
  The cpuload line is dropped because cpu0's load was already measured (NAT-166, 100%) and the 255-B limit leaves room for one
  token only. `e1scpuclk` keeps its default, so the run also repeats NAT-173's FREQ_REQ (verdict C2 expected again).
- Kernel `artifacts/nat-174/kernel-001`: no-storage sha256 `fc5c773e0ae7ba87e132eb2cd54a4f4e536065e1684dfc99f798764d635bcfca`,
  0 undefined. `build.py` checks that this is NAT-172's record with only `bsd/e1s_touch.o` changed, and that by function the patch
  differs from NAT-169's only in file-scope lines, the two new functions and the three thread-start lines in `e1s_touch_init()`.

## Host checks

- `python3 -B docs/procedures/nat-174/test_nat174.py`: 6 OK.
  - The NAT-169 event-thread peer is unchanged under the new patch.
  - Swipe timing and coordinates run on a simulated clock (`host/clock174.c`): 54 swipes from 215 s, 3 s apart, finger 9,
    DOWN + 12 MOVE + UP, x 52428 → 13107 in 16-ms steps, alternating; `e1stouch_swipe=0` posts nothing.
  - The analyser verdicts come from synthetic logs.
- Build `artifacts/nat-174/build-001`: loader sites rc 0 / ok / bad 0, relocscan clean, cmdline 254 B.
- Package `artifacts/nat-174/package-001`, image `loader-diag-xnu-scR-md1`: RECOVERY sha256
  `dcf3eab8059b884215c9992607a29b9c5ccf5e566d623c627e1189cd5b2e84a9`, payload
  `436fa4ad6dd45b7c9712cae28035a0223fbe523b34cbe55c1c6c039ff48d1308` (26206624 B).
- Session `session_nat175.py` is derived by counted replacement from NAT-173's (`derive175.py --check`). Only the image, its
  hashes, the package, the decision glob `*-nat175-*`, the marker `artifacts/nat-175/` and the preconditions (+NAT-173, NAT-174)
  change.

## Registered verdicts for NAT-175 (`swipe175.py`)

A swipe window is [DOWN, DOWN + 1 s). Idle swaps are those at least 1 s away from any touch sample. Gaps over 200 ms inside a
window are pauses.

| verdict | condition | meaning |
|---|---|---|
| S-none | no finger-9 DOWN in the delivered tail | inconclusive: the thread did not run or the tail missed it |
| S-same | swipe swap-interval median within 10% of idle | inconclusive: no animation proven (gesture ignored?) |
| F60 | swipe median ≤ 18 ms | 60 fps capacity under animation at 1958 MHz |
| F30 | ≤ 36 ms | 30–60 fps |
| F-low | slower | rendering, not cadence, limits the frame rate |

These are kernel counts, not a camera. A swap is a frame that userland handed over. "Done" means the pixels are in panel memory,
not that the panel lit them. Panel refresh and touch latency are reported separately (`down_to_first_swap`, `swipe_copy`). If a
real finger is seen (finger ≠ 9), the run is marked as touched. NAT-175 also runs `cpuclk173.py` (C2 again expected),
`touch170.py`, `frames159.py`, `load166.py` (no `tl: u` lines expected) and the display analysers.

## Not established here

This is host evidence. It does not show that SpringBoard pages on these synthetic events, or what frame rate the phone reaches.
NAT-144 showed that real taps through the same path open apps, which makes it likely that swipes work too.
