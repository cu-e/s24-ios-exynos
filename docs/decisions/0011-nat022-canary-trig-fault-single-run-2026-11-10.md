# 0011: One native run of the NAT-022 `canary-trig-fault` image (2026-11-10)

Status: accepted by the project owner (Egor) in the 2026-11-10 Claude Code session, in answer to a
question that named the canary Image SHA-256, the RECOVERY image SHA-256, the single difference from
the already-run `canary-trig`, the unchanged DECON0 accesses, the risks and the recovery path, with
the choice "Да, один запуск canary-trig-fault".

## Scope

Exactly one image: NAT-022 `canary-trig-fault`
(`artifacts/nat-022/build-003/canary-trig-fault/Image`, SHA-256
`f839ba305fae5e89c48642b422a827bc4993d491681560b2b20fd1a46b560a1b`, 49152 bytes), packaged with the
NAT-006 builder into the RECOVERY image SHA-256
`e7ab288fdd689dcb15c58cf92e19a96586b30ec3b85a6df09695d3b41772a735`
(`artifacts/nat-022/package-003/package.json`). Source commit `2e0e195`. It differs from the
`canary-trig` image of decision 0010 (`572ebd0f…`) by executing `BRK #0x1234` after the first report
round (about 19 s) so that the exception vector, exception stack and ESR/ELR/FAR/slot report are
exercised and shown on the display. Sequence: full-hash write to RECOVERY (`/dev/block/sda18`) only,
full readback, one `adb reboot recovery`, owner-operated camera recording, then restore of the pinned
stock RECOVERY (`session_trigfault.py --restore` if Android returns, otherwise Download Mode and one
NAT-013 session). Driver: `docs/procedures/nat-022/session_trigfault.py` with its own one-shot marker
`artifacts/nat-022/native-attempt-trigfault-used.json`.

## MMIO granted (and nothing else)

Identical to decision 0010: DECON0 main block `0x19100000`, only with the MMU off, only after the first
framebuffer marker is drawn, only when `GLOBAL_CON` shows DECON enabled and command mode, never after an
earlier kick faulted. Reads: `GLOBAL_CON` (0x20), `TRIG_CON` (0x30), `FRAME_COUNT` (0x04),
`SHD_REG_UP_REQ` (0x50). Writes: `TRIG_CON` (0x30) and `SHD_REG_UP_REQ` (0x50) in the vendor driver's
order. Framebuffer stores at `0xFA200000`. The exception loop may kick in the same way.

## Not granted

Retries, `loader-diag`, XNU execution, any other partition, any reset/data prompt answer, PMU/watchdog
access, any other MMIO. Each needs a new decision. The mandatory boundary of decision 0002 is
unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

The image arms no watchdog. In runs 001 and 002 S-Boot or the platform reset the phone about 90 s after
the reboot request (the display ended about 60 s after the first marker in run 002); the same is
expected here and the owner may need Download Mode. The `BRK`, the vector entry and the EL2
`ESR/ELR/FAR` reads are not host-testable and are exactly what this run tests. A run without a readable
exception report is inconclusive, not a failure of the phone.
