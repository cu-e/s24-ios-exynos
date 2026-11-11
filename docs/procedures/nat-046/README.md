# NAT-046: first native run of the reset canary `loader-diag-reset`, observed only by the host (native-device)

Evidence category: **native-device** (one run on this SM-S921B, RECOVERY only), decided under decision 0019 and recorded in
`docs/decisions/0021-nat046-loader-diag-reset-single-run-2026-11-11.md` before the run. The run is the first one in which the computer, not a camera,
recorded what the phone did. Date 2026-11-11.

## What ran

* Auto mode refused the launch at 12:44Z; it was not retried or worked around. The owner then answered one question naming the image and its hashes
  ("Да, один запуск loader-diag-reset"); this is appended to decision 0021 before the run.
* `session_reset_canary.py --image loader-diag-reset --execute` (NAT-048 driver) at 14:03Z: gates passed (decision file, pins, device checks:
  SM-S921B/e1s/S921BXXS9BYH3, RECOVERY = `/dev/block/sda18` with the stock hash, battery 79 % / 29.6 C), watcher self-test, one-shot marker, full-image
  write to RECOVERY, readback SHA-256 `a3189ca7…ea34e` = candidate, watcher started and logging, one `adb reboot recovery` at **T0 = 14:03:36.854Z**.
* The host watcher (`usb_watch.py`, sysfs attributes only, 10 Hz, 240 s) recorded; `analyze_reset.py` applied the rules fixed in the decision file.

## Observation (host, `run-001-usb-events.jsonl`)

| dt after T0 | event |
|---|---|
| -0.1 s | watcher `start`, phone present as `04e8:6860` (Android) on port 5-1 |
| +3.6 s | `04e8:6860` disappears (the baseline of runs 001-009 was +4 s) |
| **+73.0 s** | **`04e8:685d`, product `SAMSUNG USB` (Download Mode) appears on 5-1** — no owner action, no `SEC_UPLOAD` |
| +240 s | watcher stop; the device was still present in Download Mode |

Baseline (runs 001-009, loader reaching its 83 s watchdog): `SEC_UPLOAD` at about +95 s, gone at about +118 s, and Download Mode only by the owner's keys.

## Verdicts (the rules of decision 0021 / `analyze_reset.py`, not changed after the run)

* **U1+U2: supported.** The re-enumeration at +73.0 s lies after the 45 s deadline and before the 76 s split point to the watchdog path (+95 s): the
  loader's PMU stores (INFORM2, INFORM3, reboot-cmd, `0x3c00 := 2`) took effect and a reset without the ACPM STOP request works on this phone.
* **U3/U4: supported.** After that reset the device enumerated as `SAMSUNG USB` (Download Mode) on its own, i.e. S-Boot honoured INFORM3 =
  `0x12345601` as the loader had left it. (`-bl`, the Bootloader word `0x1234560d`, was not run.)

How strong this is: one run. The margin to the split point is 3 s. The two facts that carry the verdict independently of that margin are that the
watchdog path of nine earlier runs produced `SEC_UPLOAD`, never `SAMSUNG USB`, and that Download Mode appeared about 22 s before the baseline upload time.
The log cannot say why the phone re-enumerated; it does not contain the loader's own read-backs (INFORM2/INFORM3/0x190 at entry were drawn on screen
only, and no display capture was made, which the task does not require). No second Samsung device was on the host's USB buses.

## Restore and Android check

Download Mode device bus 5 address 75 (iProduct `SAMSUNG USB`). One NAT-013 session with the pyusb venv python,
`restore_stock.py restore` 14:11:08Z-14:11:12Z: outcome `awaiting-readback`, 100663296 bytes acknowledged. Android came back by itself
(`sys.boot_completed=1`, user 0, user data directories present); `check_android.py`: RECOVERY full-hash readback = stock
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`, outcome pass; `restore_stock.py assess`: all six stages true, pass. Nothing
but RECOVERY was written; no setting, account or app was touched.

## What this changes

NAT-043 (first USB-log run) can now rely on the reset path: a loader that calls `s5e_reset_to(PMU, 0x12345601)` lands in Download Mode without hands,
which makes the NAT-013 restore unattended. NAT-043 still needs the udev rule for 1209:0001 (NAT-050, owner's root) and its own decision file.
Not established: the register state at loader entry (U1-U4 beyond the reset question), anything about the USB controller, and the `-bl` word.

## Files

`run-001-usb-events.jsonl`, `run-001-analysis.json`, `evidence.json`. Raw drivers' reports stay under `artifacts/nat-046/` (git-ignored).
