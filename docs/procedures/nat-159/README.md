# NAT-159: scJ on the phone, nearest-neighbour framebuffer scaling (native-device)

- **Decision:** 0064 under 0061, one attempt, consumed (`artifacts/nat-159/native-attempt-loader-diag-xnu-scJ-md1-used.json`).
- **Image:** loader-diag-xnu-scJ-md1 (NAT-158), RECOVERY 77830038…003a, payload cd9823e1…9ce5.
- **Outcome:** pass. Stock RECOVERY was restored with a full hash match, and Android was verified (boot_completed, user-data
  directories present).
- **Touch:** none in this run, as in NAT-153 (0 finger events in both).

## Result: F2, the driver's time per frame fell by 63%

`frames159.py` applies the same rule to both runs: windows of 4500–5600 ms with at least 10 frames, after the recording if the run
recorded. The figures are kernel counts from MiniIOMobileFramebuffer's 5 s statistics lines, not a camera.

| | NAT-153 scH (bilinear) | NAT-159 scJ (`fb_filter=0`) |
| --- | --- | --- |
| Steady windows | 8 (346–382 s) | 7 (353–383 s) |
| Driver time per frame, median (range) | 70.68 ms (70.66–74.25) | **26.00 ms** (25.99–26.18) |
| Frames/s, median (range) | 6.99 (6.76–7.30) | **9.26** (7.16–10.35) |
| Frame interval, median | 143.1 ms | 108.0 ms |
| Interval minus driver ("other") | 72.4 ms | 82.0 ms |
| GPU wait / late swaps | 0 / 4 | 0 / 21 |

The grade is **F2**, because 26.0 ms is at most half of 70.68 ms. Scaling nearest-neighbour costs 2.7 times less on the phone. The
host ratio for home-screen-like content was 5.5 times, so the phone's ratio is smaller than the host's.

## What this establishes and what it does not

- **The driver is no longer the larger part of a frame.** About 82 ms of the 108 ms interval is outside it: rendering in software
  and everything else on the single running core.
  - That share rose from 72.4 ms. The content differs between the two runs: windows of 36–52 frames, and the home screen animates by
    itself.
  - `frames159` cannot separate rendering from other work, so the cause of the rise is not established.
- **The next frame-rate levers are on the "other" side:**
  - `fbscale=2` (NAT-156 lever 4: iOS renders 2.25 times fewer pixels);
  - more cores (SMP is paused: NAT-154 awaits an owner decision);
  - the GPU (GPU-017/018).
- **Also observed:** display D2-refreshing; the panel has pixels (P1, 1136377 non-zero); SMP unchanged (C0-one, cpu 1–9 reach E6
  at EL2 and stay off).
- **Not measured:** panel refresh rate, scan-out timing and input latency.

## Commands

See `evidence.json`:
1. preflight `ready-read-only`;
2. run (delivery 35.51 MB/s), Download Mode at the deadline;
3. restore with the venv `restore_stock.py`, rc 0;
4. `check_android` pass, nat-013 assess pass.
