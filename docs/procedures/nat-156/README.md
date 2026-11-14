# NAT-156: where the 70.7 ms per frame of MiniIOMobileFramebuffer goes (source review + host timing)

- **Evidence kind:** source review, with host-only timing.
- **Device:** none used.
- **Driver source:** `references/s24-port` c8860decc62c6d6180e609036d027a2997972420,
  `xnu/hackios/files/iokit/Kernel/MiniIOMobileFramebuffer.cpp`.

## What NAT-153 measured

From 341 s on, 34–37 frames per 5 s window (6–7/s), each taking **70.7 ms in the driver**, with 0 us waiting for the GPU and 0 for
the refresh. This was on the single running core, cpu0. Every swap had one layer: surface 1125×2436 BGRA, full screen (`swap N
layer 0 … from 0,0 1125x2436 to 0,0 1125x2436`). The command line set `rec_secs=270 rec_mb=64` and no `fb_*` option, so the
defaults applied: `fb_filter=1`, `fb_threads=3`, `fbscale` 3.

## What a frame costs in the driver (source)

`fStatDrawing` is the time from a swap's start to the end of `record()`. It covers every layer's `drawLayer()` and the recorder:

1. **Scaling (`drawRows`)**, 2,527,200 panel pixels (1080×2340) from the 1125×2436 surface.
   - **`fb_filter=1` (default, bilinear):** for each panel row, one blended source row (1125 pixels: two loads, `blend()` unless
     equal), then per panel pixel two loads, a compare and a `blend()` unless equal.
   - **`fb_filter=0` (nearest):** one load and one store per panel pixel.
   - **The unscaled path** applies only when the surface is exactly the panel's size: one `memcpy` per row.
2. **`record()`** (`rec_secs`): one pixel of every 3 in each direction, 375×812 = 304,500 pixels, 3 bytes each.
3. **`fb_threads=3`:** the rows are shared between the presenter and two helper threads. With one running core, the helpers
   time-share that core, so they add switching and gain nothing.

The memory is not the cause. I checked two candidates:
- **The panel:** `initialize_screen` maps it with flags 6 = `VM_WIMG_WCOMB`, write-combining (the immediate before
  `bl _ml_io_map_unmappable` in the scH kernel, the `E1S` branch of `video_console.c`), not 7 = device memory.
- **The surfaces:** they are `IOBufferMemoryDescriptor` kernel buffers with the default (cacheable) mode.

## Host timing of the same loops (`bench_scale.c`, host only)

The loops are copied without change of arithmetic. They are timed on the host (AMD Ryzen AI 5 PRO 340, gcc 15.3 -O2, best of 15,
`artifacts/nat-156/bench-host.txt`). **These are not phone numbers.** They rank the paths by the work per frame.

| Input | Bilinear (`fb_filter=1`) | Nearest (`fb_filter=0`) | Unscaled `memcpy` |
| --- | --- | --- | --- |
| flat colour | 4.34 ms | 1.47 ms | 0.39 ms |
| home-screen-like (synthetic: gradient + 24 noise icons, ≈20%) | 7.89 ms | 1.44 ms | 0.38 ms |
| noise (worst case for bilinear) | 16.18 ms | 1.47 ms | 0.37 ms |

Bilinear costs 3–11 times nearest, depending on content, and nearest costs about 4 times a `memcpy`. The phone's 70.7 ms is 4.5–16
times the host's bilinear time. That fits an in-order small core at the clock S-Boot left, but this host test does not establish
that.

## The single-core budget (inference, not a measurement)

7.1 frames/s is 141 ms per frame. 70.7 ms of that is in the driver, so the remaining ~70 ms is rendering and everything else on the
same core (CoreAnimation in software, SpringBoard, daemons). Taking the host ratios to the phone, `fb_filter=0` would cut the
driver's share to roughly 6–24 ms (≈13 ms for home-screen-like content). Then about 11–13 frames/s is expected on one core. Getting
anywhere near 60 needs more than a cheaper scaler.

## Levers, ranked by gain per frame and what each needs

| # | Lever | What it removes | What it needs |
| --- | --- | --- | --- |
| 1 | Display hardware (DECON/DPP) scans the surface itself and scales it to the panel | the whole 70.7 ms: no CPU copy | DPP scaler and RDMA programming from this phone's stock sources (NAT-070 showed DECON0 in command mode with RDMA0/1 at 1080×2340); a surface in memory the DPU can reach (contiguous, or through its SysMMU) |
| 2 | More cores (SMP) | `fb_threads` rows in parallel; the renderer and the driver on different cores | the secondary-core start (NAT-153: cores enter at EL2); that line is currently paused |
| 3 | `fb_filter=0` (nearest) | ≈ 3–11× of the scaling work (host ratio) | a boot argument only: no kernel change, the loader's checks are unaffected |
| 4 | `fbscale=2` (iOS draws 750×1624) | 2.25× fewer pixels to render; the driver's output pixel count stays the same | a boot argument only (upstream-documented); changes the UI's scale |
| 5 | `fb_threads=1` on one core | the helpers' switching | a boot argument only; small gain expected |
| 6 | `rec_secs=0` | `record()`'s 304,500 strided pixels per frame | a boot argument only, but it loses the frame recording, which is evidence of what was shown |
| — | GPU (Xclipse) rendering | the ~70 ms of software rendering | GPU-017/018 line (power, firmware, secure calls from stock sources) |

## Next native frame-rate measurement

A separate native task: scH plus `fb_filter=0`, with one variable and everything else as in NAT-153, so that the driver time and
the frame rate can be compared directly with NAT-153's 70.7 ms and 6–7/s. The display animated by itself in NAT-153, which gave
steady windows from 341 s without touch, so the comparison does not depend on the owner. `fbscale=2` comes after it as a second,
separate step.
