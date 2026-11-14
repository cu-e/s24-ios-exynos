# Decision 0069: one NAT-170 run of loader-diag-xnu-scO-md1 (shadowed GPP9 DAT, IRQ-gated touch poll)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded CPU, input and display experiments, new kernels and images included, without a separate question. This
file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-168 (pass, verdict P0) showed that the half-bit delay is not the touch poll's cost. The GPIO MMIO is: 4 loads and 3 stores of GPP9
`DAT` per bit, ~8.5 µs per access (inference), ~9.5 ms per 10 ms poll, while cpu0 is 100% busy. scO (NAT-169) changes only the touch
driver:
- `DAT` is shadowed per transfer, with the same waveform on the host peer;
- the poll reads the STM only on a low gpa1-2, the stock level-low IRQ line, or on every 25th poll.

This is not a repeat: a new image with a new, host-tested change after a passing run.

## Image

loader-diag-xnu-scO-md1 (NAT-169):
- RECOVERY `artifacts/nat-169/package-001/loader-diag-xnu-scO-md1/recovery.img`, SHA-256 8f67d7df1c9ed616add76f9fb873b76e3e78d972d92d6acbb25e99d916a28b4e (100663296 bytes);
- payload 70119f7502f05774e11b18f739a301828e1d9eac2a0131a16b295670527312f0 (26206864 bytes at 2048);
- loader Image 662f78b74676edc3c56c2558c40ae7504faf789e181dcb52570b2c8374252a01;
- kernel no-storage e32e36c1ad958c28e26ce58ad979fe408bafe1035d94987ce183ee79dce39ba0: NAT-167's objects, only `bsd/e1s_touch.o` changed.

Loader sites check rc 0 (13 constants on the NAT-143 symbols); relocscan 0 not allowed; command line 255 bytes.

Written only to RECOVERY /dev/block/sda18 with a full-hash readback before the single reboot
(`docs/procedures/nat-169/session_nat170.py`, 0aaa35e4…67e1). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-169/touch170.py` (SHA-256 c1bc16ea92c3c83c0d2dad530ec33182cac6d27a8d3a733d81328623b35812e4):
- **T-fail:** no `device id: ok` or no `event thread started`. The shadowed transfer then does not work on the chip.
- **G-fail:** a full read on a high line found events (E > 0). The line is not level-low while events are pending, so the gate is
  wrong.
- **P1:** ≤ 12.0 s per 1000 polls; **P-part:** 12–17; **P0:** ≥ 17 (NAT-168: 19.47).

Also reported, not graded for pass:
- the device ID read time against NAT-168's 5.241 ms, and the load/store split estimated from it;
- `load166.py` cpu0 verdict (NAT-168: L2, 100%);
- `frames159.py` against NAT-168 (9.55/s, driver 25.94 ms);
- the display verdicts.

No kernel text is **inconclusive**. With no touch, E covers only the chip's own status events; a touch run is a separate step.

## Risk, time limit, stop mechanism, restore

Same as decisions 0063–0068: delivery cap 225 s, receive cap 240 s; timed return 270 s with the fed watchdog; loader deadline 595 s →
Download Mode; watcher and collector 720 s.

The change does fewer GPIO reads and more skipped polls. The pins, their directions, levels and order on the wire are those of
NAT-168, which the host peer checked. The SPI clock is faster (fewer accesses per bit) but still far below the stock 10 MHz.

If the kernel fails before it takes over the watchdog, the phone may loop through SEC_UPLOAD (NAT-146). Then:
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written, and iOS runs from RAM. Restore: nat-012 `restore_stock.py` with the venv python;
`check_android.py` and nat-013 assess; `task done` or `task update` BEFORE the permission is closed. One attempt, no retry without
a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen (comparability with NAT-168).
