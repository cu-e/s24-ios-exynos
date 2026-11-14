# NAT-175: frame capacity under synthetic swipes at 1958 MHz (native, decision 0071)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scR-md1 (NAT-174), RECOVERY `dcf3eab8…`, one run on 2026-11-14.
The phone was restored with stock RECOVERY (full hash checked) and Android verified.

## Result: F30

The delivered log tail runs from 332.8 to 379.2 s of uptime and holds 14 of the 54 swipes. It contains 204 finger-9 samples and
no real-finger samples. SpringBoard did animate on the synthetic events: per swipe, ~10 swaps in 1 s, against ~3/s idle.

| | swipe | idle (same tail) |
|---|---|---|
| swap interval median | 20.92 ms | 32.41 ms |
| p10 / p90 | 11.98 / 61.44 ms | 12.11 / 271 ms |
| gaps ≤ 18 ms | 39.9% | — |
| fps per swipe, median / max | 25.2 / 36.4 | — |

Down to first swap: median 80 ms (p90 211 ms). The page animation starts after the gesture is recognised.

cpu0 reached C2 again (960000 → 1958400 kHz, add rate ×2.04). Other analysers:
- touch: P1 (11.5 s per 1000 polls; ID reads 3/3 ok);
- driver: 8.91 ms per frame;
- display: W-ok / D2-refreshing / S1 / P2;
- `cpuload` is not on this command line, so there are no load lines;
- the run ended through the timed return (`loader_return_after expired`).

## Where a swipe frame's time goes (`analysis/split175.json`)

The iOS display is 1125×2436 and the panel 1080×2340, so every frame is scaled by the CPU, which is the same single core that
renders:
- **Scaling copy (shown → done):** 8.77 ms, the same in every frame (p10 8.75, p90 8.86).
- **Beat wait (ready → shown):** median 3.35 ms, up to 17.3 ms (`fb_beat=1`).
- **Overlap:** 26 of 139 swipe swaps arrived before the previous frame's copy had finished.
- **Userland's own part (next swap minus previous done):** median 5.2 ms. It is negative when the copy still runs, and p90 is
  44.9 ms when userland stalls.

**I:** the frame rate under animation is limited by the CPU share of the scaling copy plus userland rendering on one core, not by
the panel. Removing the 8.8-ms copy (display-hardware scaling through DPP1, NAT-162) and the beat wait is the largest single-core
lever. SMP (NAT-154, stopped) and the GPU are the others.

## Not established

- The frame rate the panel shows and touch latency at the glass: these are kernel counts, not a camera.
- The swipes before 332.8 s, which fall outside the fixed 532529-B log tail.
- What bounds the userland part on one A520 core.
- Whether DPP1 scaling works. NAT-162 lists the read-only snapshot that has to come first.
