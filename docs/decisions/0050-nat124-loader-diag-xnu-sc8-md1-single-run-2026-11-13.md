# Decision 0050: one NAT-124 run of the NAT-123 touch-rail diagnostic

Date: 2026-11-13. Prepared under decision 0019, decision 0044 and the owner's
specific answer in decision 0049: "Yes, only LDO9/LDO18 at Android voltages".
This consumes that answer for one prepared run; it is not permission for
unbounded later PMIC experiments.

## Exact candidate and restore

- Image: `loader-diag-xnu-sc8-md1`.
- RECOVERY: `artifacts/nat-123/package-002/loader-diag-xnu-sc8-md1/recovery.img`,
  SHA-256 `09acac9f78749da81744c59e402e47dc1b84b09b87de20f4b06e0c33ef3168de`.
- Image.payload SHA-256 `3eebe5a342d71fcd897a75f8762a6793e57698455d584a4df2fcf8a94f268778`.
- Kernel SHA-256 `27c3f36984e67474badd43fe5d9c5eff22605d3b348c2f6138081c1def55c917`.
- Write only RECOVERY `/dev/block/sda18` (100663296 bytes), full hash readback.
- Restore from `devices/recovery/backups/2026-11-10/recovery.img`, SHA-256
  `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`.
- Driver: `docs/procedures/nat-123/session_nat123.py`, counted derivation from
  NAT-122's unchanged execution body. One-shot marker is in `artifacts/nat-124`.

## Changes and bounded hardware effects

NAT-122 saw no touch-chip response and could not use ACPM. Correct the double
base in the SRAM channel descriptor and PMIC block 0x1d -> PM1 0x05.
Validate queue pointers, type and size before use. Send the normal Samsung
SPMI MFD reads through ACPM channel 2, SID 0x0d. Require COM revision 0x01,
measured read-only in Android at `/sys/class/sec/ap_pmic/pmic_id` on this phone.
This revision comparison is a diagnostic sanity check, not cryptographic identity.

Only PM1 LDO18_CTRL 0x3d -> 0xd8 (1.8 V) and LDO9_CTRL 0x34 -> 0xf0 (3.0 V)
are permitted writes by the transport itself. Masked updates return EINVAL.
Read both rails before enabling. Set I/O before analog. Read back each write;
any error or mismatch prevents proceeding to the second rail. Already-enabled
unexpected voltage is refused rather than adjusted. No panel, charger, buck,
reset, RTC, firmware-flash or other PMIC writes. A failed readback does not
trigger an experimental rollback write; stop further writes and restore Android.

`e1spmic=2`; touch stage 3 is the compiled default (no extra token fits/needed).
Touch GPIO setup is NAT-121's mapped setup; additionally enable gpa1-2 low-level
EINT, attach the donor GIC SPI and start the bounded-by-kernel-window event
thread. Hardware IRQ and polling behavior have not been demonstrated on this
phone; interrupt routing and controller initialization remain hypotheses.
No touchscreen firmware update, calibration, persistent settings or flash commands.
Display/ADT/md0/md1 and deny-storage kernel stubs remain as NAT-121/NAT-119.

## Risks and stop conditions

A mistaken firmware layout or hardware map can hang/fault the native kernel.
Wrong regulator routing/enable behavior can cause power instability; the strict
write allowlist reduces scope, not proof of electrical safety. Readback proves
register state only, not measured rail voltage. GPIO contention/IRQ storms are
possible. Android/data preservation remains mandatory; evidence of instability
stops further device experimentation.

Keep the proven watchdog feed, 150-second kernel window (63-second fallback
without feed), 475-second loader deadline and Download Mode restore. Do not
repeat this image. No power-off, other partition, GPT/EFS/key/encryption change.
If Download Mode does not appear by ten minutes, request owner key action from
the existing recovery protocol and continue only independent host work.

## Restore and interpretation

Discover actual Download Mode bus/address, run `nat-012/restore_stock.py`,
then `check_android.py OUTPUT_JSON` and NAT-013 `assess`. Require stock RECOVERY
full-hash equality, boot_completed=1 and existing data directories. Close permit.

Pre-registered analyzer `nat-123/analyze124.py` reports power P0/P1/P2 separately
from the previous touch/display/window verdicts. Two exact readbacks plus success
are necessary for P2. Neither a reader open nor a response nor synthetic input
establishes physical iOS touch. Owner panel/touch observation is separate;
absence does not block host analysis. GPU acceleration and 60 FPS are not claimed.
