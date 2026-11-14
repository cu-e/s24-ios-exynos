# Decision 0065: one NAT-161 run of loader-diag-xnu-scK-md1 (2× UI scale, nearest-neighbour framebuffer)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 (the owner's standing authorization of 2026-11-14) names bounded display experiments and frame-rate measurement, with
new images, hashes and durations needing no separate question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-159 (decision 0064, pass) cut the framebuffer driver's time per frame from 70.68 to 26.00 ms with `fb_filter=0`. The frame
interval is now 108 ms (9.26 frames/s, median), and about 82 ms of it lies outside the driver: iOS's software rendering and
everything else on the single running core.

scK (NAT-160) adds one boot argument to scJ, `fbscale=2`, which is upstream-documented in MiniIOMobileFramebuffer.cpp:
- the screen is reported as 750×1624 (375×812 points at 2 px) instead of 1125×2436;
- the scale is published at `/chosen display-scale` and `/product artwork-scale-factor`;
- iOS then renders 2.25 times fewer pixels.

This is a new variable after a passing run, not a repeat.

## Image

loader-diag-xnu-scK-md1 (NAT-160):
- RECOVERY `artifacts/nat-160/package-001/loader-diag-xnu-scK-md1/recovery.img`,
  SHA-256 3fb15e16cb9ef20ca94c35c68abf66bbc52ca09c828f60d46b26b63c8cfdea5d (100663296 bytes);
- payload 1073e982038250e9d2daa24650dd80f641f51162d0f7511a8fbac4f291c0b98c (26206800 bytes at 2048);
- loader Image 8b61dc7157876205ce2423d6f8fe07bb8b53affa7952ffccd1723ad6c13730e3;
- kernel: scH's, 8d62baff503ddfe75ebf388fa13e9e8bf47cf46e942b54887f5c9221b44d14b4.

Changes against scJ:
- `fbscale=2` in the command line (252 bytes);
- the attempt tag;
- the image name compiled into the loader.

The payload is byte-identical to scJ's after the cmdline field. The loader's checkpoint check gives rc 0 with the NAT-143 symbols, and
relocscan finds 0 relocations that are not allowed.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-160/session_nat161.py`, c0f8797f…2dc9). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

1. **Loader and kernel:** as in NAT-159; the loader's CK records if no kernel ring arrives.
2. **UI at scale 2:** the driver's swap lines show surface 750×1624. If there is no swap at all, or SpringBoard does not stay up,
   the run is **inconclusive** for the lever.
3. **Frames** (`docs/procedures/nat-159/frames159.py`, the same rule; at least 3 steady windows). Frames/s median against NAT-159's
   9.26:
   - **G2:** ≥ 13.9 (×1.5);
   - **G1:** 10.2–13.9 (> 10%);
   - **G0:** below 10.2.
4. **Also reported:** driver ms per frame (NAT-159: 26.00), time outside the driver (82.0 ms), GPU wait, late swaps.
5. **Display:** decode113 P1 and analyze150's display verdict.

Frame rate here is the kernel's count, not a camera measurement. It does not establish the panel's refresh rate or input latency.

## Risk, time limit, stop mechanism, restore

Same as decisions 0063 and 0064:
- delivery cap 225 s, receive cap 240 s;
- timed return 270 s with the fed watchdog;
- loader deadline 595 s → Download Mode;
- watcher and collector 720 s.

The new part is userland only: iOS at display scale 2. A failure there does not change the kernel's timed return.

If the kernel fails before it takes over the watchdog, the phone may loop through SEC_UPLOAD (NAT-146). Then:
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written, and iOS runs from RAM.

Restore:
1. nat-012 `restore_stock.py` with the venv python;
2. `check_android.py` and nat-013 assess;
3. `task done` (on pass) or `task update` BEFORE the permission is closed.

One attempt, with no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen during the run (comparability with NAT-153/159).
