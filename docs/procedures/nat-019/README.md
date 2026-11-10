# NAT-019: requested timeout and log-channel preflight

2026-11-10. This is a host assessment with read-only Android/host interface
observations. No image or partition write or reboot was performed by this task.

The original request was 120 seconds. `preflight.py` builds the actual owned
watchdog implementation against host arrays under ASan/UBSan. Requests 30/83
succeed; 84/120 reject before changing any simulated register. At the cited
25.6MHz rate the maximum nominal expiry is 83.8848s; the integer API accepts at
most 83s. Header constants in the pinned BSP are counter0xffff, divider128 and
prescaler256. This does not calibrate live clock rate or expiry.

Primary source: [pinned watchdog driver](https://github.com/dx4m/android-kernel-samsung-e1s/blob/f85e53cfa5497ead5d78821efbac84e51f37a4e1/drivers/watchdog/s3c2410_wdt.c)
and its adjacent header. Local results are in
`artifacts/nat-019/preflight-001/probe/{range.json,commands.json,report.json}`.
The original 120s preflight intentionally exited2 (not ready), not a compiler/test
failure. The owner then explicitly selected **83 seconds and instructed start**.
The timer-range blocker is resolved for that amended request; it is not silently
rounded to a different interval.

Host USB inventory found the phone's Samsung Android enumeration with one ADB
interface (ff/42/01) and no ttyUSB/ttyACM devices. It does not establish the
existence or wiring of an onboard debug connector. Source inspection confirms
image-owned RAM logs and no native early UART transmitter; the project's USB
boundary performs no hardware I/O. No independent early console is qualified.
NAT-016's host recorder is not presented as an implemented native transmitter.

The existing payload cmdline did not specify RAM root or disable UFS. Source
inspection shows `e1s_ufs_probe` and root setup take `e1sufs=0`; legacy writes have
separate opt-in controls. A new candidate must not rely only on a root label:
its storage entry points and actual embedded bytes need explicit inspection.
No current claim that the saved kernel is safe to run unmodified is made.

Read-only Android check at 11:15:28Z passed: boot_completed=1, animation stopped,
model/firmware matched, user-data directories present, full RECOVERY hash matched
stock96620b8b…. No personal content was read. Reports are private under the run
directory. NAT-020 prepares the amended83s candidate and available diagnostics;
NAT-021 must separately record a single attended native attempt and return.
