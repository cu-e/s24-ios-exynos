# Decision 0080: one NAT-196 run of loader-diag-xnu-e2p-md1 (read-only EL2 probe on the started cores)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052, decision 0061 and
decision 0079. Decision 0061 covers new images within the bounded experiments without a separate question, including CPU runs that
start secondary cores with PSCI `CPU_ON`. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

The question is new: what EL2 state does the firmware leave on a core that PSCI `CPU_ON` starts?

NAT-153 established that the started cores enter at EL2 and stop after MMU-on, because XNU programs only EL1. NAT-153 did not read EL2.
This is roadmap piece S7, the read-only step before the EL2→EL1 drop (S8). The image has never run.

## What changes against the reference image (scV, NAT-185)

- **Changed.** `osfmk/start.o` only, from `docs/procedures/nat-195/start.patch` (NAT-152's patch plus the probe block).
- **The probe, on a started core that is at EL2:**
  - eight `mrs` reads: HCR_EL2, SCTLR_EL2, MDCR_EL2, VBAR_EL2, CNTHCTL_EL2, CNTVOFF_EL2, CPTR_EL2, ICC_SRE_EL2;
  - stores only into that core's own early-mark slot (kernel memory);
  - then PSCI CPU_OFF 0x84000002, the call `psci_smp.c` already makes;
  - a `wfe` loop only if CPU_OFF returns.
- **No system register is written.** That is host-tested: no `msr` in the patch or in the linked block.
- **Unchanged.** The boot CPU path, every other object, the md0 root (NAT-110) and the command line (tag `nat_attempt=NAT195-e2p`).
  The CPU_ON calls for cpu1–9 are the same as in every scV run (NAT-186, NAT-188).
- **Not touched.** Everything on the phone outside RAM.

## Image

loader-diag-xnu-e2p-md1 (NAT-195):
- RECOVERY `artifacts/nat-195/package-001/loader-diag-xnu-e2p-md1/recovery.img`, SHA-256
  ef99af4dabd107a96361b08a6efd6e1933b99ceeddd16899052d921b20e7366d (100663296 bytes);
- payload b736cb088ac99b571ea21bee7608b9b239bc44fa8c8dfbdbe90474249ba9d8d1 (26208032 bytes at 2048);
- loader Image 94712a03ff2990898fb71ddc3a39d9225d3a9f4d25f6793c16b3bfd3beb92a90;
- kernel no-storage ac5575501d10446ba41c62b1c97dac34613fe62d5490796d46df60db62fdd14b.

Loader sites check rc 0. Segments and the external symbol list equal scV's. The command line is 254 bytes.

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-195/session_nat196.py`, 3655d16814dd10e398e6f12f18041207b5a25607825478c161208ddcda556fce). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-195/e2p196.py` on the kernel text:

| verdict | condition |
|---|---|
| E-none | no early-marks line: inconclusive |
| E-noprobe | no core has stage word 0x5EC000E2 |
| E-partial | some started cores have it |
| E-ok | every started core has it |

Reported beside it:
- the decoded EL2 registers per core, and whether they are the same on all cores;
- AFFINITY_INFO (expected 1 after CPU_OFF);
- the boot CPU's run as in scV: home screen (display verdicts), fbcopy181 K, touch170, top186, cpuclk173, the timed return.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0078:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risk.** The boot CPU is unchanged, so an early failure before the watchdog feed is not expected. The secondaries now end by
CPU_OFF from EL2 instead of an exception at EL2. If CPU_OFF were refused, they would sit in `wfe`. The stop path then waits its 3 s and
reports "did not stop", as in NAT-153, and the loader reset follows.

**If the phone loops through SEC_UPLOAD (NAT-146):**
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s);
3. the owner holds Volume Up + Volume Down until the blue screen, then presses Volume Up for Download Mode;
4. the stock restore follows.

**Restore.** No partition other than RECOVERY is written. Restore with nat-012 `restore_stock.py` under the venv python, then run
`check_android.py` and the nat-013 assess. `task done` or `task update` comes BEFORE the permission is closed.

One attempt, and no retry without a new verifiable reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
