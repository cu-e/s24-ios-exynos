# 0017: One native run of the NAT-022 `loader-diag-xnu-ckpt2` image (2026-11-11)

Status: accepted by the project owner (Egor) in the 2026-11-11 Claude Code session, in answer to a question
(asked in Russian) that named the reason for the new image (native run 008 of decision 0016 showed the kernel's
own start code reaching assembly checkpoint 5 with four loader returns and resumes working, and stopping
there because the loader had no way to resume at 5), what the new image does (the same loader and the same
checkpoints 1..4 as run 008; at checkpoint 5 the loader writes `slot[2] = 11` with a cache-maintained store,
restores every live register and the SP and branches, MMU off, to the kernel's own MMU-enable block at
`site5 - 28`; the kernel enables its MMU again, runs its start code, `arm_init`, `cpu_data_init` and
`PE_init_platform` by itself and stops at its first C checkpoint 11, where a return stub with a prologue that
clears `SCTLR_EL1.M` and `C` before touching memory draws `x0`, `x1`, `x5`, `TTBR0_EL1` and the usual
SCTLR/TTBR1/VBAR/TCR block and holds), what it does not do (nothing after C checkpoint 11 and no resume from
it, no GPU, no log transport, no retry), the expected on-screen result, the loader `Image`, `Image.payload` and
RECOVERY SHA-256s, the host checks (NAT-033, NAT-034), the device access (as decisions 0013-0016), the new
hazard (kernel code after checkpoint 5 runs on the phone; a deviation can reach the kernel's panic path, whose
`psci_smp_stop_others` and `redwood_*_quiesce` callees were not analysed and may write device registers), what
the model does not cover, the recovery path and the "Not granted" list, with the choice
"Да, один запуск loader-diag-xnu-ckpt2 (Recommended)".

This is the first image in which XNU C code (beyond the assembly start code) executes on the S24.

## Scope

