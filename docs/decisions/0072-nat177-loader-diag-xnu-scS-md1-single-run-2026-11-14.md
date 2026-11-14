# Decision 0072: one NAT-177 run of loader-diag-xnu-scS-md1 (read-only display-layer snapshot)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded display experiments, new kernels and images included, without a separate question. This file is the
per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-175 (F30) measured 8.77 ms of CPU scaling in every frame under animation, on the only running core. Display-hardware scaling
through DPP1 (NAT-162) would remove that cost. Before any scaler register can be written, its current state and its power have to
be read on this phone. This run is that first read-only step. It is not a repeat of an earlier run: no DPP, SRAMC or SysMMU
register has been read before.

## What changes against NAT-175's image

Only `bsd/e1s_display.o` changes, and it only reads:
- **Gate.** First the stock PMU status words DPUB 0x12861D44, DPUF0 0x12861D84 and DPUF1 0x128626C4, all bit 0
  (`flexpmu_cal_local_s5e9945.h:819, 898, 916`). If any bit is 0, nothing else is read.
- **Reads, if all three are on:**
  - DECON 0x19100000 +0x4/0x30/0x50/0x60/0x200/0x204;
  - windows 0x19112000 and 0x19113000 at +0x0..0x1C and +0x800..0x81C;
  - WINCON 0x19132000 and 0x19133000 at +0x0;
  - DMA 0x19900000 and 0x19901000 at +0x8..0x1C, 0x40, 0x50, 0x200, 0x338, 0x740 and +0x408..0x450;
  - DPP 0x19930000 and 0x19931000 at +0x0, 0x1C, 0x30..0x3C, 0x80..0x98;
  - SRAMC 0x19950000 and 0x19951000 at +0x10/0x14;
  - SysMMU 0x19840000 at +0x0, 0x8, 0x34, 0x8000, 0x8404.
- **When.** At probe and once at 300 s of uptime.

No register is written by this code (static check and a read-only fake MMIO, NAT-176). Everything else is NAT-175's image: the
swipe thread, `touch_lat=1`, and the stock cpu0 FREQ_REQ of decision 0070.

## Image

loader-diag-xnu-scS-md1 (NAT-176):
- RECOVERY `artifacts/nat-176/package-001/loader-diag-xnu-scS-md1/recovery.img`, SHA-256 002f5653014155df0f19226ae5d2d7cdf696c70ea5fae7b1d968745321b6fdbd (100663296 bytes);
- payload 61dcbd3e463bc458238ec3bf62a0e43add3695d061a3c05d3824ac2924524e97 (26207232 bytes at 2048);
- loader Image 9a6f79399f89649fd6568fe917929f3df086c832d945dd72244bf2ee0a9af697;
- kernel no-storage d84b4ce0e6aed7d730dff9a2afbea49baf84d2eadfbb669e12e230be86966a58: NAT-174's objects plus `bsd/e1s_display.o`.

Loader sites check rc 0; relocscan clean; command line 254 bytes.

Written only to RECOVERY /dev/block/sda18 with a full-hash readback before the single reboot
(`docs/procedures/nat-176/session_nat177.py`, 93ed6dad53946973d850cc52ccfb2761d2b560285b5d760d195371ba230e96bb). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-176/dpp177.py` (SHA-256 72d8f985f8acd504bbe3e0847c6d3f7f7796c519b9f94a2ee9d441a4e50d2195):
- **R-ok:** all 12 groups present in both snapshots;
- **R-partial:** groups missing;
- **R-gated:** a power domain reported off;
- **R-none:** no snapshot line.

Decoded and reported: the DPP channel feeding each enabled window and whether it has a scaler, DMA base/format/sizes, the DPP scaler
state, SysMMU translating or bypassed, and changes between probe and late.

Also reported: `swipe175` (F30 reproduced?) and `cpuclk173` (C2), plus `touch170`, `frames159`, the display verdicts, and whether
the timed return was reached.

## Risk, time limit, stop mechanism, restore

Same bounds as decisions 0063–0071: delivery cap 225 s, receive cap 240 s; timed return 270 s with the fed watchdog; loader
deadline 595 s → Download Mode; watcher and collector 720 s.

Specific risk: a load from an unclocked or unpowered block can hang the bus or raise an SError. It is mitigated by the PMU gate,
NAT-070's earlier successful reads of DMA L0–L3 in the same DPUF0 region, and the per-group lines. If the kernel stops, the fed
watchdog expires, and the loader deadline or the SEC_UPLOAD procedure applies.

If the phone loops through SEC_UPLOAD (NAT-146):
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

No partition other than RECOVERY is written. Restore: nat-012 `restore_stock.py` with the venv python; `check_android.py` and
nat-013 assess; `task done` or `task update` BEFORE the permission is closed. One attempt, no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
