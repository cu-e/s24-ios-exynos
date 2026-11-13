# Decision 0057: one NAT-142 run of loader-diag-xnu-scC-md1 (STM screen-on start + polled touch events)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044 and decision 0052.

## Owner consent

Decision 0052 (2026-11-13) is the owner's standing permission. It covers prepared single native experiments with touch, GPIO and
interrupts. It also covers temporary peripheral power through PMIC/ACPM on confirmed stock parameters, naming LDO9/LDO18:
"Разрешаю временные операции питания периферии через PMIC/ACPM только на подтверждённых штатных параметрах именно этого S24,
включая повторное включение LDO9/LDO18."

On 2026-11-14 the owner directed the work to touch and GPU: "2 задача тач и гпу перейди к ней". The rails are unchanged from decisions
0055 and 0056: LDO18 0x3d := 0xd8 (1.8 V) and LDO9 0x34 := 0xf0 (3.0 V), read back exactly on this phone in NAT-124 and NAT-140.

## New verifiable reason

NAT-140 passed: the STM answered its ID on the USI pins with both rails verified. Its next question is whether the controller starts
scanning and reports a finger. The commands are Samsung's own screen-on sequence for this phone, which Android sends every time the
screen turns on.

## Image

Image loader-diag-xnu-scC-md1, built by NAT-141:
- RECOVERY artifacts/nat-141/package-001/loader-diag-xnu-scC-md1/recovery.img,
  SHA-256 15b2d177cc0b3f061eec1a0064e3d1569a43b296ac2c8ca4a4ea4824da70b617 (100663296 bytes).
- Image.payload SHA-256 416826b3221355df31cc6daecb6ac82470e1011df8f33a56c76b149ad0348263 (26199088 bytes at offset 2048).
- Loader Image 1dd223ef88494ff0947c80ef0f627f5bb027d0099e1582f1bd9ec779106690e8. The engine is NAT-130's.
- Kernel 9213cff4b675bb22d08aa7ef696ec82d8e0bf61c6206cfd6da0c537d4ae85914. Only e1s_touch.o differs from NAT-140's kernel.
- Cmdline (246 bytes) as NAT-140's except the tag `nat_attempt=NAT141-scC`.
- Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
  (docs/procedures/nat-141/session_nat142.py).
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.
- Root artifacts/nat-083/system-padded.apfs, SHA-256 4377e98854753f648afde01d884bde352f316acad172eb5e46d44717954262f6.

## Changes against scB (NAT-140)

After an answered ID, and only then, the following run on the controller:
1. system reset `FA 20 00 00 24 81`;
2. READY wait (at most 150 reads, 20 ms apart);
3. `C0 62` (clear events);
4. scan mode `A0 00 01` with its echo wait;
5. `C0 10` (sense on).

After that, a kernel thread reads `87` every 10 ms and posts coordinates to /dev/hakios-touch.

One GPIO change: gpa1-2 pull goes to NONE, as in Android's `tsp_int_active`.

Not done: calibration, firmware update, flash writes, IRQ attach.

## Risk

These are the commands Android itself sends on every screen-on. Their effects are volatile: a power cycle or Android's own probe
re-initializes the controller. Android re-powers and re-probes the touch controller when it boots after the restore.

## Time limit, stop mechanism, restore

The bounds are NAT-140's:
- delivery cap 225 s;
- loader receive cap 240 s;
- kernel timed return 150 s with watchdog feed;
- loader deadline 475 s, then Download Mode (NAT-140: +490 s).

The event thread ends with the kernel's timed return.

Restore:
1. Run nat-012 restore_stock.py with the venv python.
2. Run check_android.py, then nat-013 assess.
3. Require boot_completed=1, SM-S921B/e1s/S921BXXS9BYH3, the stock RECOVERY hash and user-data directories.
4. Run `task done`/`update`, then close the permission.

One attempt only, with no retry without a new verifiable reason.

## Physical action asked of the owner

Touch and swipe the screen with one finger from about 1 min 45 s to about 4 min 30 s after the phone reboots (the moment the USB
connection to Android drops). In NAT-140 the touch thread's kernel lived from about +102 s to +250 s.

## Interpretation registered before the run

`docs/procedures/nat-141/analyze142.py` reports every NAT-140 verdict, plus:
- start S0/S1/S2/S3;
- events E0/E1, with counts and coordinates;
- reader R0/R1.

What follows from each outcome:
- E1 means a finger produced controller coordinate events in XNU, and they were posted to the node.
- That iOS acted on them needs a visible UI change and is not claimed from E1.
- E0 with S3 and no touch by the owner says only that the start sequence was accepted.
