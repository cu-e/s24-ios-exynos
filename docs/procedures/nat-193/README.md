# NAT-193: scZ, the UI at two pixels a point for the swipe benchmark (host)

**WITHDRAWN by the owner on 2026-11-14, before any run.** Reducing the UI resolution is a quality compromise, and the owner does not
want it. Decision 0079 was deleted unused, NAT-193 is blocked and NAT-194 is deprioritised. Nothing ran on the phone. This file is
kept only as a record of the host work; the reference build is `docs/reference-build.md`.

**Evidence kind:** host-test (record only).

## Why

NAT-192 profiled backboardd, which takes 76 % of the only running core during the synthetic swipes (NAT-186). Its time is software
composition in QuartzCore, and every part of it is per pixel:
- filtered resampling of layer images, about 35 %;
- superellipse corner masks with `powf` per pixel, about 15 %;
- an `atan2f` span, about 15 %;
- vImage blending, about 7 %.

The cheapest lever is to compose fewer pixels. MiniIOMobileFramebuffer has an upstream boot-arg for it, `fbscale=2`.

NAT-161 tried `fbscale=2` once, on the idle home screen, where frames come at the content's own pace (about 10/s), so it could not show
a CPU gain. The synthetic swipes (NAT-174) and the per-process CPU sampler (NAT-185) now give a capacity measurement.

## Where the canvas size comes from (source review of the 20F66 cache, with `dscdis.py`)

- QuartzCore's display setup (`sub_18852b3dc`) asks IOMobileFramebuffer for the display size (`IOMobileFramebufferGetDisplaySize`)
  and the canvas sizes (`IOMobileFramebufferGetCanvasSizes`, last entry). Environment variables `CA_LCD_WIDTH`, `CA_LCD_HEIGHT`,
  `CA_CANVAS_WIDTH` and `CA_CANVAS_HEIGHT` override them. It also reads `IOMobileFramebufferGetDotPitch` and
  `IOMobileFramebufferGetDisplayArea`.
- IOMobileFramebuffer fills the canvas from the service properties `canvas-width` and `canvas-height`, unless the preferences of domain
  `com.apple.iokit.IOMobileGraphicsFamily` (`canvas_width`, `canvas_height`) set it.
- The UI's points-to-pixels scale comes from MobileGestalt, which reads the device tree: `/chosen display-scale` and
  `/product artwork-scale-factor`.

So a smaller canvas alone would leave the scale at 3 and shrink the layout. `fbscale=2` changes both together: the driver reports
750×1624 and writes scale 2 into those two device-tree properties before userland starts, so the layout stays 375×812 points.

## What scZ is

scZ is scV (NAT-185, which ran in NAT-186 and NAT-188) with one boot-arg swapped:

| | scV | scZ |
|---|---|---|
| token | `touch_lat=1` | `fbscale=2` |
| tag | `nat_attempt=NAT185-scV` | `nat_attempt=NAT193-scZ` |
| command line | 254 B | 252 B |

Why a swap, not an addition: the chain keeps the line within 255 bytes (asserts in `nat-158`/`nat-165` and every image since). The loader,
the payload format and the arm64 kernel all have 608-byte buffers, so this is a project convention, not a hardware limit; it is kept
here.

What `touch_lat=1` did: it printed the per-swap `tl:` lines. The NAT-194 verdict, bbd188, does not read them. `swipe175` does, so it has no
input in NAT-194.

Everything else is scV's:
- the kernel (`artifacts/nat-185/kernel-001`, no-storage `d7e7fee1…`);
- the md0 root (NAT-110, `6e9bdcef…`);
- the ADT, the synthetic swipe thread and every other token.

`build.py` wraps `nat-185/build.py`. It sets NAT-174's token pair to `('fb_filter=0', 'fbscale=2')` and, inside NAT-165's step, expects
`fbscale=2` where NAT-174 expected `touch_lat=1`. It then requires the final line to equal scV's with that one token and the tag replaced.

