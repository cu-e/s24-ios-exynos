# Decision 0068: one NAT-168 run of loader-diag-xnu-scN-md1 (touch SPI half-bit 8)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded CPU, input and display experiments, new kernels and images included, without a separate question. This
file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-166 (pass, L2-saturated) found cpu0 busy in every 1 s sample, and the e1s touch poll thread taking ~19.3 s per 1000 polls with
a 10 ms sleep: ~9.3 ms of bit-banged SPI per poll, about half of cpu0. The half-bit is 400 volatile loops (~4 kHz SPI); the stock
DTS allows this chip 10 MHz. scN (NAT-167) changes only the kernel default `e1s_halfbit` 400 → 8 (`otool -d`: 0x190 → 0x8).
Everything else, command line included (`cpuload=1000` kept), is scM's with the tag changed.

This is not a repeat: NAT-166 passed, and this is a new image with one changed variable.

## Image

loader-diag-xnu-scN-md1 (NAT-167):
- RECOVERY `artifacts/nat-167/package-001/loader-diag-xnu-scN-md1/recovery.img`, SHA-256 408e8ff3d6202ae2df9e5bde3dc6a2a06ce94f5ac9d0ed89c3acd83e3c203b6b (100663296 bytes);
- payload a36f0405ab89eb66122e8ebf3162d9604da1d368578d64c6c1eac787ee03a56c (26206800 bytes at 2048);
- loader Image da620fd8144491866ff0811639ba3465ac301391ed542ffa774144a2a57854c0;
- kernel no-storage eb0f0a1ee4ed7e1c101a64015c90f08498ba39d223f649f35b57f4375f778144: NAT-165's objects, only `bsd/e1s_touch.o` changed.

Loader checkpoint check rc 0 with the 13 constants on the NAT-143 symbols; relocscan 0 not allowed; command line 255 bytes.

Written only to RECOVERY /dev/block/sda18 with a full-hash readback before the single reboot
(`docs/procedures/nat-167/session_nat168.py`, 8dfb76a4…3231). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-168/touch168.py` (SHA-256 b2ded69e8d2153bc5e0f8a199e5e7a0a911e2eb0435011c55df4e9faf0c6cf4e):
- **T-fail:** no `device id: ok` or no `event thread started`: the chip does not work at this half-bit. The run is then a fail of
  this default (not of touch in general), and the next step is a middle value, not a repeat.
- **P1:** ≤ 12.0 s per 1000 polls (least-squares slope over the marks); **P-part:** 12–17; **P0:** ≥ 17 (NAT-166: 19.58 by this tool).

Also reported, not graded for pass:
- `load166.py` cpu0 verdict (NAT-166: L2, 100%); a drop below L2 means the poll was the main load;
- `frames159.py` against NAT-166 (9.61/s, driver 26.00 ms);
- the display verdicts.

No kernel text at all is **inconclusive**.

## Risk, time limit, stop mechanism, restore

Same as decisions 0063–0067: delivery cap 225 s, receive cap 240 s; timed return 270 s with the fed watchdog; loader deadline 595 s →
Download Mode; watcher and collector 720 s.

The change is a delay constant in a GPIO bit-bang loop. A faster SPI clock than the chip accepts gives wrong reads (ID check
fails, logged), not electrical harm: the pins, levels and pin directions are unchanged, and 8 loops is still far below 10 MHz.

If the kernel fails before it takes over the watchdog, the phone may loop through SEC_UPLOAD (NAT-146). Then:
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written, and iOS runs from RAM. Restore: nat-012 `restore_stock.py` with the venv python;
`check_android.py` and nat-013 assess; `task done` or `task update` BEFORE the permission is closed. One attempt, no retry without
a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen (comparability with NAT-166).
