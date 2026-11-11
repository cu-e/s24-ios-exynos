# 0023: One native run of loader-diag-usbmon-fault (2026-11-11)

Status: recorded by `claude-nat043-20261111-session` under decision 0019 (owner full-automatic mode) before the run. The file is committed before
any device access; an owner confirmation for the run itself is appended to it before the launch (the auto-mode classifier refuses an unconfirmed
native launch, see decisions 0021 and 0022). Nothing here is run until that confirmation is recorded.

## Preconditions checked when this file was written

* Decision 0022 / NAT-043 run 001 (commit 3e13f9c): the host collector received the messages of a real run of `loader-diag-usbmon` by itself:
  one boot, 148 frames, ladder summaries `err=0`, 0 drops, analyser PASS; stock RECOVERY restored in one NAT-013 session and Android verified.
  The HSI0 ladder, the DWC3 engine and the collector therefore work on this phone; this image repeats the same path and adds one controlled
  exception. The `native` permission is closed (false) and is set again, citing this file, only when the run is about to start.
* The udev rule for 1209:0001 is installed (`host_access.py --check` exit 0). NAT-039 and NAT-046 are done. Phone attached, battery above 50 %.

## Scope

Exactly one image: `loader-diag-usbmon-fault`. The non-fault image already had its single run (decision 0022); a second run of it is not part of this file.

* RECOVERY SHA-256 `f1a193dcac776dde004a3d1a379c26a4a365a150318bbc0a6501506ad7dfa103` (100663296 bytes,
  `artifacts/nat-047/package-001/loader-diag-usbmon-fault/recovery.img`).
* Packaged `Image.payload` (loader + XNU payload + ADT) SHA-256 `06281749f38bb6c8e944c3c82b4e77297b5749757e57b4d3c4d9f623b5025d77`, 21853792 bytes at offset 2048.
* Loader-only `Image` SHA-256 `2cb334cabd643c2f4d973e4cb5e8d46c562ea4c3e40093aa0d6cfb3a0f62d1e0`.
* The same NAT-047 build and package as decision 0022 (`artifacts/nat-047/build-002/build.json`), the NAT-044 reset canary plus the NAT-047 patch,
  the NAT-041 usbmon engine, the NAT-045 ladder and the NAT-042 reset module, compiled with `NAT047_FAULT=1`: its `package.json` records 19634 differing 4 KiB pages against the image of 0022 (RECOVERY `c6802dea4682...`); the spread of that
  difference over the container is not analysed here. The kernel is not started.

Sequence: the protocol of 0022 and of the NAT-049 driver `session_usblog.py --image loader-diag-usbmon-fault` (gates, one-shot marker, RECOVERY
`/dev/block/sda18` only, full readback, watcher and collector started detached and confirmed before the single `adb reboot recovery`, restore of
the pinned stock RECOVERY `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67` with the NAT-013 tool and the pyusb venv python on a
device whose iProduct is `SAMSUNG USB`, full-hash readback, Android check). No retry.

What the image does: as in 0022 (loader start, HSI0 ladder, engine bring-up, text and stage records), then in `nat047_hold` at stage
`MK_ST_PRE_JUMP` it waits up to 8 s for the host to configure the device and executes **one** `brk #0x1234` at the loader's own EL. The loader's
exception vectors write the exception record into the engine's exception frame before anything is drawn, and, by the NAT-047 design, the engine
keeps being polled (the exception loop draws and waits through `nat047_poll`) until the NAT-044 reset at 45 s; that design is untested on hardware. A BRK in the loader is a deliberate synchronous exception in code the loader itself runs; it does not touch XNU, memory
outside the loader or any register block beyond 0022's table.

## Device access granted (and nothing else)

Exactly the table of decision 0022 (PMU window `0x12860000` offsets 0xb8, 0xbc, 0x190, 0x3c00 and the `pd_hsi0` window `0x12862000`, CMU_TOP
`0x22b20000` reads, CMU_HSI0 `0x17800000`, SYSREG_HSI0 `0x17820000`, USB control and PHY `0x178a0000-0x178e0000`, DWC3 `0x17900000-0x1790ffff`, the
111-operation ladder table). No storage device and no partition other than RECOVERY is written. On the host side the run opens only USB 1209:0001
and reads `/sys/bus/usb/devices` attributes; the NAT-013 restore opens the Download Mode device as before.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive `artifacts/nat-043/<attempt>/` and the USB event log; no camera), with the rules of
`docs/procedures/nat-049/analyze_usblog.py` unchanged after the run. Coverage is shown, not assumed: watcher `start` and the collector's first
`poll` before the reboot, the collector's terminal status, and the raw files, as in the addendum of 0022.

* PASS: one boot with the id of this image, the loader log in order, stage records and the ladder report as in 0022, zero drops, **and** exactly one
  exception record with ESR `0xF2001234` (EC 0x3C, BRK imm 0x1234), an ELR inside the loader, FAR/SPSR/SP present, the engine's exception page
  (GET_EXC) agreeing with the ring's record, and the exception stage the last stage record.
* PARTIAL: the device enumerated and records arrived but the exception frame is missing, wrong or duplicated, or fewer records arrived than the
  engine wrote, or the ladder stopped at a rung.
* FAIL: no enumeration of 1209:0001 although the loader was running, or enumeration with no readable record.
* Undetermined: no host observation or a host log that does not cover the window.

USB return timing alone is never a message of the run. The return path (reset at 45 s, then NAT-013 restore) is judged as in NAT-046; its failure
does not change the log verdict. A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, HSI0 or other MMIO beyond the table above, the ACPM or any SMC call, GPU bring-up, kexec, flashing
anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain changes, and any use of the udev rule or of `sudo` by the agent. The
boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* One earlier hardware run (0022) only: the bring-up has worked once; repeatability is untested. Enumeration came at +26.8 s and the first
  pull at +26.9 s, so the 8 s CONFIGURED wait should be met, but that is an inference from one run.
* A deliberate exception on the real core is new on hardware: the loader's exception vectors and the engine's exception page have run only in
  the simulator. If the exception path faults the engine, the log is PARTIAL; the 83 s watchdog is the failsafe (SEC_UPLOAD and an automatic
  restart after about 47 s as on 2026-11-11, one observation), the 45 s deadline reset is the normal exit; Download Mode by keys is the fallback.
* x0..x30 are not captured by the loader's exception vectors. A run with no host observation is inconclusive. RAM contents are volatile.