Exactly one image: NAT-022 `loader-diag-xnu-ckpt2`
(`artifacts/nat-034/build-001/loader-diag-xnu-ckpt2/Image.payload`, SHA-256
`27d5c0075d28bde69ee8a172d2cc34f4c3b98957d562ae1e7b70e914c8684a77`, 21784160 bytes; the loader `Image` is
`c27e1c66c381976edb32af89bc5574142ead55b115206b917793dece31d9f16e`, 229376 bytes; the SWEETXNU payload bytes
are those of run 007), packaged with the NAT-006 builder into the RECOVERY image SHA-256
`56f06e2582a4692f3f40d0d1ef3fb46633799fd9bc107e963d38731150961f59`
(`artifacts/nat-034/package-001/package.json`, payload verbatim at offset 2048, 19634 pages differ from stock).
Source commit `6c992d7`, evidence record `docs/procedures/nat-022/evidence-nat034.json`. Sequence: full-hash write
to RECOVERY (`/dev/block/sda18`) only, full readback, one `adb reboot recovery`, owner-operated camera recording
(~2 minutes), then restore of the pinned stock RECOVERY (`session_xnu_ckpt2.py --restore` if Android returns,
otherwise Download Mode and one NAT-013 session run with the pyusb venv python; stock SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`, backup
`devices/recovery/backups/2026-11-10/recovery.img`). Driver: `docs/procedures/nat-022/session_xnu_ckpt2.py` with
its own one-shot marker `artifacts/nat-022/native-attempt-xnuckpt2-used.json`.

Expected on screen if the kernel gets through: the stage markers up to `PRE_JUMP` (`0x40`), four checkpoint
passes as in run 008 (`0x0201`..`0x0204`, masks `0x2`, `0x6`, `0xe`, `0x1e`), a fifth pass for checkpoint 5
(`0x0205`, mask `0x3e`), then the held report of C checkpoint 11 (STAGE `0x51`, REGS `0x020b`, mask `0x83e`,
six arrivals, the eleven `CKPT2` frames carrying `x0`, `x1`, `x5` and `TTBR0_EL1`, SCTLR_EL1 with M set, TTBR1
`0x…9e15af000`-class, VBAR `0xfffffff007437000`, TCR low 32 bits `0xa51a251a`). Other outcomes, none a failure
of the phone and none retried: the held report at checkpoint 5 again (the resume did not leave 5), mask bit 8
(the kernel's early-exception report: ESR/ELR/FAR), bit 9 (`x2 = 0`: the kernel reached its own return path),
`PRE_JUMP` or `0x51` followed by nothing (hang or fault without a report: inconclusive), or `FAIL` (the
installer refused; no jump was made).

## Device access granted (and nothing else)

Identical to decision 0016: DECON0 main block `0x19100000` (reads `GLOBAL_CON`, `TRIG_CON`, `FRAME_COUNT`,
`SHD_REG_UP_REQ`; writes `TRIG_CON` and `SHD_REG_UP_REQ` in the vendor driver's order; only with the MMU off,
only after the first marker, never after an earlier kick faulted), the framebuffer at `0xFA200000`, the PMU
INFORM register `0xbc` (`0x12860000`), the S5E9945 watchdog at `0x10040000` armed for 83 s, GIC initialisation
(`0x10200000`, `0x10240000`), and the loader's RAM work: zero the chosen window, copy the payload segments and
the ADT/`boot_args` into it, patch the ADT copy, clean data caches over the window. Changed by this decision,
and nothing else: at checkpoint 5 the loader writes one 8-byte word of the slot in the kernel copy (`slot[2] =
11`, with `dc civac` before and after) and resumes the kernel at its MMU-enable block; the kernel's code then
runs on the phone past checkpoint 5 through `arm_init`, `cpu_data_init`, `PE_init_platform` and
`loader_checkpoint(11)` (in the host model it touches EL1 system registers, the TLB and caches, and RAM inside
the loader's window only, with no MMIO and no panic call), and enters the stub through `loader_jump`'s private
TTBR0 mapping; the stub's prologue clears `SCTLR_EL1.M` and `C`. No storage device and no partition other than
RECOVERY is written.

## Not granted

Anything after C checkpoint 11, resuming from a C checkpoint, retries or a second run, any other image, any
other partition, any reset/data prompt answer, any other MMIO, GPU bring-up, kexec. Each needs a new decision.
The mandatory boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay
intact.

## Known limits disclosed

* Host evidence only (NAT-033 model, NAT-034 tests): the compiled aarch64 stub runs on the real kernel code in
  an instruction-level model with no caches, TLB, exception model, timers or devices. Not covered: whether the
  S24 behaves as the model after checkpoint 5, cache coherence of the `slot[2]` write when the kernel reads it
  with its MMU on, the kernel's second MMU enable and TLB state after the MMU-off branch, exceptions and the
  kernel's own vectors, `boot_args` and ADT content as the loader really passes them, the SCTLR bit 5/7 cause,
  and the stub's placement against `loader_jump`'s private 2 MiB block (the prologue clears the MMU first either
  way). The harness display budget: the five passes end at about 35 s, `x0/x1/x5/TTBR0` are on screen once by
  about 52 s, one complete held report by about 78 s, the display ends at about 83 s.
* **The panic path was not analysed.** A fault or panic after the resume reaches `loader_return`, then
  `psci_smp_stop_others` and `redwood_*_quiesce`, which may access device registers. The model's path has none
  of these; the first of them seen on the path (`gic_v3_irq_quiesce`) returns early on a zero pointer. This is
  the new hazard and is disclosed, not mitigated.
* A report frame says the kernel's own code ran up to that point; it does not say XNU boots.
* If the kernel hangs or faults without a report, the loader's watchdog fires or another fault occurs, the screen
  stays or goes dark on the last marker; that is where to look. Download Mode and one NAT-013 restore session
  may be needed, as after runs 1-8.
* A run without readable markers is inconclusive. RAM contents are volatile; the window zero does not touch
  storage.
