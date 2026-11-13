# Decision 0055: one NAT-137 run of loader-diag-xnu-scA-md1 (touch rails + bounded polling touch ID)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052.

## Owner consent

The owner's standing permission (decision 0052, 2026-11-13) covers temporary peripheral power operations through PMIC/ACPM on
confirmed stock parameters of this S24. It names LDO9/LDO18 explicitly. Verbatim: "Разрешаю временные операции питания периферии
через PMIC/ACPM только на подтверждённых штатных параметрах именно этого S24, включая повторное включение LDO9/LDO18."

On 2026-11-14 the owner directed the work to this line: "2 задача тач и гпу перейди к ней" (go to task 2: touch and GPU).

The values are the ones NAT-124 read back exactly on this phone (decision 0049: "Yes, only LDO9/LDO18 at Android voltages"):
- PM1 (SID 0x0d, block 0x05) LDO18_CTRL 0x3d := 0xd8, 1.8 V, touch I/O.
- LDO9_CTRL 0x34 := 0xf0, 3.0 V, touch AVDD.

## Image

Image loader-diag-xnu-scA-md1, built by NAT-129:
- RECOVERY artifacts/nat-129/package-001/loader-diag-xnu-scA-md1/recovery.img,
  SHA-256 a4809fe2704fe86b376016345ced17d669096483de892bc16c212735ce312826 (100663296 bytes).
- Image.payload SHA-256 332da1f8d464f11d19af19c9245947eae19001b88287aa1261501ffec0d9cbec (26199088 bytes at offset 2048).
- Loader Image e0aec56f286194283cb33b61e9d1869e474a8c56a7487e8f0e3ac9818d9f296b. The USB engine is NAT-130's, as in us1/NAT-132.
- Kernel NAT-128 kernel.no-storage d6d56001d32aadda5059ab0a2255b313d7ca2055da88d645d1610214bf284517.
- Cmdline (243 bytes): `rd=md1 e1sufs=0 ufs_write=0 nat_attempt=NAT129-scA debug=0xc serial=3 cpus=1 -v loader_return_after=150
  launchdsuffix=release cs_enforcement_disable=1 e1sbattery=0 rec_secs=150 rec_mb=64 e1s_wdt_pet=1 e1s_decon_hw=1 e1spmic=2 e1skeys=0 xrd=md0`.
- The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot (session_nat137.py,
  derived by derive137.py --check).
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
- Root artifacts/nat-083/system-padded.apfs, SHA-256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6.

## Changes against sc9 (NAT-127, the last run that restored userland and a visible home screen)

- **PMIC:** `e1spmic=2` enables only the two touch rails, through NAT-123's code. That code:
  - refuses on a chip ID other than 0x01;
  - pre-reads both rails and refuses if a rail is already on at an unexpected voltage;
  - reads back each write exactly, and stops at the first mismatch;
  - settles for 100 ms.
  No other regulator, buck or charger register is written.
- **Keys:** `e1skeys=0`. The key thread is not started, so there are no recurring PMIC power-key reads, which NAT-127 suspected of
  starving userland.
- **Touch:** the NAT-128 kernel makes three bounded read-only ID attempts (device ID C0 22 / D1, hardware ID FB 20 …, 50 ms apart).
  There is no IRQ, no event thread, no sense-on, no reset, no firmware, no calibration.
- **Base cmdline:** `e1sufs_probe=0` dropped. Its only reader returns on `e1sufs=0` first.
- **Loader:** the NAT-130 engine, as in NAT-132.

## Time limit, stop mechanism, restore

The bounds are sc9's:
- delivery cap 225 s;
- loader receive cap 240 s;
- kernel timed return 150 s with watchdog feed;
- loader deadline 475 s, then return to Download Mode. NAT-135 showed this also covers a stalled CPU.

Restore:
1. Run nat-012 restore_stock.py with the pyusb venv python.
2. Run check_android.py, then nat-013 assess.
3. Require boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, the full stock RECOVERY hash, and user-data directories present.
4. Close the native permission.

If Download Mode does not appear within ten minutes, the owner is asked for the key combination. This is one attempt, with no
retry without a new verifiable reason.

## Interpretation registered before the run

`docs/procedures/nat-129/analyze137.py` reads the kernel text and pixels:
- window and display as analyze124;
- power P0/P1/P2 from the rail readback lines;
- touch T0-fault / T0-no-poll / T1-no-response / T2-chip-answers;
- keys K0/K1.

Delivery numbers are reported as a repeat of NAT-132. T2 means only that the controller answered its ID. It is not touch input.
No input, acceleration or FPS claim follows from this run.
