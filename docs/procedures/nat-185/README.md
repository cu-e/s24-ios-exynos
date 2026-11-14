# NAT-185: scV, a per-process CPU-time sampler on scU (host)

## Why

NAT-184 cut the framebuffer driver to 2.16 ms per frame (K2), 6.75 ms faster, yet the share of 60-Hz frame intervals during the swipes
stayed at 56 %. The limit is now userland, and no current image shows what fills the only running core. `cpuload`'s
`ml_cpu_idle_time` lines (NAT-166) reported every core, including nine that never started, as 100 % busy, so they cannot be trusted.

## What changed (one object)

`bsd/e1s_display.o` is now built from this directory's `e1s_display.patch`. It is NAT-176's display snapshot, unchanged, plus a
sampler:
- **What it reads.** Every 5 s from 200 to 380 s of uptime, it walks the process list (`proc_iterate(PROC_ALLPROCLIST)`) and reads each
  process's user + system time with `recount_task_times()`. Those are the lifetime counters `task_info` and `bsd_kern.c` read, without
  a lock. It also reads cpu0's idle counter (`ml_cpu_idle_time(0)`).
- **What it prints.** Stamped kernel lines, which survive the whole run:
  `e1s-top: S s span US us busy US us kernel US us idle0 US us procs N lost N` and
  `e1s-top: S s top name[pid] US ...`, the six busiest.
- **Limits.**
  - A process that exits inside a span is missing from it, and one born inside a span counts with its whole life.
  - At most 160 processes; more are counted as `lost`.
  - Time folded into the counters only at context switches may lag by one slice.
- **Off switch.** `e1stop=0`.
- **No registers.** It adds no register access: no `ml_io_map`, no volatile access and no `e1s_display_read` in the added lines.

Everything else is scU (NAT-183): the run-table scaling, swipes, `touch_lat=1` and the cpu0 FREQ_REQ. The command line is scU's with
the tag `nat_attempt=NAT185-scV`, still 254 B.

**Kernel** `artifacts/nat-185/kernel-001`:
- no-storage `d7e7fee154104aaf9c59a4d2145c3901763259296ebd85cb373c388a4667c8b3`, 0 undefined;
- the expect-string for the span line is present;
- `build.py` checks that it is NAT-183's record with only `bsd/e1s_display.o`'s patch replaced.

## Host checks

`python3 -B docs/procedures/nat-185/test_nat185.py`: 8 OK. The patched source is built against `host/shim185.h` and
`host/fake185.c`. The fake kernel has a simulated process table with fixed CPU shares, cpu0's idle counter at 20 %, and a simulated
clock.
- **Windows.** Exactly 205 … 375 s, every 5 s. Each span is about 5 s, busy is the sum of the live processes' shares, the kernel
  (pid 0) is 10 % and idle0 is 20 %.
- **Process birth and exit.**
  - A process born at 252.5 s counts with its 2.5 s of life in the 255 s span.
  - It is missing from the span in which it exits (300 s).
  - `procs` follows its life.
- **Top list.** Correct order and pids. Names are cut at 19 characters.
- **Overflow.** With 205 processes: `procs 160 lost 45`.
- **Off switch.** `e1stop=0` starts no thread and prints nothing. NAT-176's late snapshot still runs.
- **Mutants caught.** Four were tried, and all four fail the test: no subtraction of the previous total, the wrong pid for the kernel,
  reversed ordering, and a new process counted as 0.
- **Scope.** Against NAT-176's patched file no line is removed, and no added line maps or reads a register.
- **Analyser `top186.py`.** It gives U-mid on the harness, with SpringBoard first at 0.40. The boundary verdicts were also tested.
- **Build** `artifacts/nat-185/build-001`: loader sites rc 0 / ok / bad 0, relocscan clean, 254 B.
- **Package** `artifacts/nat-185/package-001`, image `loader-diag-xnu-scV-md1`: RECOVERY
  `57ab39447993b83b48e4afef2674ec0ead000de87f609729c9c9f01be907b27e`.
- **Session** `session_nat186.py` (ef8ee127…), derived by counted replacement from NAT-177's (`derive186.py --check`).

## Registered verdicts for NAT-186 (`top186.py`)

The verdict is the median busy share (sum ÷ span) over the swipe windows, the spans ending at 220–375 s.

| verdict | condition |
|---|---|
| U-none | no report line (inconclusive) |
| U-sat | ≥ 0.90: the core is full, so rendering is CPU-bound |
| U-mid | 0.70 to below 0.90 |
| U-free | < 0.70: the core has time left, so frames are paced late, not starved |

Reported beside it:
- the processes with the largest totals and their shares, and the kernel's share;
- whether cpu0's idle counter agrees with span − busy (which tests `ml_cpu_idle_time`);
- K (`fbcopy181`), swipe175, dpp177, cpuclk173, touch170 and the display verdicts.

## Not established here

Host evidence only. The real process mix and whether the counters behave on this port are what NAT-186 measures.
