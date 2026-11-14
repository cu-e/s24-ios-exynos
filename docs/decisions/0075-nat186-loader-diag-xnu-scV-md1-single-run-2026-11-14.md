# Decision 0075: one NAT-186 run of loader-diag-xnu-scV-md1 (per-process CPU-time sampler)

Date: 2026-11-14. Recorded by `claude-opus-usb130-20261113` under decision 0019, decision 0044, decision 0052 and decision 0061.
Decision 0061 covers bounded CPU, display and memory experiments, new kernels and images included, without a separate question. This
file is the per-image record that decision 0061 requires.

## Rationale and new verifiable reason

NAT-184 (K2) made the framebuffer driver 4× faster (2.16 ms per frame), but the share of 60-Hz frame intervals during the swipes stayed
at 56 %. What fills the only running core is unknown, because the existing `cpuload` idle counter reports never-started cores as
100 % busy. This run measures each process's CPU time during the swipes.

This is a new measurement: no image so far has carried a per-process sampler.

## What changes against NAT-184's image

- **Changed.** Only `bsd/e1s_display.o` (`docs/procedures/nat-185/e1s_display.patch`). It is NAT-176's read-only display snapshot plus
  a thread that, every 5 s from 200 to 380 s:
  - reads `recount_task_times()` of every process through `proc_iterate()` and cpu0's idle counter;
  - prints stamped `e1s-top:` lines.
- **Not touched.** No register access is added. Its only writes are its own static arrays.
- **Kept from NAT-184.** The run-table scaling, the swipe thread, `touch_lat=1` and the stock cpu0 FREQ_REQ of decision 0070.

## Image

loader-diag-xnu-scV-md1 (NAT-185):
- RECOVERY `artifacts/nat-185/package-001/loader-diag-xnu-scV-md1/recovery.img`, SHA-256
  57ab39447993b83b48e4afef2674ec0ead000de87f609729c9c9f01be907b27e (100663296 bytes);
- payload 117aafcc15c8e78e1c04707c1921a962bd680678cd3b3090ed0a8803943c7a88 (26208032 bytes at 2048);
- loader Image d38398ebb0bece791e441bfec28026a17eea4a421e1e3a5a592e575e90f1d704;
- kernel no-storage d7e7fee154104aaf9c59a4d2145c3901763259296ebd85cb373c388a4667c8b3: NAT-183's objects with
  `bsd/e1s_display.o` rebuilt.

Loader sites check rc 0; relocscan clean; command line 254 bytes (scU's with the tag `nat_attempt=NAT185-scV`).

Written only to RECOVERY /dev/block/sda18, with a full-hash readback before the single reboot
(`docs/procedures/nat-185/session_nat186.py`, ef8ee127ca0ed506efd9938bfe47378b81a3a25488743fdcaf5827eec1919823). Stock restore
SHA-256: 96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67.

## Observable criteria (registered before the run)

`docs/procedures/nat-185/top186.py` takes the median busy share over the swipe windows (spans ending 220–375 s):

| verdict | condition |
|---|---|
| U-none | no report line: inconclusive |
| U-sat | ≥ 0.90 |
| U-mid | 0.70 to below 0.90 |
| U-free | < 0.70 |

Reported beside it:
- the top processes and their shares, and the kernel's share;
- whether cpu0's idle counter agrees with span − busy;
- K (`fbcopy181`; it must stay about 2.2 ms), swipe175, dpp177, cpuclk173, touch170, frames159 and the display verdicts;
- whether the timed return was reached.

## Risk, time limit, stop mechanism, restore

The bounds are those of decisions 0063–0072:
- delivery cap 225 s, receive cap 240 s;
- timed return at 270 s with the fed watchdog;
- loader deadline 595 s, then Download Mode;
- watcher and collector 720 s.

Specific risk: proc_iterate takes the process-list lock briefly every 5 s, and recount_task_times reads counters without a lock;
both are what task_info and the kernel's own exception tracer do. The host harness checked the arithmetic, the table overflow and the off
switch. If the kernel stops, the fed watchdog expires and the loader deadline or the SEC_UPLOAD procedure applies.

If the phone loops through SEC_UPLOAD (NAT-146):
1. the host does not deliver again;
2. the owner forces a restart (Volume Down + Side, 7–10 s), then holds Volume Up + Volume Down until the blue screen and presses
   Volume Up for Download Mode;
3. the stock restore follows.

No partition other than RECOVERY is written. Restore: nat-012 `restore_stock.py` with the venv python, then `check_android.py` and
nat-013 assess. `task done` or `task update` comes BEFORE the permission is closed. One attempt, and no retry without a new verifiable
reason.

## Physical action asked of the owner

None, unless the SEC_UPLOAD loop above happens. Please do not touch the screen.
