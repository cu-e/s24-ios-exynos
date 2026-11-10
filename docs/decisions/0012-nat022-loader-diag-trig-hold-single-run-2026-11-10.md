# 0012: One native run of the NAT-022 `loader-diag-trig-hold` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code session, in answer to a
question that named the loader Image.payload SHA-256, the RECOVERY image SHA-256, the RECOVERY-only
write with full readback, the single `adb reboot recovery`, the stock restore, every device access of
the loader (DECON0 as in 0010/0011 plus PMU INFORM, the 83 s watchdog, GIC, RAM zero/copy/clean), the
fact that the image never jumps into the kernel copy, the risks and the recovery path, with the
choice "Да, один запуск loader-diag-trig-hold".

## Scope

Exactly one image: NAT-022 `loader-diag-trig-hold`
(`artifacts/nat-022/build-004/loader-diag-trig-hold/Image.payload`, SHA-256
`7c6206bd06923a91524afe95ec03573ed6fa680978cc839c40991debf7702cb3`, 21767776 bytes; the loader
`Image` is `901565b225c2137ebd99e4684cb4dc9a6b4f3ecf68632eedcf9ef8b16cf7db28`, 212992 bytes), packaged
with the NAT-006 builder into the RECOVERY image SHA-256
`511b4833f0b6c24f5adffe762451bcbf937aa9a23b64bdd41d254885e006c475`
(`artifacts/nat-022/package-004/package.json`). Source commit `82f636e`. It is the NAT-020 build-003
loader with stage markers (each stage redraws the bands, kicks DECON0 once and dwells 1.2 s) and a
hold in place of the jump: the held `PRE_JUMP` marker is a statement about the loader, not about XNU,
and the kernel copy is never entered. Sequence: full-hash write to RECOVERY (`/dev/block/sda18`) only,
full readback, one `adb reboot recovery`, owner-operated camera recording (~2 minutes), then restore of
the pinned stock RECOVERY (`session_loaderhold.py --restore` if Android returns, otherwise Download
Mode and one NAT-013 session). Driver: `docs/procedures/nat-022/session_loaderhold.py` with its own
one-shot marker `artifacts/nat-022/native-attempt-loaderhold-used.json`.

## Device access granted (and nothing else)

* DECON0 main block `0x19100000`, identical to decisions 0010/0011: only with the MMU off, only after
  the first framebuffer marker is drawn, only when `GLOBAL_CON` shows DECON enabled and command mode,
  never after an earlier kick faulted. Reads `GLOBAL_CON` (0x20), `TRIG_CON` (0x30), `FRAME_COUNT`
  (0x04), `SHD_REG_UP_REQ` (0x50); writes `TRIG_CON` (0x30) and `SHD_REG_UP_REQ` (0x50) in the vendor
  driver's order. Framebuffer stores at `0xFA200000`.
* What the NAT-020 loader does on its own, as in NAT-021 (decision 0008): read and possibly clear the
  PMU INFORM register `0xbc` (`0x12860000`); arm the S5E9945 watchdog at `0x10040000` for 83 s; GIC
  initialisation (`0x10200000` distributor, `0x10240000` redistributor); zero the RAM window it
  chose, copy the ~21 MB payload segments and the ADT/boot_args into it, and clean data caches over the
  window. No storage device and no partition other than RECOVERY is written.

## Not granted

Any jump into the kernel copy or execution of XNU code, retries, any other image, any other partition,
any reset/data prompt answer, any other MMIO. Each needs a new decision. The mandatory boundary of
decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

The loader arms an 83 s watchdog; a hold longer than that ends in a reset whose effect is part of what
is measured. In NAT-021 the same loader ended in a restart and `SEC_UPLOAD` about 110 s after the
reboot request, and the stock restore through Download Mode passed; that is a precedent, not a
guarantee. The display ended about 60 s after the first marker in runs 002 and 003, so late stages
(the full-window cache clean, `PRE_JUMP`) may not be visible; the stage mask carried by every frame
mitigates a missed frame, not a dark screen. The AArch64 start path, the loader's real DTB and RAM use
and the timing of the zero/copy/clean steps are not host-testable. A run without readable markers is
inconclusive, not a failure of the phone. The owner may need to enter Download Mode physically.
