# Decision 0077: one NAT-190 run of loader-diag-xnu-scX-md1 (backboardd user-pc profiler)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers new images within the bounded experiments without a separate question. This file is the per-image record that
decision 0061 requires.

## Rationale and new verifiable reason

NAT-186 and NAT-188 established three facts:
- backboardd takes 76 % of the only core at about 68 ms of CPU per frame;
- Reduce Transparency and Reduce Motion do not change that;
- which code inside backboardd uses the time is unknown. No userland profiler existed.

NAT-189 adds a read-only kernel sampler of backboardd's saved user pc and lr. It is host-tested on a simulated kernel (11 OK, 7 mutants
killed). This image has never run before, and its question has never been asked: where in the shared cache backboardd spends its time.
The answer decides the next lever: a cheaper render path, a copy fix, or only SMP/GPU.

## What changes against NAT-186's image (scV)

- **Changed.** `bsd/e1s_display.o` only. It gains the `e1s-pc` sampler and loses NAT-176's `e1s-dpp` display-register snapshot.
- **The sampler reads only kernel memory.** It walks the process list and backboardd's threads, and reads `recount_thread_time_mach`,
  `get_user_regs` and the shared-region start. It does no MMIO, no copyin/copyout, and writes no thread state.
- **Less hardware access than NAT-186.** The removed snapshot was loads only; the snapshot's register maps are gone with it.
- **Unchanged.** The md0 root (NAT-110), every other driver, and the command line (tag `nat_attempt=NAT189-scX`).
- **Not touched.** Everything on the phone outside RAM, as before.

## Image

loader-diag-xnu-scX-md1 (NAT-189):
- RECOVERY `artifacts/nat-189/package-001/loader-diag-xnu-scX-md1/recovery.img`, SHA-256
  170f8c9374d50198bc656769b0d27066cd34e6e1e75240c2e6c7c059fab5dda5 (100663296 bytes);
- payload 03e586cca696f1c65740b003e22a843b8add841eee175957c832b591b5a78540 (26208816 bytes at 2048);
- loader Image c971e119eba796a9f37d1584b8045fd774d699e26e0e63ba2c19913ea2588a3f;
- kernel no-storage dc827310b3f4e2766b0ad2bcd25e43bda52f0b4bfe287fa968eccce787f9a0b9.

Loader sites check rc 0, with the same symbols as scV and every kernel segment the same size. The command line is 254 bytes.

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-189/session_nat190.py`, be64e14886fb35b37f5a955247c4cfa1b565010ac732bd8c57ea581f41a012db). Stock restore
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

The bounds are those of decisions 0063–0076:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

**Specific risk.** The sampler preempts backboardd 1000 times a second, so the frame rate may drop by about its `self` share (the
harness models 0.5 %). The thread walk holds backboardd's task lock for a few microseconds. If the sampler faulted, the kernel would
panic: the fed watchdog stops, and the loader deadline or the SEC_UPLOAD procedure applies.

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
