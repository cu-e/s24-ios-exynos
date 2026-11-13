# NAT-118: the owner's look at the physical panel, and why the framebuffer is not shown whole

Date: 2026-11-13. Kinds: **owner observation** (physical panel, NAT-118 run, decision 0046) + **source-review/analysis** of the
NAT-118 archive. The owner's words (Russian, verbatim): "В прошлом запуске я видел на физическом экране нижнюю полоску iPhone, но не
видел иконок и фона." Translation: "In the last run I saw the iPhone's bottom bar on the physical screen, but did not see icons or
the background." The time within the run at which the owner looked is not known.

This is the first report of an iOS element on the physical panel of this phone. It is an observation, not a recording: no photo.

## What the archive says about the same run (measured, host clock from the reboot command)

| host +s | event |
| --- | --- |
| 26.8 | loader on USB (boot 1) |
| 185-197 | checkpoints 1-27, then the kernel runs (kernel clock ~186 s at bsd_init) |
| ~293-336 kernel s | backboardd swaps the home screen into 0xfa200000, 6-7 frames/s |
| 350.6 | the kernel returns (timer); boot 2 of the loader engine; KL dump starts |
| 353.4-363.8 | PX report: panel memory holds 1,149,581 non-black pixels (home-screen layout) |
| 416.5-447.7 | loader HOLD: marker frames drawn and DECON0 kicked repeatedly |
| ~496 | Download Mode |

## Two mechanisms that explain "bottom bar but no icons or background" (hypotheses, from the code that ran)

1. **The panel is not refreshed while the kernel runs.** DECON0 is in MIPI *command* mode (`GLOBAL_CON 0x133`, NAT-070): the panel
   only takes a new frame when DECON is triggered. In NAT-022 the frame counter advanced (~120/s, from the panel's TE) only after a
   *hardware*-form kick; after the *software*-form kick it did not move. The loader alternates the two forms (`mk_kick`, odd = HW,
   even = SW) and nothing in the kernel kicks DECON (`MiniIOMobileFramebuffer` only `memcpy`s into the buffer; no DECON code).
   Which form the last pre-jump kick had is not recorded; if it was the SW form, the panel froze on the loader's last frame for the
   whole kernel window, and every iOS swap stayed in memory only.
2. **After the return the loader paints over the top 88 % of the buffer.** `mk_ckpt3_hold` and `show()` draw 34 bands of 256 KiB from
   0xfa200000 (`marker.h`: `MK_BANDS = 2 + 32`, `MK_BAND_BYTES = 0x40000`) = 8,912,896 B = rows 0-2063 of 2340 at stride 4320, and
   kick DECON after each draw. Only the bottom ~277 panel rows (iOS rows ~2148-2436 of 2436 after scaling) keep the iOS picture:
   that is exactly the home-indicator/dock strip. Icons and wallpaper are under the bands (black/white stripes).

Mechanism 2 alone predicts the owner's report for any look during the HOLD phase (host +416..496 s). Mechanism 1 predicts that a look
during the kernel window showed no iOS at all. Both are fixable without new hardware knowledge: the HW-form kick is the vendor
sequence the loader has used since NAT-022.

## Next image (NAT-119 build, NAT-120 run)

* Kernel: after checking `GLOBAL_CON` (enabled, command mode), issue the loader's proven HW-form kick from the 10 s heartbeat thread
  (mask HW trigger, global shadow update request, unmask with `HW_TRIG_EN`), log `TRIG_CON` and `FRAME_COUNT` at each kick: the frame
  counter delta between kicks is a measured refresh rate of the panel during iOS (boot-arg `e1s_decon_hw=1`).
* Loader: after the kernel's own return, stop drawing marker bands into the framebuffer (the iOS picture stays; kicks continue).
* Owner: watch the panel from about 4 minutes after the reboot until Download Mode; a photo with the time is the best record.
