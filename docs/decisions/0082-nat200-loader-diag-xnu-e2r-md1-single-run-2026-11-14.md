# Decision 0082: one NAT-200 run of loader-diag-xnu-e2r-md1 (ten CPUs, SpringBoard's abort reason)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052, decision 0061 and
decision 0079. Decision 0061 covers new images within the bounded CPU experiments, including PSCI `CPU_ON` runs, without a separate
question. This file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-198 ran ten CPUs (S2-all). SpringBoard aborted twice there, with an uncaught Objective-C exception on a libdispatch thread, which
it does not do on one CPU. The text of that exception was in the 994 KB of the log that the transport does not deliver.

NAT-199 makes the kernel copy that text, read-only, into the message buffer, which arrives whole. Its reason is the proven obstacle
to a stable UI on several CPUs. The image has never run.

## What changes against e21 (NAT-198)

- **Changed.** One more object, `osfmk/user_exception_trace.o` (`docs/procedures/nat-199/user_exception_trace.patch`, additions
  only). 2 s after a user abort, a thread call reads the loader log in kernel memory. It prints each distinct
  `Terminating app due to uncaught exception` line and its first-throw stack line with `printf`.
  - It writes no register and no device.
  - It reads the log only.
  - The segments equal e21's, and the loader sites check is rc 0.
- **Unchanged.** Everything else, including:
  - the NAT-197 EL2→EL1 drop and the CPU_ON of cpu1–9;
  - the md0 root (NAT-110);
  - the command line, except the tag `nat_attempt=NAT199-e2r` (254 bytes).
- **Not touched.** Nothing on the phone outside RAM. No PMIC, clock or GPU change beyond scV's (cpu0 FREQ_REQ 1959000 kHz).

## Image

loader-diag-xnu-e2r-md1 (NAT-199):
- RECOVERY `artifacts/nat-199/package-001/loader-diag-xnu-e2r-md1/recovery.img`, SHA-256
  747f74e7a612f9502a3c248b154cbe302579d992b68b50a26a0d9e7f57c805de (100663296 bytes);
- payload bfc2914b00ce27cca966fa01fcc5a575c7d483a126da5c7de6cee11c0c3331e6 (26208400 bytes at 2048);
- kernel no-storage 320420f4e08ee2204f449f62c6a8585177f8caf8ce59d383915b741cfb78c6a3.

The image is written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot. The session driver is
`docs/procedures/nat-199/session_nat200.py`, SHA-256 eccf26acda1e7a885d713d5309009021817cc1ef7e464fe2f6ce1470dedd306b.

Stock restore SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-199/reason200.py` on the kernel text, first match:

| verdict | condition |
|---|---|
| R-no-abort | no abort line |
| R-none | abort lines, no `reason scan` line: inconclusive |
| R-reason | a `userabort: reason:` line, with exception name, reason and throw stack |
| R-abort-no-text | scan lines, but no reason line |

Reported beside it: `smp198` and the scV measures.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0081:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risk.** The NAT-198 configuration with ten CPUs ran to its timed return and Download Mode. The added code only reads
kernel memory and prints in a thread call. An unexpected fault there would be a kernel panic, which ends the run through the same
loader path.

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
