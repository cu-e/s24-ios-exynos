# NAT-091: native run of loader-diag-xnu-sa-md1 (decision 0035)

Status when this file was written (2026-11-12T16:15Z): **not run**.

* Preflight (all gates of `session_nat090.py`, no device write, no reboot): outcome `ready-read-only`; registry gate empty, RECOVERY readback equals the pinned stock (`96620b8b...`), battery level 84. Local record: `artifacts/nat-090/preflight-001/report.json`.
* First launch `--execute` at 2026-11-12T16:02:48Z (`artifacts/nat-090/run-001/report.json`): the driver's own device check `adb shell -T getprop sys.boot_completed` returned `error: closed`, the driver stopped with `outcome: stopped`, `device_write_started: false`, `reboot_sent: false`. The phone had left the host USB bus (no 04e8 or 1209 device for the next 10 minutes; why is not known: the owner may have taken it). The one-shot marker was not written, so decision 0035's single native attempt is **not consumed**. The `native` permit was closed again.
* This is not an experimental result and not a retry: nothing reached the phone. When the phone is back on adb, the run is launched once with a new `--out` (the old directory stays as a record).
