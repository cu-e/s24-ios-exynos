# NAT-098: native run of `loader-diag-xnu-sq-md1` (decision 0037), the quiet Stage A image

Evidence kind **native-device**, outcome **inconclusive**. The task stays open. The one-shot marker
`artifacts/nat-096/native-attempt-loader-diag-xnu-sq-md1-used.json` exists; decision 0037 is consumed.

## What ran

`loader-diag-xnu-sq-md1` is NAT-092's image with exactly one change: the `com.apple.lsd` job is left out of the
small root. It ran once on the S24 on 2026-11-12 (reboot requested 18:07:32.851Z, host load 3.47 at launch),
RECOVERY slot only, restored from the pinned stock image (NAT-013, 18:14:07Z), Android checked (`check_android` pass,
`assess` pass: RECOVERY readback equals the stock hash, user-data directories present).

## Pre-registered result

| Analyser (unchanged) | Result |
| --- | --- |
| `analyze_nat087.py` (chain) | row 9, PARTIAL: two boots of the image in the archive, two producer drops, the kernel text is in the second boot (as in NAT-093) |
| `analyze_nat097.py` (Stage A ladder, reader v2) | **A8 not evaluated**: `no launchd line in the returned text`; the lost `KL begin` was inferred (length 111,842, 345 of 428 records, holes of 4,896 and 3,072 bytes, no conflicts) |
| `analyze_nat089.py` (reader v1) | A8: `no why=2 kernel-log dump with text in the archive` (it needs the begin line) |

A1 was the only pass. This is not one.

## What the run showed (post-hoc reading, outside the rows)

* The root arrived whole: 2,475,720,704 bytes in 179.2 s, 13.81 MB/s, no device errors.
* **The CPU-monitor flood is gone**: 0 of 304 timestamped lines (NAT-093: 235 of 243). The window is no longer one
  repeated message.
* The text is continuous from kernel clock 215.1 s to its last line at 268.5 s; the unsent middle and both holes lie
  before 216 s. A line missing in that range is missing from the kernel log.
* launchd ran the three boot tasks of NAT-088 and skipped 20; `Early boot complete` at 217.917 s.
* Eight processes (pids 9-16) were created in 22 ms (seven self-starting Apple jobs plus the heartbeat is eight);
  pids 17-25 followed, the last four 10.0 s apart. Apple's `logd` (pid 16) and `containermanagerd` (pid 12) are
  named by the kernel's minisandbox lines. No panic, no PID 1 exit line.
* Missing, unlike NAT-088: every launchd console-form line, `Unable to find persona with type 6`, `xpcproxy`, and
  every heartbeat `ps -A` list. So spawns and exits are invisible to the ladder, and which other daemons stayed up
  is still unknown. **Hypothesis H-logd (untested):** once `logd` runs, launchd's logging and the jobs' console
  output stop reaching the kernel log.

Full numbers, the per-item report required by decision 0037 and the disclosures are in `evidence.json`;
`kernel-text-excerpt.txt` is the sanitized excerpt (the full text contains the host user name and stays under
`artifacts/`).

## Evidence levels

| Level | State |
| --- | --- |
| code written | yes (images, drivers, analysers from NAT-096/097) |
| built | yes |
| checked in a model | yes (host tests of the image and readers) |
| ran on the S24 | yes: Apple's launchd, logd and containermanagerd ran; at least 17 processes were created |
| showed real iOS UI | no |

## Disclosed slip

The analysers were first run at about 18:15-18:17Z, before the collector had finished (its `manifest.json` was
written 18:17Z). They gave the same rows; the outputs are kept as `early-*`, and the rows above are from a rerun
after the collector and the USB watcher exited.

## Files

`task.json`, `evidence.json`, `kernel-text-excerpt.txt`, `README.md`.
