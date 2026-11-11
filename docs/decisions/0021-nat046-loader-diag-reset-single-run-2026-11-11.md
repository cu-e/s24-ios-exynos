# 0021: One native run of loader-diag-reset (2026-11-11)

Status: recorded by `claude-nat046-20261111-session` under decision 0019 (owner full-automatic mode) before the run; no question was asked.
The owner's latest message (2026-11-11, Russian, as typed): "Телефон подключён, правило установлено, продолжай проверки можешь тестить на телефоне даю полные права"
("The phone is connected, the rule is installed, continue the checks, you may test on the phone, I give full rights"). The sentence about the
udev rule is not true on this host (`/etc/udev/rules.d` has only `51-android.rules`; `host_access.py --check` exits 2); this run does not use it.

## Scope

Exactly one image: `loader-diag-reset` (reset reason `0x12345601`, Download Mode request). The `-bl` image (`0x1234560d`) is not part of this
decision and needs its own file.

* RECOVERY SHA-256 `a3189ca7914b48b0b5d3a575c2936b6425bccdafde16e66c34fedf1f3d1ea34e` (100663296 bytes,
  `artifacts/nat-044/package-002/loader-diag-reset/recovery.img`, package record `package-002/package.json`).
* Packaged `Image.payload` (loader + XNU payload + ADT, as in runs 001-009) SHA-256
  `b79aeecc689c02c7a95ee487fb4a4b808ef8915292e0888122de9be983acaa14`, 21771872 bytes at offset 2048.
* Loader-only `Image` SHA-256 `24baf94e039be4869361706356005bc19aa891a2ce170332f8a6ab2f718635a1`.
* Built by NAT-044 (`artifacts/nat-044/build-002/build.json`, packaged by `docs/procedures/nat-044/package.py` after decision 0020), repository
  commit `9aa15ea` at the time of this decision. The image is the run-006 loader (NAT-020 build-003 + NAT-022 markers + NAT-027 aligned ADT +
  NAT-026 payload fix) plus the NAT-044 patch and the unmodified NAT-042 module (`s5e9945_reset.h`
  `05d7a85802cdceb59c2c168dc9ae8bf00b4edaf8c7f24bf9e113e233cc932352`, `s5e9945_reset.c`
  `6be65500f2e4661b80f70b73c0c2bb21d5797a38257c6ec0ecaef7fcf307b391`). The kernel is not started: the run ends in the loader's hold loop.

