# NAT-177: the display layers S-Boot leaves running (native, decision 0072)

**Evidence kind:** native-device. **Image:** loader-diag-xnu-scS-md1 (NAT-176), one run on 2026-11-14. The phone was restored with
stock RECOVERY (full hash checked) and Android verified.

## Result: R-ok

PMU DPUB, DPUF0 and DPUF1 all read 0x1. All 12 groups were read at 123.09 s and again at 300.34 s, and only FRAME_COUNT differs
between the two (`analysis/dpp-lines.txt`, `analysis/dpp177.json`).

| Block | Value | Meaning |
|---|---|---|
| WINCON2 / WINCON3 | 0x1 / 0x11 | both on; CHMAP 0 → DPP0 (no scaler), CHMAP 1 → DPP1 (scaler) |
| win2 / win3 position | (0,0)–(1079,2339) both | both cover the panel; win3 FUNC_CON 0xff0d02 (on top, alpha 0xff) |
| DMA0 / DMA1 | IN_CTRL 0xff400000, 1080×2340, BASEADDR 0xfa200000 (shadow equal) | ARGB8888; both read the one buffer the CPU fills |
| DPP0 / DPP1 | id 0x07030000, CFG_ERR 0, SCL_CTRL 0, ratios 0x100000 | scalers off (1.0) |
| SRAMC0 / SRAMC1 | 0 / 0 | no scaler SRAM mode |
| SysMMU 0x19840000 | CTRL 0, CTRL_VM 0x24 (bit 0 clear), FLPT 0, version 0x90010000 | not translating: DMA addresses are physical |
| DECON | TRIG_CON 0x3063, SHD_REG_UP_REQ 0, INT_EN 0x303011, DATA_PATH 0xb1 | command mode, no pending shadow update |
| FRAME_COUNT | 11141 → 32413 in 177.25 s | **120.01 Hz**: the panel scans at 120 Hz |

The other analysers repeat NAT-175's results:
- swipes F30 again (median 21.0 ms against 20.92 ms; copy 8.77 ms; beat wait 5.37 ms);
- cpu0 C2;
- touch P1 (11.53 s per 1000 polls);
- display W-ok / D2 / S1 / P2;
- the timed return was reached.

## What follows

- **I:** display-hardware scaling needs no IOMMU work, because the SysMMU is bypassed. DMA1/DPP1 must take a physically
  contiguous 1125×2436 ARGB buffer with the DPP1 scaler on. The CPU then copies unscaled, or later not at all, and win2/DMA0 can be
  left as they are or turned off.
- NAT-178 (source review) pins the exact stock register sequence and the coefficients before any write.
- The 120-Hz scan is a direct input to the 120-FPS goal. The driver's beat (`fb_hz`) is 60 today.

## Not established

- Which of win2/win3 the panel actually shows. Both cover it with the same buffer, and win3 is on top.
- The BASEADDR width above 32 bits and the alignment rule.
- Whether scaler programming works on this phone.
