# Decision 0070: one NAT-173 run of loader-diag-xnu-scQ-md1 (cpu0 clock probe + one stock DVFS request)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded CPU and clock experiments, and ACPM operations on confirmed stock parameters of this device, new kernels
and images included, without a separate question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-170 (pass) left cpu0 100% busy, rendering ~80 ms of each ~98 ms frame. cpu0 is a Cortex-A520 at the clock S-Boot left. NAT-171
(source review plus an Android readback on this phone) found how stock Android sets that clock: one ACPM IPC message, with the
firmware owning the PLL and the voltage. This is the first DVFS step, not a repeat.

## Exactly what is sent, and where each value comes from

| Item | Value | Source |
| --- | --- | --- |
| Mailbox | APM 0x12B90000, channel 0 | `s5e9945-acpm.dtsi:29-51`; cal_if `acpm-ipc-channel = <0>` (`s5e9945.dts:190`) |
| Channel layout | type 1, 8 × 16 B, AP-polled | logged on this phone (NAT-170 kernel text) |
| Message | `{2 | seq<<16, 1959000, 0, 0}` | `acpm_dvfs.c:26-64`: index 2 = `ACPM_DVFS_CPUCL0` 0x0B040002 (`s5e9945.h:318`), FREQ_REQ = 0 (`acpm_dvfs.h:20`), word 3 = timer or 0 |
| Level | 1959000 kHz | this phone's policy0 `cpuinfo_max_freq` and top `scaling_available_frequencies` entry (`artifacts/nat-171/policy0.txt`); stock holds it for ~70 s at every boot (`exynos-cpufreq.c:1343-1407`) |
| Voltage | not sent; the firmware applies its own table | the stock kernel never programs a CPU voltage (NAT-171 §3) |
| Reads | PLL_CPUCL0 `PLL_CON3` 0x1DC4010C; mailbox `INTMR1` | `cmucal-sfr.c:3166`; `acpm_ipc.c` |

No CMU, PLL or PMIC register is written by our kernel. The message is sent once, with no retry, and only if the PLL decodes and is
more than 1% below 1959000. The PMIC path of NAT-123 is unchanged; decision 0049's whitelist still applies.

## Image

loader-diag-xnu-scQ-md1 (NAT-172):
- RECOVERY `artifacts/nat-172/package-001/loader-diag-xnu-scQ-md1/recovery.img`, SHA-256 d73121352e1c538f013e8a3d09533c93aeeb304bde0186d1b6f6137179a01622 (100663296 bytes);
- payload c60622b9d5600c2dc5e9d22f33ba97250c45a9a74faf64b4a924dd755f8f73c2 (26206448 bytes at 2048);
- loader Image 42a001f50b8d47512a2012daac9a455d92f1a5cabba7f69aa93174db4362565c;
- kernel no-storage 5891f6aad205b453fffad7d32b5aeece715145d10dc5321e63910a1ef2fef352: NAT-169's objects, only `bsd/e1s_acpm.o` changed.

Loader sites check rc 0; relocscan 0 not allowed; command line 255 bytes, scO's with the tag changed.

Written only to RECOVERY /dev/block/sda18 with a full-hash readback before the single reboot
(`docs/procedures/nat-172/session_nat173.py`, 09154b46…861c). Stock restore SHA-256:
96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-172/cpuclk173.py` (SHA-256 dc4c09e36ac1f25d2912d69c1330fc29007262a0aa449550d65c07698452080f):
- **C2:** after-PLL within 1% of 1959000 and the add rate ≥ 1.5× the before rate: the clock was raised;
- **C1:** any other change;
- **C-same:** sent with error 0 but the PLL is unchanged (the firmware ignored it);
- **C-err:** non-zero error (e.g. 60 = no reply in 0.5 s);
- **C-skip:** no request, with the logged reason;
- **inconclusive:** no `e1s-cpuclk` line.

Also reported against NAT-170 (10.16/s, driver 17.89 ms, other 80.5 ms, 11.82 s per 1000 polls): `frames159`, `load166`,
`touch170`, the display verdicts, and whether the run reached the timed return.

## Risk, time limit, stop mechanism, restore

Same bounds as decisions 0063–0069: delivery cap 225 s, receive cap 240 s; timed return 270 s with the fed watchdog; loader
deadline 595 s → Download Mode; watcher and collector 720 s.

Specific risks:
- **The firmware hangs or rejects the request.** The transport waits at most 0.5 s and then continues.
- **The new clock is unstable.** The request carries a stock level that the firmware sequences with its own voltage table. If the
  kernel dies, the watchdog it feeds expires.
- **Heat.** There is no thermal loop. The run lasts ≤ 270 s on a little core at a level stock Android uses at every boot.

If the phone loops through SEC_UPLOAD (NAT-146):
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down and presses Volume Up for Download
   Mode;
3. the stock restore follows.

A reboot into Android re-initialises DVFS through its own driver (I). No partition other than RECOVERY is written, and iOS runs from
RAM. Restore: nat-012 `restore_stock.py` with the venv python; `check_android.py` and nat-013 assess; `task done` or
`task update` BEFORE the permission is closed. One attempt, no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
