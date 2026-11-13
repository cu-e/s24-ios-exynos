# Decision 0051: one NAT-127 sc9 display-recovery control

Date: 2026-11-13. Under decision 0019 and decision 0044, reiterated by the
owner's latest instruction to continue autonomously toward physical iOS UI,
input, Xclipse acceleration and sustained measured 60 FPS while preserving Android.
This run does not invoke the consumed PMIC-write permission of decision 0049.

## Image and boundary

Image loader-diag-xnu-sc9-md1, built by NAT-126:
- RECOVERY artifacts/nat-126/package-001/loader-diag-xnu-sc9-md1/recovery.img,
  SHA-256 0580150ea177ce4471d4461735af482664f1987a9b6238fca28d6ddc7f70b2cf.
- Image.payload SHA-256 99b18d7f23f9da8f16e0ad889990d686b252c1af7a71d07cffd6dc0b47a72fe6.
- Kernel a31e746c961beae19a58deef24a9e0df72e3764fd66478eb0e369b936eba485a
  (NAT-125 five-object rebuild, zero undefined symbols, 29 deny-storage stubs).
- Only RECOVERY /dev/block/sda18, 100663296 bytes; full-hash readback before reboot.
- Stock restore SHA-256 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67,
  devices/recovery/backups/2026-11-10/recovery.img.

## Hypothesis and exact changes

NAT-124 confirmed regulator state but recorded no new iOS frames or launchd
lines, unlike sc7. Two new execution paths were ACPM/power-key polling and the
unresponsive-controller low-level IRQ/event thread. This control removes both;
it cannot by itself isolate which caused regression.

Explicit e1spmic=0 returns before ACPM probe, PMIC reads or writes. No LDO,
charger, reset, RTC or other power-management transaction occurs. The existing
kernel contains the strict two-write allowlist, but that path is not entered.

NAT-125 sequences the STM ID transfer before printing its bytes and returns
without IRQ/thread setup when the controller does not respond. Only sc7's
mapped GPIO/SPI ID read then occurs in that case. If a nonzero/non-FF response
is seen, existing step-3 IRQ/event path remains possible; the assumption is
reported, not proof of controller identity. No scan-on/reset/firmware update.

NAT-119/121 display, no marker overdraw, product ADT and md0/md1 are unchanged.
Kernel command line remains below 256 bytes, serial=3, cpus=1, timed return 150 s,
watchdog feed with 63 s fallback, loader deadline 475 s. Restore from actual
Download Mode bus/address through nat-012, then check_android.py OUTPUT and
NAT-013 assess. Require boot_completed=1, expected model/firmware, full stock
RECOVERY hash and user-data directory presence; close native permission.

## Stop conditions / risk

One attempt only, no retry of sc9. Kernel GPIO/IRQ code may still fault or hang;
use existing timed return/watchdog/Download Mode restore. No writes to BOOT,
init_boot, vendor_boot, dtbo, vbmeta, super, USERDATA, GPT, EFS, keys or encryption;
no erase/unlock/reset. If Download Mode absent by ten minutes, request recovery
keys under existing protocol; stop experimental device actions on Android/data
risk. Owner observation is requested but never delays restoration.

## Interpretation registered before run

Run existing nat-123/analyze124.py plus nat-113/decode113.py. Require new iOS
frames/launchd evidence to restore the userland milestone, not mere nonzero
panel memory or DECON refresh. Physical visibility is a separate owner
observation. Touch, power, display and userland verdicts remain separate.
P0-no-verified-rails is expected with PMIC disabled, not an experiment failure.
No GPU acceleration or 60 FPS assertion follows from scanout or a new frame.
