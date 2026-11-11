# Decision draft: one native run of `loader-diag-xnu-ckpt3-usb` (NAT-052) — NOT a decision, NOT requested

Status: **draft text only.** No decision number is assigned (0018 is reserved for the NAT-036 `loader-diag-xnu-ckpt3` image; the next free
number is taken when this is promoted). Nothing was asked of the owner and nothing was run. It is written in the form of
`docs/procedures/nat-047/decision-template.md` and decision 0022 so that, once its preconditions hold, the agent can copy it to
`docs/decisions/00NN-nat052-loader-diag-xnu-ckpt3-usb-single-run-<date>.md` (the glob a NAT-057 driver will look for), fill every `<...>`,
commit it before any device access and append the run-time owner confirmation as decision 0021/0022 did.

## Preconditions (a missing one means the file is not promoted and the run does not start)

1. **NAT-043 has a hardware verdict of PASS or PARTIAL that reached the collector**, i.e. the computer has received loader text/stage
   records over the NAT-041 engine from a real run. Without that, this image's only observation channel is untested and its extra value
   (kernel stops) is unobservable. This needs NAT-050 (the udev rule, owner's root) and NAT-043's own run-time confirmation first.
2. NAT-057 is done: a session driver and an analyser for this image, host-tested (gates, hashes, one-shot marker, restore, verdict rules
   below), derived from `docs/procedures/nat-049/session_usblog.py`.
3. NAT-046 is done (reset to Download Mode without owner action) — met (commit 1f00d5f).
4. The registry `native` permission is set by `lab.py project permit` citing the promoted file only when the run starts, and closed after.
5. The phone is attached, ADB works, battery above 50 % and below 42 C, nothing else on the host USB root hub used for the run.

## Scope

Exactly one image: `loader-diag-xnu-ckpt3-usb`.

* RECOVERY SHA-256 `a8161cccddb4282796a848b2c5b464d5457dcc0bb9bc2e0c1fa9cb1014967d97` (100663296 bytes,
  `artifacts/nat-052/package-002/loader-diag-xnu-ckpt3-usb/recovery.img`, 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT) SHA-256 `9d9cb972496807177771febf819d783f0823ecd2fb44fad2f9fadbfc3027440e`,
  21857888 bytes at offset 2048 (the ADT size field is 13960, aligned by the NAT-026 payload fix recorded in `build.json`).
* Loader-only `Image` SHA-256 `d9a630042097249bae7cb3be6a87cf64af01c78aebd38ac3911d04260728c18a` (303104 bytes).
* Built by `docs/procedures/nat-052/build.py` (`artifacts/nat-052/build-003/build.json`), packaged by NAT-044's `package.py` through
  NAT-047's wrapper (`artifacts/nat-052/package-002/package.json`), repository commit `<commit of NAT-052>`; `build-001` and `build-002` (before the
  dead depth counter was removed) were byte-identical to each other and are superseded by `build-003`.
* Sources: `patch_ckpt52.py` `732bcf9ec53b…`, `glue52.h` `ef4c55e9b45d…`, `glue52_impl.h` `2b11850d5972…` (full hashes in `build.json`, which
  the promoted file must quote in full); NAT-036 `ckpt3.c` `3232e8810945…`, `ckpt3_stub.S` `32ad7a8c0cea…`, `markerlib3.c` `e5d620c27593…`; NAT-047 `markerlib47.c` `97fac0a7f8c8…`, `usb47.h` `3d029820fa66…`; NAT-041 engine `usbmon.c` `37a53cbaa888…`; NAT-045 `ladder.c` `211413b8a72a…`, `ladder_usb.c` `eedec2487f83…`; and the unmodified NAT-042 reset module.
* Stop list: `11,30,31,32,33,34,35,12,40,41,42,43,44,13,14,15,16` (17 C stops) plus the five asm stops = 22 arrivals; the stub holds at
  checkpoint 16. NAT-044 deadline reset 60 s after the 83 s watchdog arm; service window 0.3 s per pass.