Sequence (the protocol of runs 001-009, driven by `docs/procedures/nat-048/session_reset_canary.py`): read-only preflight (device identity,
RECOVERY is `/dev/block/sda18` with unchanged stock hash, no remote `dd`, battery >= 50 % and < 42 C, no odin4/heimdall, host USB watcher
self-test); one-shot marker `artifacts/nat-048/native-attempt-loader-diag-reset-used.json`; full-image write to RECOVERY (`/dev/block/sda18`)
only; full SHA-256 readback; the host USB watcher (`usb_watch.py`, 240 s, fsynced JSONL, sysfs attributes only) started and confirmed logging;
one `adb reboot recovery` (T0); the run; then restore of the pinned stock RECOVERY (SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with `session_reset_canary.py --restore` if Android returns, otherwise with
the NAT-013 tool and the pyusb venv python on a device whose iProduct is `SAMSUNG USB` (never `SEC_UPLOAD`), followed by full-hash readback
and an Android check. Any failure after the write and before the reboot restores stock and does not reboot. No retry.

What the image does, in order: (1) the existing loader start, ADT/payload preparation and 83 s hardware watchdog arm of run 006; (2) at entry of
`recovery_guard()` it reads INFORM2/INFORM3/reboot-cmd of the PMU (0x12860000, offsets 0xb8, 0xbc, 0x190) and clears INFORM3 only if it holds
the Download (0x12345601) or Bootloader (0x1234560d) request; (3) it holds PRE_JUMP showing the markers of run 006 and the NAT-044 report frames
(kind 14); (4) 45 s after the watchdog was armed it draws the RESET stage frame (0x41) and calls `s5e_reset_to(PMU, 0x12345601)`: INFORM2 byte 2
:= 0x4e, INFORM3 := 0x12345601, reboot-cmd bits [2:0] := Download, each read back, then `0x3c00 := 2`. If a read-back differs nothing is triggered,
the result is drawn (kind 14, idx 7) and the hold continues to the watchdog. The reset is attempted at most once.

## Device access granted (and nothing else)

As in decision 0017 for the base image, plus the PMU window `0x12860000`: reads and writes at offsets 0xb8, 0xbc, 0x190 and 0x3c00 only. No
storage device and no partition other than RECOVERY is written. On the host side the run reads `/sys/bus/usb/devices` attributes and runs
`adb`; it opens no USB device node (NAT-013 restore excepted, as in runs 001-009).

## Pass/fail, fixed in advance

Observation is by the host only (USB enumeration with timestamps from `usb-events.jsonl`; display capture is optional and not required).
T0 = `reboot_requested_at` of the driver report. Deadline 45 s after the loader's own start (plus a few seconds), watchdog at about 83 s after
its arm. The rules are those of `docs/procedures/nat-048/analyze_reset.py` (split point 76 s for 45/83), applied without change:

* U1+U2 supported: the first return of a 04e8 device after it left the bus is between the deadline and the split point; the loader's PMU stores
  took effect and a reset without the ACPM STOP request works;
* U3/U4 supported: and that device is VID 04e8 iProduct `SAMSUNG USB` (Download Mode) without an owner action;
* U3/U4 refuted: a reset at the deadline but the host sees `SEC_UPLOAD`, an Android identity or nothing;
* U1/U2 refuted: no re-enumeration until the watchdog time (then `SEC_UPLOAD` at about +95 s as in runs 001-009);
* undetermined: no host observation, a log that does not cover 120 s after T0, or any other timing.

Any outcome is evidence; none is "return to Android is solved". A run with no host observation is inconclusive. Nothing is retried within the run.

## Not granted

Any other image or partition, a second run (the `-bl` image needs its own decision file), any other MMIO, the NAT-043 USB-log image, GPU
bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain changes. The boundary of decision 0002 is
unchanged: Android, apps, settings, accounts and user data stay intact. The registry `native` permission is set per this record and 0019 and
grants nothing beyond it.

## Known limits disclosed

* Source review + host/simulator tests only (NAT-042, NAT-044, NAT-048): the sequence is the vendor kernel's minus the ACPM STOP request (U2) and
  the cache flush; U1-U4 are open until this run.
* If the reset does not happen the 83 s hardware watchdog is the failsafe (runs 001-009: `SEC_UPLOAD` at about +95 s, gone at about +118 s). The
  phone may then come back to Android on its own (restore with `--restore`) or sit in an upload/Download state that needs the owner's hands; the
  restore is then done when the device is present and the interim state is recorded, not guessed around (decision 0019, point 5).
* The RESET marker is on screen for milliseconds before the reset: its absence on a recording is not evidence.
* `/sys/bus/usb/devices` showing Download Mode the way the fake tree in the NAT-048 tests does is an assumption this run tests. A second Samsung
  device on the host bus would be indistinguishable from the phone (the host has only this phone's 04e8 device attached now).
* RAM contents are volatile; nothing about the running Android is read or changed by the image.

## Owner confirmation (added before the run, 2026-11-11, after the 12:44Z refusal; the answer arrived about an hour later)

After the Claude Code auto-mode classifier refused the launch at 12:44Z (not retried or worked around), the owner was asked one narrowly scoped
question in the session, listing this image's hashes, the single RECOVERY write, the 45 s self-reset, the 83 s watchdog, the stock restore, that
data/apps/settings are untouched, and that an unplanned restart through SEC_UPLOAD had just happened on this phone (NAT-051, `clk_summary` read).
The owner answered (Russian, as selected): "Да, один запуск loader-diag-reset (Recommended)". This confirms exactly one run of this image and
nothing else; the "Not granted" list above is unchanged.