## What `fbscale=2` does in the driver (source review of NAT-185's MiniIOMobileFramebuffer.cpp)

- With `fbscale` set and not 3, the reported size becomes 375 × 2 by 812 × 2 = 750×1624.
- The driver sets `/chosen display-scale` and `/product artwork-scale-factor` to 2 in the I/O registry.
- The panel is still written in full, 1080×2340, nearest-neighbour (`fb_filter=0`), now enlarging. NAT-183's run table handles any
  monotonic map; its host test checks 750 → 1080 byte for byte against the per-pixel loop. An upscale gives 331 runs per row instead of
  45, so the driver's copy is expected to cost more than scV's 2.16 ms. NAT-194 measures it (fbcopy181).

## Host checks

`python3 -B docs/procedures/nat-193/test_nat193.py`: 6 OK.
- **Command line.** Token by token against scV, exactly two differ: the tag, and `touch_lat=1` → `fbscale=2`. 252 bytes. The safety
  tokens are present: `e1sufs=0`, `e1skeys=0`, `e1spmic=2`, `small_cores=0`, `e1s_wdt_pet=1`, `loader_return_after=270`.
- **Same kernel and root.** The kernel hash, md0 hash, md1 reserve and ADT offset and size equal scV's. Loader sites rc 0 / ok / bad 0.
- **Payload.** Same length as scV's. From the command line on, every byte is identical (XNU segments, ADT, md0). Before it, fewer than
  32 bytes differ, all inside the loader image: the tag-derived constants of `markerlib52`/`ckpt3`, as in every tag change.
- **Driver source.** The `fbscale` tunable, the 375×812 points, both device-tree properties and the run table, as above.
- **Analyser.** bbd188 on NAT-186's log with every `tl:` line removed gives the same rows and the same 67.95 ms.
- **Session.** `derive194.py --check` passes. The session pins the package's RECOVERY and payload hashes, and the RECOVERY file hashes to
  the pinned value.

`python3 -B docs/procedures/nat-183/test_nat183.py` was rerun: 3 OK.

## Image

- **Build** `artifacts/nat-193/build-001`; loader Image `67455140…`.
- **Package** `artifacts/nat-193/package-001`, `loader-diag-xnu-scZ-md1`:
  - RECOVERY `ae2199c2c660f02b12eb7bfe202dc8bd124ef121a8e74a81ee9851ac3af3b4c3`;
  - payload `6719580fb01a2de16261a82c5daf97411b7da71ee2cef26c15bf11f180cb629f` (26208032 B at 2048).
- **Session** `session_nat194.py` (`4e57ff10…`), derived by counted replacement from NAT-177's driver by `derive194.py`. Only the image,
  its hashes, the package, the decision glob, the marker and the precondition list change.

## Registered verdicts for NAT-194

These are in decision 0079. bbd188, unchanged, against NAT-186's 67.95 ms per frame:

| verdict | condition |
|---|---|
| B-none | no span with frames: inconclusive |
| B2 | median ≤ 33.98 ms |
| B1 | median ≤ 54.36 ms |
| B0 | otherwise |

A purely per-pixel cost would give about 30 ms.

Reported beside it:
- frames per 5 s;
- top186 shares;
- fbcopy181 K;
- the `display 750x1624` line and the swap sizes;
- the panel thumbnail;
- cpuclk173, touch170, the display verdicts and the timed return.

## Not established here

- Whether iOS at scale 2 finds 2× artwork in this 3× device's root. Missing 2× assets would be resampled from 3× ones, which costs
  resampling work. NAT-161 showed that the home screen comes up.
- The driver's cost for the 750 → 1080 enlargement on the phone.
- Whether the swipes drift into the Today view, as in NAT-186. That view costs about 190 ms per frame against 30 ms on the home pages.
  The median over the spans is the registered measure because of that.
