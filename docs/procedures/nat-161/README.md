# NAT-161: scK on the phone, 2× UI scale (native-device)

- **Decision:** 0065 under 0061, one attempt, consumed.
- **Image:** loader-diag-xnu-scK-md1 (NAT-160).
- **Outcome:** the run passed and the criteria were evaluated. The lever's grade is **G0**. Stock RECOVERY was restored with a full
  hash, and Android was verified.
- **Touch:** none.

## Frames (`frames159.py`, the same rule as NAT-153/159)

| | NAT-153 scH | NAT-159 scJ (`fb_filter=0`) | NAT-161 scK (+ `fbscale=2`) |
| --- | --- | --- | --- |
| Surface | 1125×2436 | 1125×2436 | **750×1624** |
| Steady windows | 8 | 7 | 10 |
| Driver time per frame (median) | 70.68 ms | 26.00 ms | 25.75 ms |
| Frames/s (median, range) | 6.99 (6.8–7.3) | 9.26 (7.2–10.4) | 9.65 (3.6–10.2) |
| Outside the driver per frame | 72.4 ms | 82.0 ms | 77.9 ms |

- iOS came up at scale 2: the driver reports `display 750x1624` and every swap is a 750×1624 surface.
- SpringBoard stayed up. The only exits are mediaserverd crashing on SIGSEGV, as in NAT-159.
- Rendering 2.25 times fewer pixels changed the frame rate by 4%.

## Why: the single core is half idle (`cpu161.py`)

Between the two `ps` snapshots the heartbeat prints (328–363 s, 34.9 s), CPU time was:

| Where | CPU time |
| --- | --- |
| Processes | 10.68 s (SpringBoard 5.65 s, backboardd 2.27 s, runningboardd 0.77 s, launchd 0.74 s, …) |
| Framebuffer driver | 6.78 s, from its 5 s windows weighted by overlap |
| **Total** | **50% of the span** |

The idle home screen's frame rate is not CPU-bound. In NAT-153/159 the first two snapshots fall during boot, so they cannot be
compared. The driver source says CoreAnimation "does not go by the refresh notifications of this driver … but by a clock of its own".
The ~10/s cap seen in every run (at most 51–52 frames per 5 s) is therefore most likely the rate at which the home screen's content
changes, or CoreAnimation's own pacing. It is not the hardware's capacity.

NAT-144 is a hint of this: with touch it reached 21.72/s with the bilinear driver.

## Consequences for the 60 fps line

- Frame rate measured on the idle home screen stops being a useful benchmark once the driver is cheap. A capacity measurement needs
  continuous content:
  - owner scrolling (as in NAT-144);
  - or a self-running animation;
  - with per-swap timing (`touch_lat=1`: `tl: s ID` at every SwapEnd and `tl: v ID ready/shown/done` for every frame), which shows
    whether frames wait on CoreAnimation, the swap queue or the beat.
- `fb_filter=0` stays: it cut the driver's time by 63% (NAT-159). `fbscale=2` makes the picture less sharp for no measured gain on
  this content. It is not kept by default until a capacity measurement says otherwise.
- **Not established:**
  - what paces the idle frames;
  - the frame rate under interaction at scale 2;
  - panel refresh rate, scan-out and input latency.
