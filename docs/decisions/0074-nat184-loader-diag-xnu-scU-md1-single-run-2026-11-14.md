# Decision 0074: one NAT-184 run of loader-diag-xnu-scU-md1 (framebuffer scaling from a per-layer run table)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded display experiments, new kernels and images included, without a separate question. This file is the
per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-181 (K0) showed that NAT-180's run copy did not shorten the driver: 8.74 ms per frame. NAT-182 measured the reason on the same
A520 core and clock, from Android userland. Finding the runs per pixel costs as much as the per-pixel copy (7.83 against 7.44 ms),
while runs found once and copied with 45 `memcpy` per row take 2.32 ms, with the same pixels.

NAT-183 puts that table into the driver. This is a new verifiable reason: the run-table form has not run natively, and NAT-182 predicts
a driver time well under 5 ms.

## What changes against NAT-177's image

- **Changed.** Only `iokit/MiniIOMobileFramebuffer.cpo` (`docs/procedures/nat-183/MiniIOMobileFramebuffer.patch`, additions only):
  - a run table built in `drawLayer()` for nearest-neighbour;
  - `memcpy` per run in `drawRows()`;
  - the per-pixel loop kept as the fallback.
- **Not touched.** No register, no mapping and no new memory beyond a 1080-entry table allocated at start. The framebuffer addresses
  and values written are the same.
- **Kept from NAT-177.** The read-only display snapshot, the swipe thread, `touch_lat=1` and the stock cpu0 FREQ_REQ of decision 0070.

## Image

loader-diag-xnu-scU-md1 (NAT-183):
- RECOVERY `artifacts/nat-183/package-001/loader-diag-xnu-scU-md1/recovery.img`, SHA-256
  bd274be10ff2b3dba21cecc62880d237a2aebdf3f35910bfc0016b6db4cb95a0 (100663296 bytes);
- payload 329967960461b08699f7ce453c31ec8ec5ffdc4fa58809bb74a19d33fa1b0b7a (26207520 bytes at 2048);
- loader Image fe453212767c7d695940f56a14bf41f58a33b7788c0506f97e27a4a1b1ce141f;
- kernel no-storage 564946fbb7b9e27a99978e6b77c4c5eb29658162bc9fd2e2a9eb019993f2bb4a: NAT-176's objects plus
  `iokit/MiniIOMobileFramebuffer.cpo`.

Loader sites check rc 0; relocscan clean; command line 254 bytes (scS's with the tag `nat_attempt=NAT183-scU`).

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-183/session_nat184.py`, ec619f9ab9c053d03a2c3b6bae68c6004dcf612425b81c9d2372c84386053b67). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-180/fbcopy181.py` (unchanged) reads the driver time: the median of "us each in the driver" over the steady 5 s
windows.

| verdict | condition |
|---|---|
| K-none | no steady window: inconclusive |
| K2 | median ≤ 5.0 ms |
| K1 | median < 8.0 ms |
| K0 | median ≥ 8.0 ms |

Reported beside K:
- `swipe175`'s verdict and the swipe copy median. They are compared only where the swipes animated, which shows as more than one swap per
  swipe (NAT-181);
- dpp177 (it must stay R-ok and identical);
- cpuclk173, touch170 and frames159;
- the display verdicts and the panel thumbnail, where a wrong picture would show;
- whether the timed return was reached.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0072:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

Specific risk: a wrong run table could draw a wrong picture or write past a row. The host tests (verbatim code, 2000 random maps)
exclude that, and every run lies inside the range the loop wrote. If the kernel stops, the fed watchdog expires and the loader deadline or
the SEC_UPLOAD procedure applies.

If the phone loops through SEC_UPLOAD (NAT-146):
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down until the blue screen and presses
   Volume Up for Download Mode;
3. the stock restore follows.

No partition other than RECOVERY is written. Restore: nat-012 `restore_stock.py` with the venv python, then `check_android.py` and
nat-013 assess. `task done` or `task update` comes BEFORE the permission is closed. One attempt, and no retry without a new verifiable
reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
