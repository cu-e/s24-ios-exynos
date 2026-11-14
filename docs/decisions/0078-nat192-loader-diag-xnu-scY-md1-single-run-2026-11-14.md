# Decision 0078: one NAT-192 run of loader-diag-xnu-scY-md1 (backboardd user-pc profiler, NAT-190 assertion fixed)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers new images within the bounded experiments without a separate question. This file is the per-image record that
decision 0061 requires.

## Rationale and new verifiable reason

This is a rerun of the NAT-190 question: where in the shared cache backboardd spends its ~68 ms of CPU per frame. NAT-190 (decision 0077)
failed at 200.07 s with a kernel assertion. `recount_current_thread_time_mach()`, called for the sampler's own time, requires interrupts
off (`recount.c:567`), and the e1s DEVELOPMENT kernel checks it.

The new verifiable reason is that the cause is identified from the panic backtrace (`_e1s_pc_thread+0xac`) and fixed on the host:
- NAT-191 reads the self time with `recount_thread_time_mach(current_thread())`, which has no such precondition;
- the harness now aborts on `recount_current_*`, and NAT-189's patch reproduces the NAT-190 panic there;
- `nm -u` of the new object shows no `recount_current_*`;
- every other kernel interface the object calls was reviewed in the XNU 8796 source.

This is a new image (scY) and not a repeat of scX.

## What changes against NAT-190's image (scX)

- **Changed.** Only the three self-time calls in `bsd/e1s_display.o`.
- **The sampler reads only kernel memory.** It does no MMIO, no copyin or copyout, and no thread-state writes.
- **Less hardware access than NAT-186.** NAT-176's e1s-dpp register snapshot stays left out, as in scX.
- **Unchanged.** The md0 root (NAT-110) and the command line (tag `nat_attempt=NAT191-scY`).
- **Not touched.** Everything on the phone outside RAM.

## Image

loader-diag-xnu-scY-md1 (NAT-191):
- RECOVERY `artifacts/nat-191/package-001/loader-diag-xnu-scY-md1/recovery.img`, SHA-256
  cafc0d3329ffb90f66d77f580cffb6cf3ba279d270b96ed7361a707902b47885 (100663296 bytes);
- payload 89fcb733648766320269b55eeab475f7976e9405a7e68ad88e07a53af11cf1c3 (26208816 bytes at 2048);
- loader Image 928a93cabaec2dc1dafc20e32f77647022a45031736b2191c6c48ce2998df0ea;
- kernel no-storage dd2b9f3ffdd97263653664c8b4e13dbcf7587657adad6bf5333304f061c16886.

Loader sites check rc 0, with every kernel segment the same size as scV. The command line is 254 bytes.

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-191/session_nat192.py`, d1bda36aa98c63862278f341c5f16d68992d3ccf0f6fe4603c349b0918f594cd). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-189/pc190.py` reads the swipe windows (220–310 s):

| verdict | condition |
|---|---|
| P-none | no `e1s-pc` window line: inconclusive |
| P-thin | fewer than 2000 samples |
| P-ok | otherwise |

For P-ok the analyser reports:
- the coarse coverage;
- the group shares: copy, trap, ca, raster, runtime, other, outside;
- the leading group over the swipe windows and in the last window (310–375 s, where NAT-186 drifted into the Today view);
- the top images and functions from the fine and lr tables.

Reported beside it:
- the sampler's own cost (`self` µs per window);
- e1s-top's backboardd share and per-frame CPU against NAT-186 (67.95 ms);
- K, swipe175 and the display, touch and clock verdicts;
- whether the timed return was reached.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0077:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risk.** The sampler preempts backboardd 1000 times a second, so the frame rate may drop by about its `self` share (the
harness models 0.5 %). The thread walk holds backboardd's task lock for a few microseconds. If the sampler faulted or hit an assertion, the kernel
would panic as in NAT-190: the fed watchdog stops, and the loader deadline takes the phone to Download Mode (NAT-190 did this by itself), or the SEC_UPLOAD procedure applies.

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
