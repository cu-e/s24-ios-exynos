# 0010: One native run of the NAT-022 `canary-trig` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code session,
in answer to a question that named the image SHA-256, the DECON0 reads and writes,
the risks and the recovery path, with the choice "Да, один запуск canary-trig".
It follows the owner's message "сделай и доведи чтобы работало, можешь в фоне опять
телефон перезапустить, я ещё раз поищу метки", which stated the intent but named no
image; this record is bound to the image below.

## Scope

Exactly one image: NAT-022 `canary-trig` (`artifacts/nat-022/build-002/canary-trig/Image`,
SHA-256 `572ebd0f33a03a7d07f663267301f97661f4e3f0051e0d9e8c3597b06385f89b`, 49152 bytes),
packaged with the NAT-006 builder into the RECOVERY image SHA-256
`f2cc234a70e7b4f54eb3469567d523233e70f486a220005cb36da47c00bcec64`
(`artifacts/nat-022/package-002/package.json`). Source commit `0a603a4`. Sequence: full-hash
write to RECOVERY (`/dev/block/sda18`) only, full readback, one `adb reboot recovery`,
owner-operated camera recording, then restore of the pinned stock RECOVERY
(`session_trig.py --restore` if Android returns, otherwise Download Mode and one NAT-013
session). Driver: `docs/procedures/nat-022/session_trig.py` with its own one-shot marker
`artifacts/nat-022/native-attempt-trig-used.json`.

## MMIO granted (and nothing else)

All at the DECON0 main block `0x19100000` (runtime FDT, UI-007), only with the MMU off, only
after the first framebuffer marker is drawn, only when `GLOBAL_CON` shows DECON enabled and
command mode, and never after an earlier kick faulted:

- reads: `GLOBAL_CON` (0x20), `TRIG_CON` (0x30), `FRAME_COUNT` (0x04), `SHD_REG_UP_REQ` (0x50);
- writes: `TRIG_CON` (0x30) and `SHD_REG_UP_REQ` (0x50), in the vendor driver's order
  (mask, global update request, unmask), alternating the HW-trigger and SW-trigger forms.

Source: `docs/procedures/nat-022/decon-trigger-facts.md` (pinned BSP `f85e53cf…`).
Framebuffer stores at `0xFA200000` as in decision 0009.

## Not granted

Retries, `canary-fault`, `loader-diag`, XNU execution, any other partition, any
reset/data prompt answer, PMU/watchdog access, any other MMIO (DPP, DSIM, SysMMU, clocks).
Each needs a new decision. The mandatory boundary of decision 0002 is unchanged: Android,
apps, settings, accounts and user data stay intact.

## Known limits disclosed

The image arms no watchdog; if S-Boot does not reset the phone the owner may need the hardware
key combination. An access to an unpowered DECON0 can hang the bus; the same S-Boot reset to
`SEC_UPLOAD` seen in run 001 (~95 s) is the expected symptom. That the image executes at all,
the DECON0 state at entry, TE presence, the window base and the SysMMU path are unverified. A
run without visible markers is inconclusive, not a failure of the phone.