Sequence (the protocol of runs 001-009, NAT-046, NAT-043 and the NAT-049 driver): gates (this file, the registry, the udev rule,
collector self-test, device checks, watcher self-test); one-shot marker; full-image write to RECOVERY (`/dev/block/sda18`) only; full
readback; the USB event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running; one
`adb reboot recovery`; the run; then restore of the pinned stock RECOVERY (SHA-256
`96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose
iProduct is `SAMSUNG USB` (never `SEC_UPLOAD`), followed by full-hash readback and an Android check. A failure after the write and
before the reboot restores stock and does not reboot. No retry.

What the image does, in order: the run-006 loader start, ADT/payload preparation and 83 s watchdog arm; the NAT-045 ladder and the
NAT-041 engine bring-up as in NAT-043 (same MMIO table); the loader's VBAR is captured; the checkpoint installer (NAT-036) starts the XNU
kernel at its entry; at each of the 22 arrivals the stub installs the loader's vectors, queues one `CK ...` text record, polls the engine
for 0.3 s, restores the kernel's vectors and resumes the kernel; at checkpoint 16 it queues `HOLD stage=.. code=..`, keeps polling and
showing frames, and the NAT-044 reset follows at the deadline. Kernel code runs between stops with the engine unattended.

## Device access granted (and nothing else)

As in decision 0022 (NAT-043): the PMU window `0x12860000` (offsets 0xb8, 0xbc, 0x190, 0x3c00 and the `pd_hsi0` window `0x12862000`),
CMU_TOP `0x22b20000` reads, CMU_HSI0 `0x17800000`, SYSREG_HSI0 `0x17820000`, the USB control and PHY blocks `0x178a0000-0x178e0000` and
the DWC3 `0x17900000-0x1790ffff`, exactly as the 111-op table lists them — **none added** — plus what the kernel's own early boot code
touches up to checkpoint 16 as in decision 0017 (run 009). No storage device and no partition other than RECOVERY is written. On the host
side the run opens only USB 1209:0001 and reads `/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive `artifacts/nat-052/<attempt>/` and the USB event log); the camera is not used.
Rules are those of the NAT-057 analyser, which reads the archive through `decode52.progress`:

* PASS (kernel progress over the transport): one boot with this image's id; the loader log lines; the `CK` notes with consecutive `n`
  and no gaps in `progress()['gaps']`; the last note reached; either `HOLD stage=0x.. code=0x..` with the final mask bit
  (`reached_final`) or the exact last stop at which the notes ended; zero drop count.
* PARTIAL: the channel works (boot record and loader text) but the notes end before the final stop with no exception note — the last
  note names how far XNU got, and the missing next note is the finding; or notes with gaps (drops).
* EXCEPTION: a note with `esr/elr/far`: the kernel took an early exception; the values are the finding.
* FAIL: enumeration of VID 0x1209 but no readable record, or no enumeration although the loader ran; undetermined: no host observation.
* The return path is judged as in NAT-046; its failure does not change the log verdict. A result other than PASS is evidence, not a reason
  to run again.

## Not granted

Any other image or partition, a second run, the fault variants, MMIO beyond the above, ACPM/SMC calls, GPU bring-up, kexec, flashing
anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain changes, use of `sudo`/the udev rule by the agent. The boundary of
decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Source review and host/simulator tests only (NAT-036, NAT-041, NAT-045, NAT-047, NAT-052). The real DWC3 behaviour after a stretch
  with no polling (kernel running), the engine DMA coherence with the kernel's caches, the fixed 0.3 s service window and the time
  budget are untested on the S24. `docs/procedures/nat-052/README.md` lists them.
* NAT-051 (2026-11-11): a debugfs `clk_summary` read sent this phone through `SEC_UPLOAD` and an automatic restart; cause not established.
  If the loader or the kernel hangs the 83 s watchdog is the failsafe (SEC_UPLOAD, restart by itself after about 47 s in one observation).
* The kernel runs XNU early boot code under the loader's MMU-off stub with the loader's vectors only while serviced; an exception while the
  kernel's vectors are installed is not reported by this channel (the stub's early-exception path is).
* x0..x30 are not captured by the loader's exception vectors. A run with no host observation is inconclusive. RAM contents are volatile.

## Owner confirmation (added before the run)

`<to be added: one narrowly scoped question naming this image's hashes, the single RECOVERY write, the kernel start, the 60 s reset, the
83 s watchdog, the stock restore and that data/apps/settings are untouched; the owner's answer quoted>`.
