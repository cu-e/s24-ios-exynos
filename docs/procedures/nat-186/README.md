# NAT-186: what fills the only core during the swipes (native, decision 0075)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scV-md1 (NAT-185), one run on 2026-11-14. Afterwards stock RECOVERY was
restored with a full hash check (`restore-001/report.json`, nat-013 assess: Android booted, RECOVERY readback matches) and Android was
verified.

## Result: U-sat, and the consumer is backboardd

The sampler ran from 124 s to 380 s and printed 35 spans with no process lost (`analysis/top186.json`).

| over the swipe windows (220–375 s) | share of cpu0 |
|---|---|
| **busy, median** | **0.996**: the core is full |
| **backboardd** (pid 16, the CoreAnimation render server) | **0.76** |
| SpringBoard | 0.077 |
| kernel_task | 0.039 |
| everything else (remindd, mediaserverd restarts, launchd, …) | < 0.01 each |

cpu0's idle counter reads 0 in every span. It agrees with span − busy here only because the core really is full. Whether it counts idle
time at all on this port is still open.

### backboardd's cost per frame, from the same spans and the driver's 5 s frame counts

| phase | backboardd CPU per 5 s | frames per 5 s | backboardd CPU per frame |
|---|---|---|---|
| before the swipes (205–215 s) | 0.65–1.0 s | 49–51 | 13–20 ms |
| swipes between home pages (e.g. 300 s) | 3.25 s | 109 | about 30 ms |
| swipes in the Today view (315–375 s) | 4.3–4.5 s (88 %) | 18–28 | **about 190 ms** |

The last panel frame (`analysis/panel-thumb.ppm`) is the widget-only Today view, left of home page 1. The synthetic swipes alternate
left and right, so a run can drift into that view. There, backboardd needs about 190 ms of the A520 for every frame of the widget
materials.

This explains what NAT-181 and NAT-184 described as "SpringBoard stops answering". It was not ignoring the swipes. The render server
filled the core with very slow frames.

## Other results

- **K2:** driver 2.162 ms, as in NAT-184. The copy in swipe frames is 2.15 ms.
- **Swipes: F60 by the registered rule, with a caveat.** The median swap interval inside the swipe windows is 16.66 ms and 63 % are at
  60 Hz, but the per-swipe rate ranges from 3 to 87 fps (median 22.5). The verdict reflects the cheap swipe frames, not a sustained 60.
- **Unchanged:** dpp177 R-ok, cpuclk173 C2, touch170 P1, display W-ok / D2, timed return reached, 54 swipes done.

## What follows

**Rendering is CPU-bound in backboardd on one A520 at 1958 MHz.** Even cheap frames cost 13–30 ms, so a sustained 60 fps in software
needs one of three things:
1. **less render work per frame:** fewer blur and material effects, which is what iOS's Reduce Transparency and Reduce Motion settings
   remove. This is the lever available now: a change to the delivered userland root, no hardware access;
2. **more and faster cores:** the SMP line, NAT-154, is stopped by the classifier and awaits the owner;
3. **GPU composition:** the Xclipse start needs SMC/HVC and PMU steps, which await the owner's decision.

## Not established

- Which effects make backboardd's frames expensive. No userland profiler is available, and the sampler counts whole processes.
- Whether cpu0's idle counter works when the core is not saturated.
