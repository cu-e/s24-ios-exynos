# Decision text template: one native run of `loader-diag-usbmon` (NAT-043)

Not a decision. Under decision 0019 (owner full-automatic mode) the agent writes the decision file itself, as
`docs/decisions/00NN-nat043-<image>-single-run-<date>.md`, **before** the run, and commits it with the image build and package
records. Fill every `<...>`; delete nothing from "Not granted" or "Known limits". The protocol is that of runs 001-009
(decisions 0011-0017) and of NAT-046: only RECOVERY is written, the pinned stock RECOVERY is restored afterwards, full-hash
readback. Preconditions to check before writing it (a missing one means the file is not written and the run does not start):

* NAT-046 has a result and the loader's reset returned the phone to Download Mode (`SAMSUNG USB`) without an owner action, or the
  decision names another gated return path with evidence. Otherwise the run's only automatic exit is the watchdog and the
  return needs the owner's keys.
* NAT-039 is done (live USB stack of the running Android inventoried read-only) and the NAT-045 plan was cross-checked against it.
* The registry `native` permission was set with `lab.py` citing decision 0019 and this decision file.
* The phone is attached, ADB works, the battery is above 50 %, nothing else is plugged into the host's USB root hub used for the run.

```markdown
# 00NN: One native run of <loader-diag-usbmon | loader-diag-usbmon-fault> (<date>)

Status: recorded by the agent under decision 0019 (owner full-automatic mode) before the run; no question was asked.

## Scope
Exactly one image: `<image>`, RECOVERY SHA-256 <sha> (`artifacts/nat-047/package-001/<image>/recovery.img`), the packaged
`Image.payload` (loader + XNU payload + ADT) SHA-256 <sha> at offset 2048, loader-only `Image` SHA-256 <sha>, built by NAT-047
(`artifacts/nat-047/build-002/build.json`, packaged by `package.py`, source commit <sha>). The image is the NAT-044 reset canary
(run-006 loader family) plus the NAT-047 patch, the NAT-041 usbmon engine (<sha>), the NAT-045 ladder (<sha>) and the unmodified
NAT-042 reset module (<sha>). The kernel is not started: the run ends in the loader's hold loop and its reset at <deadline> s.

Sequence (the protocol of runs 001-009 and NAT-048's driver): full-hash write of the image to RECOVERY (`/dev/block/sda18`) only;
full readback; the collector `s24_logd.py` (pyusb venv python, `--provenance unqualified-live`) and the USB event watcher
started detached and confirmed running; one `adb reboot recovery`; one-shot marker <path>; the run; then restore of the pinned
stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb
venv python on a device whose iProduct is `SAMSUNG USB`.

What the image does, in order: the loader start and the 83 s watchdog arm of run 006; at `loader_main` the NAT-045 ladder rungs
L0-L2 (reads), then L3-L8 (writes to the HSI0 power-domain, clock, PHY and DWC3 registers listed in the NAT-045 plan
`docs/procedures/nat-040/plan.json`), the NAT-041 engine start (DWC3 at 0x17900000), a bounded wait of 3 s for the bus reset;
from then on the engine is polled from the loader's bounded loops; text, stages, the ladder report and (fault image) the
exception frame are served to the host collector over EP0 vendor control requests; the NAT-044 reset at <deadline> s.
<Fault image only: after the host configured the device, or after 8 s, the loader executes one `brk #0x1234`; the exception
path records the frame into the engine before drawing it.>

## Device access granted (and nothing else)
As in decision 0017 for the base image, the PMU window `0x12860000` (offsets 0xb8, 0xbc, 0x190, 0x3c00 only, NAT-044), plus the
HSI0 registers the NAT-045 plan names (<list from `build.json`/plan: registers and counts>). No storage device and no partition
other than RECOVERY is written.

## Pass/fail, fixed in advance
Observation is by the host only: the collector archive `artifacts/nat-043/<attempt>/` (frames, payload, usb-transfers) and the
USB event log; the camera is not used.
* PASS (transport): the archive holds one boot with the id of this image, the loader log lines in order, stage records and the
  ladder report, with a zero drop count and fsynced raw bytes; for the fault image also the exception frame with ESR
  `0xF2001234`.
* PARTIAL: the device enumerated as VID 0x1209 PID 0x0001 but fewer records arrived than the engine wrote (the archive states
  how many), or the ladder stopped at a rung (the report names the rung and the op).
* FAIL: no enumeration of VID 0x1209 although the loader was running (the host USB log and, if recorded, the screen status say
  how far it got), or enumeration with no readable record.
* Undetermined: no host observation or the host log does not cover the window.
The return path (reset at the deadline, then NAT-013 restore) is judged as in NAT-046; a failure of it does not change the log
verdict. Nothing is retried within the run.

## Not granted
Any other image or partition, a second run (the fault image needs its own decision file), HSI0 or other MMIO beyond the
list above, GPU bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset. The boundary of decision
0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed
* Source review + host/simulator tests only (NAT-041, NAT-045, NAT-047). The clock/PHY/PD sequence and the DMA/SMMU
  assumptions are untested on the S24; the HSI0 writes are the first writes to that block from this loader.
* If the ladder writes hang the bus the loader may stop; the watchdog is the failsafe and Download Mode may then need the
  owner's keys or a longer wait.
* x0..x30 are not captured by the loader's exception vectors; the exception frame has ESR, ELR, FAR, SPSR and SP only.
* A run with no host observation is inconclusive. RAM contents are volatile.
```
