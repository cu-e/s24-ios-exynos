# NAT-181: scT on the phone, column-run copy in the framebuffer scaling (native, decision 0073)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scT-md1 (NAT-180), one run on 2026-11-14. Afterwards stock RECOVERY was
restored with a full hash check (`restore-001/report.json`, nat-013 assess: Android booted, RECOVERY readback matches) and Android was
verified.

## Result: K0, no gain worth having

| | NAT-177 (scS, per-pixel loop) | NAT-181 (scT, memcpy runs) |
|---|---|---|
| driver time per frame, median of steady 5 s windows | 8.914 ms (34 windows) | **8.736 ms** (21 windows; 8.59–8.99) |
| copy per swipe frame (`tl: v`) | 8.77 ms | **8.59 ms** |
| display snapshot (dpp177) | R-ok | R-ok, identical except FRAME_COUNT |
| last frame (panel thumbnail) | home page 1 | the same home page 1, icons intact |
| cpu0 clock | C2 1958 MHz | C2 |
| touch / display | P1 / W-ok D2 | P1 / W-ok D2 |

The timed return was reached (`loader_return_after expired`), and the swipe thread ended after 54 swipes.

The run copy saves 0.18 ms per frame (2 %), against NAT-180's hope of several milliseconds. The picture is unchanged, which confirms the
host equivalence test on the phone.

### What this shows about the copy

| run | cpu0 clock | driver time |
|---|---|---|
| NAT-170 | 960 MHz | 17.89 ms |
| NAT-173 | 1958 MHz | 8.93 ms |

The ratio is 2.00, exactly the clock ratio, while cutting the instruction count did nearly nothing:
- **DRAM latency** does not limit it: a latency-bound copy would not halve with the core clock.
- **Instruction count** does not limit it either: one `memcpy` per run in place of a load and store per pixel saved 0.18 ms.
- **What remains** is a cost in the core's own clock domain. The candidates are the store path into the write-combined panel mapping
  (about 10 MB per frame) and line fills of the cached source (about 11 MB). The two are not separated yet.

This is the next measurement: NAT-182 is a bandwidth reference on the same A520 core.

### The swipes: F-low, but not caused by the change

The swipe analyser gives F-low (37.66 ms median, 4.6 fps per swipe). The swipes animated at first: the 229 s window had 82 frames, half
of the intervals under 18 ms. From about 236 s on, SpringBoard answered almost no swipe, with 1 swap per swipe and 1–5 frames per
second. The input was delivered exactly as in NAT-177: 19 DOWN, 237 MOVE and 20 UP samples of finger 9 in the tail, with no real
finger.

The driver time is unchanged and the picture is right, so the change is not a plausible cause. The UI state SpringBoard went into is
not observable without a picture during the run. The swipe frame rate is therefore not comparable with NAT-177's; this run only
measures the driver time.

## Not established

- What SpringBoard was doing after about 236 s.
- Whether the copy's limit is the write-combined stores, the source reads, or the cluster clock.

## Files

- `analysis/`: kernel text, fbcopy181, swipe175, frames159, dpp177, cpuclk173, touch170, load166, pixels, panel-thumb and verdict
  (in `artifacts/nat-181/`, kept local).
- Decision: `docs/decisions/0073-nat181-loader-diag-xnu-scT-md1-single-run-2026-11-14.md`.
