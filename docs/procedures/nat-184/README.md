# NAT-184: scU on the phone, scaling from a per-layer run table (native, decision 0074)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scU-md1 (NAT-183), one run on 2026-11-14. Afterwards stock RECOVERY was
restored with a full hash check (`restore-001/report.json`, nat-013 assess: Android booted, RECOVERY readback matches) and Android was
verified.

## Result: K2, the framebuffer driver is 4× faster

| | NAT-177 (per-pixel) | NAT-181 (NAT-180 runs) | **NAT-184 (run table)** |
|---|---|---|---|
| driver time per frame, steady median | 8.914 ms | 8.736 ms | **2.163 ms** (1.98–2.34, 27 windows) |
| swipe-frame copy (`tl: v`) | 8.77 ms | 8.59 ms | **2.14 ms** |
| display snapshot (dpp177) | R-ok | R-ok, same | R-ok, same (only FRAME_COUNT differs) |
| last frame | home page 1 | home page 1 | home page 2 with widgets, drawn intact |

Also: cpu0 C2, touch P1, display W-ok / D2, timed return reached, 54 swipes done.

NAT-182's Android prediction (2.32 ms for the copy alone) held on the phone. That makes 6.75 ms of the single core free in every frame.

## But the frame rate did not follow

From the driver's own 5 s histograms over the whole swipe phase (218–378 s):

| run | intervals | < 18 ms (60 Hz) | 26–35 ms (30 Hz) | ≥ 35 ms | frames / s over the phase |
|---|---|---|---|---|---|
| NAT-177 | 1296 | **57 %** | 32 % | 9 % | 11.4 |
| NAT-181 | 393 | 41 % | 41 % | 16 % | 4.4 |
| NAT-184 | 687 | **56 %** | 29 % | 11 % | 7.2 |

**The 60-Hz share did not rise when the driver became 6.75 ms faster.** When SpringBoard animates, about half its frames still miss
the 16.7 ms beat and land on the 33 ms one. Frames that are ready now wait 9–11 ms for the beat, against about 6 ms before, and the
driver still counts 6–42 swaps per window that came "a refresh late themselves", which is userland's lateness.

SpringBoard again stopped answering the synthetic swipes for parts of the run (the tail, 328–384 s: 16 swipes, most with 0–3 swaps),
as in NAT-181. So the frames per second over the phase depend on that UI state and are not comparable between runs. The 60-Hz share of
the intervals that did happen is comparable.

The limit is now userland: the renderer itself takes more than 16.7 ms for about half the frames, or it is paced late. What uses the
core is not measured in any current image. NAT-166's `cpuload` lines reported all ten cores 100 % busy, including nine that never
started, so `ml_cpu_idle_time` is not trustworthy here. Next: NAT-185/186, a per-process CPU-time sampler.

## Not established

- What fills the CPU during swipes, and whether the core is saturated.
- Why SpringBoard stops answering the synthetic swipes partway through.
