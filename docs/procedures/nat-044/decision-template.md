# Decision text template: one native run of `loader-diag-reset` (NAT-046)

Not a decision. Under decision 0019 (owner full-automatic mode) the agent writes the decision file itself, as
`docs/decisions/00NN-nat046-loader-diag-reset-single-run-<date>.md`, **before** the run, and commits it with the image build
record. Fill every `<...>`; delete nothing from "Not granted" or "Known limits". The protocol is that of runs 001-009
(decisions 0011-0017): only RECOVERY is written, the pinned stock RECOVERY is restored afterwards, full-hash readback.

```markdown
# 00NN: One native run of loader-diag-reset (<date>)

Status: recorded by the agent under decision 0019 (owner full-automatic mode) before the run; no question was asked.

## Scope
Exactly one image: `loader-diag-reset` (or `loader-diag-reset-bl` for the second, U4 run, only if the first showed a reset that
did not reach Download Mode), RECOVERY SHA-256 <sha> (`artifacts/nat-044/package-002/<image>/recovery.img`), the packaged
`Image.payload` (loader + XNU payload + ADT, as in runs 001-009) SHA-256 <sha> at offset 2048, loader-only `Image` SHA-256 <sha>, built by
NAT-044 (`artifacts/nat-044/<build>/build.json`, packaged by `package.py`, source commit <sha>). The image is the run-006 loader (NAT-020 build-003 +
NAT-022 markers + NAT-027 aligned ADT + NAT-026 payload fix) plus the NAT-044 patch and the unmodified NAT-042 module
(`s5e9945_reset.{h,c}` SHA-256 <sha>, <sha>). The kernel is not started: the run ends in the loader's hold loop.

Sequence (the protocol of runs 001-009): full-hash write of the image to RECOVERY (`/dev/block/sda18`) only; full readback; one
`adb reboot recovery`; one-shot marker <path>; the run; then restore of the pinned stock RECOVERY (SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device
whose iProduct is `SAMSUNG USB`.

What the image does, in order: (1) the existing loader start, ADT/payload preparation and 83 s hardware watchdog arm of run 006;
(2) at entry of `recovery_guard()` it reads INFORM2/INFORM3/reboot-cmd of the PMU (0x12860000, offsets 0xb8, 0xbc, 0x190) and
clears INFORM3 only if it holds the Download (0x12345601) or Bootloader (0x1234560d) request; (3) it holds PRE_JUMP showing the
markers of run 006 and the NAT-044 report frames (kind 14); (4) at <deadline> s after the watchdog was armed it draws the
RESET stage frame (0x41) and calls `s5e_reset_to(PMU, <reason>)`: INFORM2 byte 2 := 0x4e, INFORM3 := <reason>, reboot-cmd bits
[2:0] := <mode>, each read back, then `0x3c00 := 2`. If a read-back differs nothing is triggered, the result is drawn (kind 14,
idx 7) and the hold continues to the watchdog. The reset is attempted at most once.

## Device access granted (and nothing else)
As in decision 0017 for the base image, plus the PMU window `0x12860000`: reads and writes at offsets 0xb8, 0xbc, 0x190 and 0x3c00
only. No storage device and no partition other than RECOVERY is written.

## Pass/fail, fixed in advance
Observation is by the host only (USB enumeration with timestamps; display capture is optional). T0 = the moment the host sees
the device leave its previous state after `adb reboot recovery`; the loader's deadline is <deadline> s after its own start +
a few seconds; the watchdog would fire at about 83 s after the loader's arm.
* U1+U2 supported: the host sees a USB re-enumeration at the deadline (before the watchdog time) — the loader's PMU stores took
  effect and a reset without the ACPM STOP request works;
* U3/U4 supported: and the device enumerates as VID 04e8 iProduct `SAMSUNG USB` (Download Mode) without an owner action;
* U3/U4 refuted: a reset at the deadline but the host sees `SEC_UPLOAD`, a normal boot or nothing;
* U1/U2 refuted: no re-enumeration until the watchdog time (then `SEC_UPLOAD` at about +95 s as in runs 001-009);
* undetermined: no host observation, or the host log does not cover the window.
Any outcome is evidence; none is "return to Android is solved". Nothing is retried within the run.

## Not granted
Any other image or partition, a second run (the `-bl` image needs its own decision file), any other MMIO, GPU bring-up, kexec,
flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset. The boundary of decision 0002 is unchanged: Android, apps,
settings, accounts and user data stay intact.

## Known limits disclosed
* Source review + host/simulator tests only (NAT-042, NAT-044): the sequence is the vendor kernel's minus the ACPM STOP request
  (U2) and the cache flush; U1-U4 are open.
* If the reset does not happen the watchdog is the failsafe; Download Mode may then need the owner's keys or a longer wait.
* The RESET marker is on screen for milliseconds before the reset: its absence on a recording is not evidence.
* A run with no host observation is inconclusive. RAM contents are volatile.
```
