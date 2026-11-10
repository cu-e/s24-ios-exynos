# NAT-021: one requested 83-second RECOVERY experiment, 2026-11-10

Owner: `codex-83s-session-20261110-r7`, primary checkout, branch `main`.
Decision: [0008](../../decisions/0008-single-83s-recovery-diagnostic-2026-11-10.md).
Candidate: NAT-020 build-003, SHA-256
`b5ff3bf7e4d6bcd36cc518fbc4ab0daaaf8a1985056a65708f60b51f4f9a6a49`.

At 11:35:58.923789 UTC, after writing and fully hashing the candidate RECOVERY,
the single `adb reboot recovery` was requested. ADB returned exit 0 at
11:36:02.686691 UTC. This proves command completion, not entry into the loader or
XNU. No second native reboot is permitted. The observation bound is 203 seconds
from the reboot request (11:39:21.923789 UTC), or an earlier stop condition.
The native result is **inconclusive**. Stock restoration and Android return
were verified afterward, as recorded below. No additional native attempt is
authorized by this session.

## Actual transfer

Android/root were available. The retired modified Odin4 was not used; it has
unqualified protocol changes and weakened checks. No Download Mode session was
opened. Instead, ADB streamed the fixed image directly to the validated block
device `/dev/block/sda18`, with no temporary image file on the phone. Its symlink,
block-device type, 100663296-byte size, original hash, model/firmware and completed
Android boot were checked first. Battery was 84%, temperature 30.2 C.

`session.py` fixes both permitted images, hashes, size and target. It uses an
exclusive host lock, refuses an existing remote `dd`, fsyncs the write and
requires a full matching partition hash before its sole recovery reboot. A
persistent attempt marker refuses a second native launch. Restoration mode
writes only the fixed original RECOVERY and never reboots. Seven host fault
controls cover successful ordering, wrong target, active writer, partial write,
readback mismatch, preflight, repeated launch and unknown reboot outcome.
These are host controls, not a hardware simulator.

## Rejected preparation, preserved separately

`attempt-001` did not reboot. Both its candidate transfer command and automatic
stock fallback were rejected with `dd: bad conv=nocreat,` before opening output.
An immediate read-only audit found no `dd` process, boot-completed Android and the
unchanged full stock RECOVERY hash. The phone's Toybox advertises `nocreat` in
help but actually rejects it. Syntax controls using a nonexistent input and no
output file proved `conv=notrunc,fsync` is accepted and `conv=nocreat` is rejected.

The rejected marker was preserved as `preopen-rejected-marker.json`, with its
assessment and original report/audit hashes; nothing was deleted or overwritten.
This allowed the corrected transfer in `attempt-002`, the **first and only actual
native boot**. The corrected command checks `test -b /dev/block/sda18` immediately
before `dd` instead of assuming `nocreat` support. The final command sequence is
in `artifacts/nat-021/attempt-002/report.json`.

## Logs and limits

Each host USB transition is an exclusive, fsynced event file under
`artifacts/nat-021/usb-attempt-002/`; the earlier observer remains separate.
Neither collector opens USB or records serial numbers. These are enumeration
observations, not native console messages. The loader's new stage/fault/drop
records remain in image RAM; native USB delivery, reset retention, watchdog
calibration and automatic Android return remain unqualified. No success claim
can be made without direct evidence.

Do not retry a failed or inconclusive native boot. Do not answer data/reset
prompts. At the stop condition, use the owner's physical Download Mode entry and
the fixed-stock NAT-013 tool, one session per fresh entry, if Android is absent.
If Android returns, `session.py --restore --out NEW` can restore only the pinned
stock image without rebooting. Finish with `check_android.py`, stock RECOVERY
hash and minimal user-environment metadata; do not inspect personal contents.

## Actual outcome and return

The owner observed only "Samsung Galaxy / Secured by Knox", followed by a
restart. No loader UI, native stage marker or kernel console was captured.
At 11:37:48.607738 UTC the host enumerated `SEC_UPLOAD`, 109.683949 seconds after
the reboot request. This elapsed time does not establish the watchdog's start
time, actual expiry interval, or whether XNU ran. No Odin command was sent to
`SEC_UPLOAD`. The session stopped and the owner physically entered ordinary
Download Mode, confirming "Downloading…"; sysfs independently showed the new
enumeration as `SAMSUNG USB` (bus 5, address 29).

The fixed-stock NAT-013 tool ran exactly one Odin session in that fresh entry,
11:39:11.247999–11:39:14.490666 UTC. It checked the exact measured PIT and target
(binary 0, UFS 8, identifier 18; start 75152, count 24576), uploaded all 96 MiB,
received EndSession 0 and normal-reboot 0, and returned `awaiting-readback`.
The unchanged stock image and its single-member tar were rehashed beforehand.

At 11:40:21.899634 UTC ADB observations established:

- SM-S921B/e1s, firmware S921BXXS9BYH3;
- `sys.boot_completed=1`, `init.svc.bootanim=stopped`;
- full RECOVERY SHA-256
  `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`;
- current user 0 and user/app directory availability without reading contents.

A further read at 11:40:58 UTC returned user state `RUNNING_UNLOCKED` and an
empty `/sys/fs/pstore`. The latest stock boot's `ro.boot.bootreason=recovery`
does not identify the earlier native crash. NAT-013's independent `assess`
combined every restore stage with the actual full readback and returned `pass`.
No other partition was targeted, and no reset/data-erasure action was selected.

All collected host records occupy separate directories/files. The native RAM
logs were not recovered; persistence across reset is unqualified. There is no
evidence that a host log file was overwritten. The exact native failure cannot
be distinguished among pre-loader/entry checks, guard, loader operations,
handoff and XNU from these records. Host builds and disassembly do not establish
which path this phone took. NAT-017's independently received early canary is
needed to resolve that gap. Its missing channel remains a blocker; no further
native boot is planned here. The temporary native-scope registry flag is being
returned to false after consuming this single session.

Local records: `artifacts/nat-021/attempt-002/report.json`,
`usb-attempt-002/`, `boot-log-assessment-001.json`,
`stock-restore-001/report.json`, `android-after-stock-001.json`,
`post-restore-diagnostics-001.json` and `stock-restore-assessment-001.json`.
The seven fault controls passed after correcting the flags; the final project
check is in `artifacts/nat-021/make-check.log`.
