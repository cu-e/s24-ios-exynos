# 0016: One native run of the NAT-022 `loader-diag-xnu-ckpt` image (2026-11-11)

Status: accepted by the project owner (Egor) in the 2026-11-11 Claude Code session, in answer to a question
(asked in Russian) that named the reason for the new image (native run 007 of decision 0015 showed control
reaching the kernel copy's entry address, where only our own stub ran), what the new image does (the same
loader up to the full-window cache clean; instead of a stub at the kernel's entry it only fills the three zero
words after the `XNULDRST` magic in the kernel copy's `_loader_stub_slot`, after checking the slot and all five
NAT-029 assembly checkpoint sites word by word in the copy, and jumps to the kernel's own, unmodified entry; the
kernel stops itself at its assembly checkpoints and branches to a return stub in the loader image, which draws
the arrival, saves and restores every live register and the SP, resumes the kernel at checkpoints 1..4 and holds
at checkpoint 5), what it does not do (nothing after checkpoint 5, no `arm_init`, no GPU, no log transport, no
retry), the expected on-screen result, the loader `Image`, `Image.payload` and RECOVERY SHA-256s, the host checks
(NAT-031), the device access (as decisions 0013-0015), the new hazard (the kernel's own first instructions run
on the phone), what the model does not cover, the recovery path and the "Not granted" list, with the choice
"Да, один запуск loader-diag-xnu-ckpt".

This is the first image in which XNU instructions execute on the S24.

## Scope

Exactly one image: NAT-022 `loader-diag-xnu-ckpt`
(`artifacts/nat-031/build-002/loader-diag-xnu-ckpt/Image.payload`, SHA-256
`c8ee3a21aa620891da9c1a50da5c6279fe78015b1d8b09560a587f3947d2ed60`, 21775968 bytes; the loader `Image` is
`5d40d6238ea89642e82b097766398abc29205f43150e2eb4413d739d395f368e`, 221184 bytes; the SWEETXNU payload bytes are
those of run 007), packaged with the NAT-006 builder into the RECOVERY image SHA-256
`b17d0a8c2a25029cc71df874093707706862faf53c3138427b325d72d98d94c1`
(`artifacts/nat-031/package-001/package.json`, payload verbatim at offset 2048). Source commit `5c7d634`,
evidence record `docs/procedures/nat-022/evidence-nat031.json`. Sequence: full-hash write to RECOVERY
(`/dev/block/sda18`) only, full readback, one `adb reboot recovery`, owner-operated camera recording
(~2 minutes), then restore of the pinned stock RECOVERY (`session_xnu_ckpt.py --restore` if Android returns,
otherwise Download Mode and one NAT-013 session; stock SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`, backup
`devices/recovery/backups/2026-11-10/recovery.img`). Driver: `docs/procedures/nat-022/session_xnu_ckpt.py` with
its own one-shot marker `artifacts/nat-022/native-attempt-xnuckpt-used.json`.

Expected on screen if the kernel reaches its checkpoints: the stage markers up to `PRE_JUMP` (`0x40`, which is
not proof of anything beyond the loader), then four checkpoint passes (marker kind `CKPT` = 11, STAGE `0x51`)
with `x2:x3` = `0x0201`, `0x0202`, `0x0203`, `0x0204` and arrival masks `0x2`, `0x6`, `0xe`, `0x1e`, then the
held report with `0x0205`, mask `0x3e`, five arrivals, SCTLR_EL1 with M clear and VBAR_EL1
`0xfffffff007437000`. Other outcomes, none a failure of the phone and none retried: a held report after fewer
checkpoints (where the kernel stopped or the resume failed), mask bit 8 (the kernel's early-exception report:
ESR/ELR/FAR), `PRE_JUMP` followed by nothing (hang or fault without a report: inconclusive), or `FAIL` (the
installer refused; no jump was made).

## Device access granted (and nothing else)

Identical to decision 0015: DECON0 main block `0x19100000` (reads `GLOBAL_CON`, `TRIG_CON`, `FRAME_COUNT`,
`SHD_REG_UP_REQ`; writes `TRIG_CON` and `SHD_REG_UP_REQ` in the vendor driver's order; only with the MMU off,
only after the first marker, never after an earlier kick faulted), the framebuffer at `0xFA200000`, the PMU
INFORM register `0xbc` (`0x12860000`), the S5E9945 watchdog at `0x10040000` armed for 83 s, GIC initialisation
(`0x10200000`, `0x10240000`), and the loader's RAM work: zero the chosen window, copy the payload segments and the
ADT/`boot_args` into it, patch the ADT copy, clean data caches over the window. Changed by this decision, and
nothing else: the loader writes three 8-byte words of the slot in the kernel copy (and, at each checkpoint 1..4,
one word of it again) instead of a 40-byte stub at the entry; after the clean the handoff clears `SCTLR_EL1`
M/C/I, runs `ic iallu` and branches (`br x16`) to the kernel copy's own entry address; the kernel's start code
then runs on the phone up to its fifth assembly checkpoint (in the host model it touches EL1 system registers,
the TLB and caches, and RAM inside the loader's window only), and returns to the loader's stub through the slot.
No storage device and no partition other than RECOVERY is written.

## Not granted

Continuing the kernel past checkpoint 5 in any way, resuming at checkpoint 5, C checkpoints, retries, any other
image, any other partition, any reset/data prompt answer, any other MMIO. Each needs a new decision. The mandatory
boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Host evidence only (NAT-031, model NAT-030): the compiled aarch64 stub and installer run on the real kernel
  start code in an instruction-level model with no caches, TLB, exception model, timers, devices or SIMD. Not
  covered: whether the S24 behaves as the model at any checkpoint, instruction-fetch and I-cache coherence after the
  loader's clean and `ic iallu`, the real memory attributes of the window (data accesses with the MMU off are
  Device memory), alignment faults in the kernel's own start code, the kernel's exception path before and after it
  sets `VBAR_EL1`, `dc civac` on the slot line with real caches, whether the SIMD-using marker routines are safe at
  every stop, and the display budget (host harness: passes end at about 30 s, the first complete held report at
  about 63 s, display end at about 83 s).
* A checkpoint frame says the kernel's own instructions ran up to that point and the loader's return and resume
  worked; it says nothing about anything after `arm_init`'s start and does not say XNU boots.
* If the kernel hangs or faults without a report, the loader's watchdog fires or another fault occurs, the screen
  stays or goes dark on the last marker; that is where to look. Download Mode and one NAT-013 restore session may
  be needed, as after runs 1-7.
* A run without readable markers is inconclusive. RAM contents are volatile; the window zero does not touch
  storage.
