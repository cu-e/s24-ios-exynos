# 0009: One native run of the NAT-022 `canary-plain` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code
session, in answer to the question "Разрешаете один нативный запуск
`canary-plain` (XNU-free, только цветные метки в framebuffer 0xFA200000) через
запись в RECOVERY?" with the choice "Да, один запуск canary-plain".

## Scope

Exactly one image: NAT-022 `canary-plain` (no XNU, no watchdog arming, no MMIO
except framebuffer stores), packaged into a RECOVERY image with the NAT-006
builder. Its SHA-256 is recorded in `artifacts/nat-022/package-001/package.json`
before any write. Sequence: full-hash write to RECOVERY (`/dev/block/sda18`) only,
full readback, one `adb reboot recovery`, owner-operated camera recording, then
restore of the pinned stock RECOVERY (NAT-021 path: `--restore` if Android
returns, otherwise physical Download Mode and one NAT-013 session).

## Not granted

Retries, `canary-fault`, `loader-diag`, XNU execution, any other partition, any
reset/data prompt answer, PMU/watchdog/MMIO access. Each needs a new decision.
The mandatory boundary of decision 0002 is unchanged: Android, apps, settings,
accounts and user data stay intact.

## Known limits disclosed

The image arms no watchdog; if S-Boot does not reset the phone the owner may
need the hardware key combination. Display scanout of 0xFA200000, pixel order,
stride and the AArch64 start path on silicon are unverified. A run without
visible markers is inconclusive, not a failure of the phone.
