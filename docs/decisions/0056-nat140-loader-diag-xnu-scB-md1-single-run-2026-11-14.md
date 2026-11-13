# Decision 0056: one NAT-140 run of loader-diag-xnu-scB-md1 (USI SPI9 pin map, MISO level check, 1 MiB kernel log ring)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052.

## Owner consent

The owner's standing permission (decision 0052, 2026-11-13) covers prepared single native experiments. It covers touch and GPIO among
the bounded peripheral experiments, and covers temporary peripheral power operations through PMIC/ACPM on confirmed stock parameters
of this S24, naming LDO9/LDO18. Verbatim: "Разрешаю временные операции питания периферии через PMIC/ACPM только на подтверждённых
штатных параметрах именно этого S24, включая повторное включение LDO9/LDO18."

On 2026-11-14 the owner directed the work to touch and GPU: "2 задача тач и гпу перейди к ней".

The rail values are unchanged from decision 0055 and were read back exactly on this phone in NAT-124:
- PM1 (SID 0x0d, block 0x05) LDO18_CTRL 0x3d := 0xd8, 1.8 V;
- LDO9_CTRL 0x34 := 0xf0, 3.0 V.

## New verifiable reason (no repeat of a failed run)

NAT-137 (scA) gave T1: poll 1 all 00, then all ff. NAT-139 found two things.
1. The driver's SPI9 map (CLK gpp9-2, MISO gpp9-0) came from a pin list that carries no signal order. The pinned DT's USI pad names
   imply CLK gpp9-0 and MISO gpp9-2:
   - uart1 rxd/tx/rts on pads 0/1/2;
   - hsi2c_18 SCL/SDA on gpp9-0/1;
   - hsi2c_19 on gpp9-2/3.

   Under that map, the old driver sampled an undriven pad, and NAT-139's pin-level host peer reproduces the phone's all-00 result.
2. The 128 KiB kernel log ring lost the PMIC readbacks. `msgbuf=1048576` keeps them.

This run changes exactly those two things.

## Image

Image loader-diag-xnu-scB-md1, built by NAT-139:
- RECOVERY artifacts/nat-139/package-001/loader-diag-xnu-scB-md1/recovery.img,
  SHA-256 e9aa908ea4c4edf1938e5722d296ce38fb711c6520607ba47c3713d9c6bce431 (100663296 bytes).
- Image.payload SHA-256 d26656ac2d0ae97fe5befdd8aa4fd2203e0a369d2a8b9307dbeb248cdf3d24a2 (26199088 bytes at offset 2048).
- Loader Image 55f6d3b92d89da3ee35de0f2b99ca2581eb038b98109ae7be568bb9f025d71c1. The USB engine is NAT-130's.
- Kernel NAT-139 kernel.no-storage b5483e1de76d7c734aefa80ae27e75f0f8292c5221ddf6baa10e664f4e541617. Only e1s_touch.o differs from
  the NAT-128 kernel that scA ran.
- Cmdline (246 bytes): `rd=md1 e1sufs=0 nat_attempt=NAT139-scB debug=0xc serial=3 cpus=1 -v loader_return_after=150
  launchdsuffix=release cs_enforcement_disable=1 e1sbattery=0 rec_secs=150 rec_mb=64 e1s_wdt_pet=1 e1s_decon_hw=1 e1spmic=2
  e1skeys=0 msgbuf=1048576 xrd=md0`.
- The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
  (docs/procedures/nat-139/session_nat140.py, derived by derive140.py --check).
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
- Root artifacts/nat-083/system-padded.apfs, SHA-256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6.

## Changes against scA (NAT-137)

- **Touch pins:**
  - CLK gpp9-0, MOSI gpp9-1, MISO gpp9-2 (input, pull NONE), CS gpp9-3.
  - The same three bounded read-only ID polls (C0 22 / D1 …, FB 20 …).
  - New: one MISO read with CS high, then CS low for two half-bit delays without a clock edge, a MISO read, and CS high.
  - No IRQ, event thread, reset, sense-on, firmware or calibration.
- **Kernel log:** `msgbuf=1048576` (XNU's own boot-arg, bounded at 1 MiB). `ufs_write=0` is removed; its only reader enables writes
  on `== 1` alone, the kernel is the no-storage build and `e1sufs=0` stays.
- **Unchanged:** PMIC (`e1spmic=2`, NAT-123 code: chip-ID check, pre-read, exact readbacks, stop at first mismatch), `e1skeys=0`,
  loader, engine, root and display path.

## Risk

If the USI map is wrong and the old map was right, pad 0 (the chip's MISO under that map) is driven as a clock while CS is low. The
same kind of drive conflict already happened in NAT-122, NAT-124 and NAT-137 under the opposite hypothesis. It is low-drive (DRV 0),
bounded (three polls, about 0.1 s), and ends when CS rises. No other new pin is driven.

## Time limit, stop mechanism, restore

The bounds are scA's:
- delivery cap 225 s;
- loader receive cap 240 s;
- kernel timed return 150 s with watchdog feed;
- loader deadline 475 s, then return to Download Mode (NAT-137: Download Mode at +494 s).

Restore:
1. Run nat-012 restore_stock.py with the pyusb venv python.
2. Run check_android.py, then nat-013 assess.
3. Require boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, the full stock RECOVERY hash, and user-data directories present.
4. Close the native permission after `task done`/`update`.

If Download Mode does not appear within ten minutes, the owner is asked for the key combination. This is one attempt, with no retry
without a new verifiable reason.

## Interpretation registered before the run

`docs/procedures/nat-139/analyze140.py`:
- every NAT-137 verdict;
- spi_map MAP-ok/MAP-missing;
- MISO levels;
- log L-pmic-kept/L-pmic-lost.

Outcomes:
- **T2:** the controller answered its ID on the USI map. It is not touch input.
- **T1 with L-pmic-kept and P2:** rails verified and no ID on either map. The next suspects are reset/boot timing and the SPI read
  framing, which are host work.
- **T1 with L-pmic-lost:** the log fix failed, which is inconclusive.

No input, acceleration or FPS claim follows from this run.
