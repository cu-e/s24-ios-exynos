# NAT-192: where backboardd's time goes (native, decision 0078)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scY-md1 (NAT-191), one run on 2026-11-14 (reboot 07:47:53Z). Afterwards
stock RECOVERY was restored with a full hash check, and Android was verified:
- `restore-001/report.json`, from the nat-012 trace;
- nat-013 assess: pass;
- `check_android.py`: pass, recovery_hash_match true.

## Result: P-ok. Software composition, not copying.

The sampler ran through all four windows with no panic and no lost thread slot:

| window | ticks | samples |
|---|---|---|
| 200–220 s | 17063 | 11326 |
| 220–265 s | 37924 | 30242 |
| 265–310 s | 39105 | 39284 |
| 310–375 s | 56274 | 56734 |

Its own cost was **0.6 %** of the time (`self` 132–388 ms per window). backboardd was pid 16. The shared cache slide was 0x4f150000.

Registered verdict (pc190): **P-ok**, with 69 526 samples over the swipe windows and coarse coverage 0.996.

### Which images, from the fine table (64-byte buckets, 87–92 % coverage)

| | 200–220 | 220–265 | 265–310 | 310–375 |
|---|---|---|---|---|
| QuartzCore | 0.59 | 0.63 | 0.63 | 0.60 |
| libsystem_m (`powf`, `atan2f`) | 0.15 | 0.14 | 0.13 | 0.16 |
| vImage (`vImagePremultipliedAlphaBlend_BGRA8888` path) | 0.07 | 0.06 | 0.07 | 0.07 |
| libsystem_kernel (blocked in traps: `semwait`, activity id) | 0.09 | 0.07 | 0.04 | 0.04 |
| libsystem_platform (memmove etc.) | 0.01 | 0.01 | 0.01 | 0.01 |

**Correction to the registered group line.** `pc190.py` assigns each 64 KiB coarse bucket to the image at the bucket's start. This
is wrong where an image starts inside a bucket. The coarse table therefore names `libsystem_pthread` (0.13–0.16) and
`RegulatoryDomain` (0.04–0.10) for what the fine table resolves as libsystem_m and QuartzCore.

The verdict, P-ok, and the leading group, QuartzCore (`ca`), are unaffected. The group shares in `analysis/pc190.json` are not to be
quoted. The table above is the corrected reading. This is a post-hoc correction, and the analyser is to be fixed before it is used again.

### Which code: QuartzCore's software renderer

Function starts come from the `.symbols` file, where names are `<redacted>`. The code was read with `dscdis.py`: NDK llvm-objdump over
the cache bytes, with stub islands resolved by hand. Over the swipe windows:

- **Bilinear image sampling, about 35 %.**
  - `sub_1884471ec` takes 19–22 % of the samples, `sub_188447348` 10 %, `sub_188448380` 4–6 %.
  - These are one-pixel-per-iteration span loops: 16.16 fixed-point source x and y, four neighbouring texels, NEON `usubl/sqrdmulh/uaddw`
    interpolation, and one 32-bit store.
  - `sub_188448380` forces alpha to 0xff (an opaque source); `sub_188447348` clamps at the edges.
  - Their caller `sub_18843fe04` is the lr in 46–56 % of the samples.
  - In other words, images are resampled with filtering every frame: layer contents drawn at non-integer positions or scales.
- **Continuous-corner masks, about 15 %.**
  - `sub_1884454c8` (3–5 %) calls `powf` 12 times for every 4 pixels: `|x|^p` and `|y|^p`, then the sum `^(1/p)`.
  - Its 8-bit result is replicated into all four channels, which is a superellipse coverage mask: iOS's continuous corners on icons,
    the dock platter, widgets and pills.
  - `powf` alone takes 11–13 %.
- **A span with `atan2f`, about 13–17 %.** `sub_18844755c` takes 10–15 %, plus `atan2f` 2–3 %. That is a per-pixel angle, as in an
  angular (conic) gradient or a rotated sample.
- **vImage premultiplied blend, about 7 %.**
- **Copies under 1 %.**

## Companion verdicts, and how this run differs from NAT-186

Reported in `analysis/`:
- fbcopy181 K2 (2.17 ms);
- cpuclk173 C2;
- touch170 P1;
- display W-ok / D2;
- top186 U-sat (busy 1.0);
- backboardd 0.834 of the core.

bbd188 reads **B0 at 213.5 ms** of backboardd CPU per frame, against NAT-186's 67.95. Frames fell from about 50 per 5 s to about 30 at
200 s, the sampler's start. Before any swipe, the 200–220 s window already had backboardd running in 64 % of the ticks. From 238 s the
panel took 6–9 frames per 5 s.

Two explanations remain open:
1. **Observer effect.** The sampler preempts every 1 ms, walks backboardd's threads and briefly takes its task lock. Its own time is only
   0.6 %, but its effect on backboardd's render thread, through context switches and cache/TLB pressure on the A520, is unmeasured.
2. **A different UI state.** The last frame shows a home page with only the dock, the page pill and the colourful wallpaper, not
   NAT-186's widget view.

The shares above describe what backboardd computes. The absolute cost per frame in this run is not comparable to NAT-186.

## What it means for 60 fps

The cost is per-pixel software composition in QuartzCore:
- filtered resampling;
- superellipse masks with `powf` per pixel;
- an `atan2f` span;
- blending.

None of it is a copy or a driver cost, and blur was already ruled out (NAT-188).

The levers that follow:
- **Fewer pixels.** Render the UI at a lower canvas size and let the driver scale it to the panel. IOMobileFramebuffer reads
  `canvas_width` (string present in the 20F66 cache); every term above scales with the pixel count.
- **Fewer per-pixel transcendental calls.** The masks and the conic-gradient-like spans depend on what is on screen: the wallpaper,
  icon masks and materials.
- **SMP and the GPU.** They remain the structural fixes. NAT-154 and the GPU start await the owner.

## Not established

- The sampler's observer effect on frame rate. A run with `e1spc=0` and the same image would measure it.
- The exact CoreAnimation operations behind the redacted functions. The functions are identified by their code, not by name.
- Why the 200–220 s idle window was already busier than in NAT-186.
