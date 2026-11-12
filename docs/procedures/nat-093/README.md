# NAT-093: Stage A re-run on the S24 (loader-diag-xnu-sb-md1)

Native-device run under decision 0036
(`docs/decisions/0036-nat092-loader-diag-xnu-sb-md1-single-run-2026-11-12.md`).
Outcome: **inconclusive** (pre-registered rows: chain row 9, Stage A row A8).
The task stays open; a non-pass outcome does not complete it.

## What ran

* Image `loader-diag-xnu-sb-md1` (built by NAT-092, `docs/procedures/nat-092/`),
  written once to the test RECOVERY slot, driven by `session_nat092.py`.
* Launch 2026-11-12 16:59:08Z, host 1-minute load average 3.89 (decision 0036
  condition: below 6, no agent build/test/mutation process).
* Restore with NAT-013 (pyusb venv python), `check_android.py` and `assess`
  both pass; the RECOVERY readback equals the pinned stock.

## Evidence levels (kept distinct)

| Level | Content |
| --- | --- |
| ran on the S24 | whole 2,475,720,704-byte root delivered (179.5 s, 13.79 MB/s, no device-side errors); kernel mounted it; init 35/35 checks; `df`, `mount`, `ps`, `vm_stat` printed; Apple's `lsd` ran as pid 21 under launchd and requested a CPU monitor above the kernel cap ~10 times a second |
| host analysis | pre-registered analysers `analyze_nat087.py` (chain row 9) and `analyze_nat089.py` (row A8, "no why=2 dump with text"), run unchanged |
| host analysis, post hoc | `posthoc_boot2.py` reads the surviving records of the collector's second boot; written after the result; **not a ladder row** |
| not shown | whether the seven self-starting Apple jobs ran, A1-A7, PID 1 survival, any UI |

## Why A8

The kernel text is in the collector's second boot (the loader after its timed
return). The producer reported two ring-overrun drops; 83 of the 428 records
(7,968 bytes) were lost, including the `KL begin` record. NAT-089's reader needs
`begin`, so it reports no dump.

## Post-hoc reading (`posthoc.json`, `kernel-text-excerpt.txt`)

* Dump length 170,097 bytes: an 8,192-byte head (complete) + a 32,768-byte tail
  (345 of its records present). The 129,137 bytes between them are not part of
  the dump format.
* The head ends inside rc's `vm_stat` output, before launchd's first line.
* The tail (kernel clock 254.10-276.66 s) is 235 repeats of
  `process lsd[21] denied attempt to escape CPU monitor (missing required
  entitlement).` plus the memory lines of pids 26 and 27 and one memory summary.
  The message is the printf in `osfmk/kern/task_policy.c`; the kernel clamps
  the request and goes on, so it is noise, not a fault, but it consumes the
  window.
* No panic line and no PID 1 exit line in the surviving tail: an absence in a
  window with holes, not a negative.

## Disclosures

* The post-hoc reader was written after the pre-registered analysers returned
  A8. No threshold or row definition changed.
* Another workload's Java process (170-240% of one core) ran on the host during
  the run.
* `artifacts/nat-092/run-001/kernel-log-boot2-posthoc.txt` contains the host
  user name (kernel text) and stays local; the committed excerpt is sanitized.

## Files

`task.json`, `evidence.json`, `posthoc_boot2.py`, `posthoc.json`,
`kernel-text-excerpt.txt`. Raw run artifacts stay under `artifacts/nat-092/`
(gitignored).
