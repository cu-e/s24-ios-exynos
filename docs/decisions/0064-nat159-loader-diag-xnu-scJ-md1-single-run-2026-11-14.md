# Decision 0064: one NAT-159 run of loader-diag-xnu-scJ-md1 (nearest-neighbour framebuffer scaling)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 (the owner's standing authorization of 2026-11-14) names bounded display experiments and frame-rate measurement, with
new images, hashes and durations needing no separate question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-153 (decision 0063) ran scH and returned with stock RECOVERY restored and Android verified. In its steady windows after the
recording ended (346–382 s, 8 windows), MiniIOMobileFramebuffer took **70.68 ms per frame in the driver** (median), at
**6.99 frames/s** (median), on the single running core. These figures come from `docs/procedures/nat-159/frames159.py` on
`artifacts/nat-153/analysis/kernel-text.txt`.

NAT-156 (source review + host timing) found that this time is the CPU's bilinear scaling of the 1125×2436 surface onto the
1080×2340 panel. On the host the same loops cost 3–11 times more bilinear than nearest. scJ (NAT-158) changes only that:
- boot-arg `fb_filter=0`;
- the recording tokens `rec_secs=270 rec_mb=64` dropped for room. NAT-153's recording had ended before the windows compared.

This is not a repeat of a failed run. NAT-153 passed. The run measures one new variable.

## Image

loader-diag-xnu-scJ-md1 (NAT-158):
- RECOVERY `artifacts/nat-158/package-001/loader-diag-xnu-scJ-md1/recovery.img`,
  SHA-256 778300380b4ccd975d34e1cee89aca428db68db88d9e48232376399367a7003a (100663296 bytes);
- payload cd9823e1ce5a4b4d38d7e6d63fc9e0fe2142bfded8bd1710b782664336089ce5 (26206800 bytes at 2048);
- loader Image 7217ef2c2f5b2d2a0209054cc8643e44f91440c02d9ea7153b04a3cc6e917238;
- kernel: scH's, 8d62baff503ddfe75ebf388fa13e9e8bf47cf46e942b54887f5c9221b44d14b4 (`artifacts/nat-152/kernel-001`).

Changes against scH:
- the command line (`fb_filter=0` in place of the two recording tokens, the attempt tag);
- loader `ckpt3.c` (NAT-157: messages without absolute pointers);
- the image name compiled into the loader.

Every byte of `payload.adt8.bin` after the command-line field is scH's. The loader's checkpoint check on this payload gives rc 0, with
the 13 constants on the NAT-143 symbols. relocscan finds 0 relocations that are not allowed.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-158/session_nat159.py`, 0fa7d22e…e2ae). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

1. **Loader:** it passes its checks and jumps to the kernel, so a kernel ring arrives. If not, the loader's CK records say where it
   stopped. A failed check now prints its message (NAT-157).
2. **Frames** (`frames159.py`, the same rule as for NAT-153: windows of 4500–5600 ms with at least 10 frames). At least 3 steady
   windows are needed for a verdict; fewer is inconclusive. Driver time, median against NAT-153's 70.68 ms:
   - **F2:** ≤ 35.3 ms (at most half);
   - **F1:** 35.3–63.6 ms;
   - **F0:** ≥ 63.6 ms (less than 10% gain).
3. **Also reported, not graded:** frames/s median against 6.99, `other_ms` (interval minus driver) against 72.4 ms, GPU wait and late
   swaps.
4. **Display:** `decode113` P1 (the panel has pixels) and `analyze150`'s display verdict, as in NAT-153.

Frame rate here is the kernel's count, not a camera measurement. It does not establish the panel's refresh rate or input latency.

## Risk, time limit, stop mechanism, restore

Same as decision 0063 (NAT-153 ran this exact path):
- delivery cap 225 s, receive cap 240 s;
- timed return 270 s with the fed watchdog;
- loader deadline 595 s → Download Mode;
- watcher and collector 720 s.

The kernel is scH's, and cpu 1–9 are started by PSCI `CPU_ON` as in NAT-153. They enter at EL2 and stay off; nothing new is asked of
them.

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

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen during the run. NAT-153 had no touch events, so the
windows are comparable only without touch.
