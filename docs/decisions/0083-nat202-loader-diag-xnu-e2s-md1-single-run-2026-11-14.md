# Decision 0083: one NAT-202 run of loader-diag-xnu-e2s-md1 (ten CPUs, mediaserverd's fault)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052, decision 0061 and
decision 0079. Decision 0061 covers new images within the bounded CPU experiments, including PSCI `CPU_ON` runs, without a separate
question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-200 ran ten CPUs (S2-all) and recorded SpringBoard's SMP-only abort: `NSInternalInconsistencyException`, `Invalid parameter
not satisfying: routingContextUID`, thrown in MediaPlayer, called from MediaControls. The route context comes from the media
server. mediaserverd crashes with SIGSEGV in every run since NAT-118, and where it faults has never been recorded.

NAT-201 turns on the kernel's existing user-exception trace, which prints the faulting pc, lr, registers' texts and frames before
delivery. The image has never run.

## What changes against e2r (NAT-200)

- **Changed.** One data byte of the kernel: the default of `user_exception_trace_enabled`, 0 → 1
  (`docs/procedures/nat-201/user_exception_trace.patch`, NAT-199's patch with one line changed). The trace reads the faulting
  thread's saved registers and its own user stack (`copyin`, `copyinstr`) and prints.
  - It writes no register and no device.
  - The boot-arg `systrace` is not set, so the failed-system-call and exec traces stay off.
  - Every symbol and segment equals NAT-199's, and the loader sites check is rc 0.
- **Unchanged.** Everything else, including:
  - the NAT-197 EL2→EL1 drop and the CPU_ON of cpu1–9;
  - the NAT-199 abort-reason scan;
  - the md0 root (NAT-110);
  - the command line, except the tag `nat_attempt=NAT201-e2s` (254 bytes).
- **Not touched.** Nothing on the phone outside RAM. No PMIC, clock or GPU change beyond scV's (cpu0 FREQ_REQ 1959000 kHz).

## Image

loader-diag-xnu-e2s-md1 (NAT-201):
- RECOVERY `artifacts/nat-201/package-001/loader-diag-xnu-e2s-md1/recovery.img`, SHA-256
  9e21d2cb7a0b66f0c2ae151d70c431c21cdf6a9b233cc0b8b5d020332b0c1e17 (100663296 bytes);
- payload 3bf77cfecf5f6e60e96e9a341ba607bb9a397c0ddf212070a5b1af9a7d3812d8 (26208400 bytes at 2048);
- kernel no-storage dd5cbc7d9c6e58935b6bd1f3e0ad96632ad43bd174040c14d1c6b09e9861c07f.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot. The session driver is
`docs/procedures/nat-201/session_nat202.py`, SHA-256 4e565de9256aba8bd51e9b2a543f3e2b40d2f2b97ee2fd8a12a18686aa8e673b.

Stock restore SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-201/trap202.py` on the kernel text, first match:

| verdict | condition |
|---|---|
| T-none | no `usertrap:` line: inconclusive |
| T-other | `usertrap:` lines, none of mediaserverd's |
| T-media | a mediaserverd `usertrap:` line, with exception, codes, pc/lr, register texts and frames |

Reported beside it: `reason200`, `smp198` and the scV measures.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0081:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risk.** The e2r configuration with ten CPUs ran to its timed return and Download Mode (NAT-200). The trace runs in the faulting
thread's own context in `exception_triage_thread()`, preemptible, and reads user memory with the fault-safe `copyin`. Its output
is bounded by the crash rate (mediaserverd about every 5 s). An unexpected fault there would be a kernel panic, which ends the run
through the same loader path.

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
