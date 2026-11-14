# Decision 0066: one NAT-164 run of loader-diag-xnu-scL-md1 (per-swap timing lines)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 (the owner's standing authorization of 2026-11-14) covers bounded display and input experiments and measuring frame
rate, panel refresh and input latency separately. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-159 and NAT-161 both passed, with frames on the idle home screen every ~100 ms. NAT-161's CPU split shows the single core about
50% idle. The driver's 5 s statistics cannot say what paces the frames.

scL (NAT-163) is scJ plus `touch_lat=1`. That is instrumentation only: one line per swap, one per frame and one per touch sample,
in the driver's own format. The run is not a repeat: it is the same image as the passing NAT-159 run, with this new
measurement.

## Image

loader-diag-xnu-scL-md1 (NAT-163):
- RECOVERY `artifacts/nat-163/package-001/loader-diag-xnu-scL-md1/recovery.img`, SHA-256 6ab4112f6f9102443b4b7b472562e30aa37f27b17dbd953cdfead7cf50d67f5a (100663296 bytes);
- payload 93a2989acf6ea87dd4055bf63065da5e05b1bf95020d317b50da4c393f57e00b (26206800 bytes at 2048);
- loader Image 5ba8dc29312976e53ca10273708ed917a1e25590f46b89fac4dacdd5d5e14984;
- kernel: scH's, 8d62baff503ddfe75ebf388fa13e9e8bf47cf46e942b54887f5c9221b44d14b4.

The payload is byte-identical to scJ's after the cmdline field (254 bytes). The loader's checkpoint check gives rc 0 on the NAT-143
symbols, and relocscan finds 0 relocations that are not allowed.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-163/session_nat164.py`, da0fd4f2…d8a8). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-163/tl164.py`, for swaps with no touch sample within 1 s:
- **T-cadence:** the swap interval median is ≥ 80 ms, and `swap_to_done` median is ≤ 40 ms. Then CoreAnimation itself hands over
  frames at ~10/s: the pacing is upstream of the driver.
- **T-driver:** `swap_to_done` median is > 40 ms. Frames wait inside the driver (queue or beat).
- **T-fast:** the swap interval median is < 80 ms, while the driver's 5 s lines still show ~10/s. Frames are lost or held.
- Fewer than 50 tl swap lines is **inconclusive**.

If touch samples exist: frames/s during touch (`frames159` windows plus the tl swap interval during touch) and touch-to-panel-memory
latency (kernel part only). Also reported: `frames159` windows against NAT-159 (instrumentation cost) and the display verdicts.

## Risk, time limit, stop mechanism, restore

Same as decisions 0063–0065:
- delivery cap 225 s, receive cap 240 s;
- timed return 270 s with the fed watchdog;
- loader deadline 595 s → Download Mode;
- watcher and collector 720 s.

If the kernel fails before it takes over the watchdog, the phone may loop through SEC_UPLOAD (NAT-146). Then:
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written, and iOS runs from RAM.

Restore:
1. nat-012 `restore_stock.py` with the venv python;
2. `check_android.py` and nat-013 assess;
3. `task done` or `task update` BEFORE the permission is closed.

One attempt, with no retry without a new verifiable reason.

## Physical action asked of the owner (optional)

If you are at the phone: from about 4:30 to 6:00 after the reboot (the home screen is up by then), swipe left and right between the
home-screen pages without stopping, then leave the phone. If you are not there, leave it untouched; the idle measurement does not
need you.
