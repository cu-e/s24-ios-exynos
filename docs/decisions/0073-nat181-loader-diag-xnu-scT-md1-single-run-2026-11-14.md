# Decision 0073: one NAT-181 run of loader-diag-xnu-scT-md1 (framebuffer scaling copied by column runs)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded display experiments, new kernels and images included, without a separate question. This file is the
per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-175 and NAT-177 measured the framebuffer driver at 8.77–8.91 ms of every frame on the only running core. Nearly all of it is the
per-pixel nearest-neighbour copy from 1125×2436 to 1080×2340. NAT-180 replaces that loop with a `memcpy` per run of consecutive source
columns, 45 runs per row, and the host tests show the pixels are the same.

This is not a repeat: the framebuffer object has not run in this form before. The question is how much the phone saves, which only the
phone can show, because it depends on write-combining bandwidth.

## What changes against NAT-177's image

- **Changed.** Only `iokit/MiniIOMobileFramebuffer.cpo`, and only the `fb_filter=0` row copy in `drawRows()`
  (`docs/procedures/nat-180/MiniIOMobileFramebuffer.patch`).
- **Not touched.** No register, no mapping and no allocation. The same framebuffer addresses are written with the same values.
- **Kept from NAT-177.** The read-only display snapshot, the swipe thread, `touch_lat=1` and the stock cpu0 FREQ_REQ of decision 0070.

## Image

loader-diag-xnu-scT-md1 (NAT-180):
- RECOVERY `artifacts/nat-180/package-001/loader-diag-xnu-scT-md1/recovery.img`, SHA-256
  4aa3d32ca90c98c2e810e49892454f945386b63f384d6af1e7ee9221bdd653ac (100663296 bytes);
- payload 4a520259a1403d2467092a4eb6c915c172aca678b866c63fbf979290d24df24d (26207328 bytes at 2048);
- loader Image d9e760bdfb14a988578734a71bd6c7d92ad35090e4a391c85a779c766a162ba4;
- kernel no-storage bdb71bd6ca366b7565a6252f42876486cb088a958fb7b870c16dea8bff76f4b4: NAT-176's objects plus
  `iokit/MiniIOMobileFramebuffer.cpo`.

Loader sites check rc 0; relocscan clean; command line 254 bytes (scS's with the tag `nat_attempt=NAT180-scT`).

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-180/session_nat181.py`, 0fb770a12fe2a16f88a0e53a6eda2dcb15864ed42c28af9f81d32e16e8afba67). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-180/fbcopy181.py` reads the driver time: the median of "us each in the driver" over the steady 5 s windows. The
baseline is NAT-177's 8.914 ms.

| verdict | condition |
|---|---|
| K-none | no steady window: inconclusive |
| K2 | median ≤ 5.0 ms |
| K1 | median < 8.0 ms |
| K0 | median ≥ 8.0 ms: no gain shown |

Reported beside K:
- `swipe175`'s verdict (F60 ≤ 18 ms / F30 ≤ 36 ms / F-low) and the swipe copy median;
- dpp177 (the snapshot must still be R-ok with the same values);
- cpuclk173, touch170 and frames159;
- the display verdicts, where a wrong picture would show;
- whether the timed return was reached.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0072:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

Specific risk: a wrong run computation could draw a wrong picture or write past a row. The host tests exclude that for the driver's
real map, and the destination range is the one the loop wrote. If the kernel stops, the fed watchdog expires and the loader deadline or
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
