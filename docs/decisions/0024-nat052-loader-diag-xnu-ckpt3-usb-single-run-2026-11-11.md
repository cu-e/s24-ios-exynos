# 0024: One native run of loader-diag-xnu-ckpt3-usb (2026-11-11)

Status: recorded by `claude-nat057-20261111-session` under decision 0019 (owner full-automatic mode) before the run. The file is committed before
any device access; an owner confirmation for the run itself is appended to it before the launch (the auto-mode classifier refuses an unconfirmed
native launch, see decisions 0021-0023). Nothing here is run until that confirmation is recorded. Promoted from
`docs/procedures/nat-052/decision-draft.md`; the numbers and hashes below are those of the NAT-052 package-002 and build-003 records.

## Preconditions checked when this file was written

* The host computer has received the messages of two real native runs by itself (decisions 0022 and 0023, NAT-043 runs 001 and 002, evidence
  `docs/procedures/nat-043/evidence.json`, commit fa32ec6): the HSI0 ladder, the NAT-041 DWC3 engine and the NAT-041 collector work on this phone, 0 drops,
  one no-poll stretch of 7.19 s survived in both runs, the loader's controlled exception arrived. Those runs did not start the kernel.
* NAT-052 (the image, host-test, 68f21e0/54f245d) and NAT-057 (this run's driver `docs/procedures/nat-057/session_nat052.py` and analyser
  `analyze_nat052.py`, host-test) are done or are marked done in the commit that adds this file. NAT-039 and NAT-046 are done.
* **NAT-043 is `in_progress` in the registry**, not `done`: `task done` needs the `native` permission open and opening it only for bookkeeping was refused by
  the auto-mode classifier on 2026-11-11 (not retried). The NAT-057 driver requires NAT-043 `done`. The owner's confirmation below therefore includes
  one more step: after the owner's yes, in the same window in which `native` is set to true citing this file, the agent runs
  `lab.py task done NAT-043 --evidence docs/procedures/nat-043/evidence.json` and then the driver; `native` is set to false again once this run is over.
  Without that part of the confirmation the driver refuses to launch.
* The udev rule for 1209:0001 is installed (`host_access.py --check` exit 0). Phone attached on ADB, battery above 50 %.

## Scope

Exactly one image: `loader-diag-xnu-ckpt3-usb`.

* RECOVERY SHA-256 `a8161cccddb4282796a848b2c5b464d5457dcc0bb9bc2e0c1fa9cb1014967d97` (100663296 bytes,
  `artifacts/nat-052/package-002/loader-diag-xnu-ckpt3-usb/recovery.img`, 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT) SHA-256 `9d9cb972496807177771febf819d783f0823ecd2fb44fad2f9fadbfc3027440e`,
  21857888 bytes at offset 2048 (the ADT size field is 13960, aligned by the payload fix recorded in `build.json`).
* Loader-only `Image` SHA-256 `d9a630042097249bae7cb3be6a87cf64af01c78aebd38ac3911d04260728c18a` (303104 bytes).
* Built by `docs/procedures/nat-052/build.py` (`artifacts/nat-052/build-003/build.json`), packaged by NAT-047's wrapper of NAT-044's `package.py`
  (`artifacts/nat-052/package-002/package.json`). Sources (SHA-256): `patch_ckpt52.py` `732bcf9ec53b73687d10c1096966d1fc3e6c0e94d4e9c9417c98fe2fcde1d60f`,
  `glue52.h` `ef4c55e9b45d3e940eede78912f7c07169bfe8ffa73895e350859bf9842e2a9d`, `glue52_impl.h` `2b11850d5972f080ea938b3abbd6a6a66b34c47df4bcf9cedd15aaa7b5f8a192`;
  NAT-036 `ckpt3.c` `3232e8810945293e174022c0856a21049056d4da2ae0a7b8a7c462105794b436`, `ckpt3_stub.S` `32ad7a8c0ceab9d619c7e0aebceec9d166bbd1e971361104e6132ab9cb90c7d3`,
  `markerlib3.c` `e5d620c275930f4ead66d231c554395bd947e39632d5bb3cdec7c46dc1ba0dbc`; NAT-047 `markerlib47.c` `97fac0a7f8c8376ee4be37232cd35d468ef832463acda317d35ec2d3477feebc`,
  `usb47.h` `3d029820fa6680a53ef1297e96df442c297f4b4539e5cd5eb9e1ae0884cd54b1`; NAT-041 engine `usbmon.c` `37a53cbaa8887958107693f87e27e43c70b64a66ea791e10993d8f163fcdd205`;
  NAT-045 `ladder.c` `211413b8a72a74bff67389a44dd8abfe3a7808f4d1b43f7ffca0aa7474515877`, `ladder_usb.c` `eedec2487f831424c6d378a0072dc736cd5ad81ef9cdd3dd187a5a6cfe1b3dcf`.
* Stop list: the five assembly stops plus `11,30,31,32,33,34,35,12,40,41,42,43,44,13,14,15,16` (22 arrivals); the stub holds at checkpoint 16.
  Loader deadline reset 60 s, 83 s watchdog, engine service window 0.3 s per pass.

Sequence (the protocol of 0021-0023 and of the NAT-057 driver `session_nat052.py --image loader-diag-xnu-ckpt3-usb`): gates (this file naming both
hashes and decision 0019, the registry, the udev rule, the collector self-test, the device checks, the watcher self-test); one-shot marker
`artifacts/nat-057/native-attempt-loader-diag-xnu-ckpt3-usb-used.json`; full-image write to RECOVERY (`/dev/block/sda18`) only; full readback; the USB
event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running; one `adb reboot recovery`; the run; then restore of the
pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device
whose iProduct is `SAMSUNG USB` (never `SEC_UPLOAD`), full-hash readback and an Android check. A failure after the write and before the reboot restores stock
and does not reboot. No retry.

What the image does, in order: the loader as in 0022 (start, ADT/payload preparation, 83 s watchdog arm, the NAT-045 ladder and the NAT-041 engine bring-up with
the same MMIO table); the loader's VBAR is captured; the NAT-036 checkpoint installer starts the XNU kernel at its entry; at each of the 22 arrivals the stub
installs the loader's vectors, queues one `CK n=.. arr=.. last=.. ...` text record, polls the engine for 0.3 s, restores the kernel's vectors and resumes the
kernel; at checkpoint 16 it queues `HOLD stage=.. code=..`, keeps polling, and the reset follows at the deadline. **New on hardware:** XNU C code between
C checkpoint 11 (the furthest any hardware run reached, run 009 / decision 0017) and checkpoint 16 runs on the phone (nothing after checkpoint 16 runs: the stub
holds there, and NAT-036 refuses later stops because the kernel's `TTBR0` changes in `arm_vm_init`, NAT-035 section 2), with the engine unattended between stops; the loader's stub writes one 8-byte slot word per stop with cache maintenance and
restores the kernel's registers, SP and SCTLR as in the NAT-036 model.

## Device access granted (and nothing else)

The table of decision 0022 (PMU window `0x12860000` offsets 0xb8, 0xbc, 0x190, 0x3c00 and the `pd_hsi0` window `0x12862000`, CMU_TOP `0x22b20000` reads, CMU_HSI0
`0x17800000`, SYSREG_HSI0 `0x17820000`, USB control and PHY `0x178a0000-0x178e0000`, DWC3 `0x17900000-0x1790ffff`, the 111-operation ladder table) — **none added** —
plus what the kernel's own early boot code touches up to checkpoint 16 (as decision 0017 granted up to checkpoint 11: EL1 system registers, the TLB and caches, RAM
inside the loader's window). No storage device and no partition other than RECOVERY is written. On the host side the run opens only USB 1209:0001 and reads
`/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive under `artifacts/nat-057/` and the USB event log; no camera), judged by
`docs/procedures/nat-057/analyze_nat052.py` unchanged after the run. Coverage is shown, not assumed: watcher `start` and the collector's first `poll` before the reboot,
the collector's terminal status, and the raw files.

* PASS (kernel progress over the transport): one boot with this image's id and banner, the loader log and both ladder summaries `err=0`, the 22 `CK` notes `n=1..22` with the
  checkpoints this image has at each position and no gap, the final-stop bit at `n=22` (checkpoint 16) **and** the `HOLD` record, zero drops, nothing unread, no exception.
* PARTIAL: the channel works (boot record and loader text) but the notes end earlier or have gaps or the HOLD is missing: the last note names how far XNU got, and the
  missing next note is the finding.
* EXCEPTION: a note with `esr/elr/far` (the kernel's early exception) or a loader exception record: the values are the finding.
* FAIL: no enumeration of 1209:0001 although the loader ran, or enumeration with no readable record. Undetermined: no host observation or a host log that does not cover the window.

USB return timing alone is never a message of the run. The return path (reset at the deadline, then NAT-013 restore) is judged as in NAT-046; its failure does not change
the log verdict. A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, the fault variants, MMIO beyond the above, ACPM/SMC calls, GPU bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys,
erase/factory reset, boot chain changes, and any use of `sudo` or the udev rule by the agent. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts
and user data stay intact.

## Known limits disclosed

* Source review and host/simulator tests only for the kernel part (NAT-036, NAT-041, NAT-045, NAT-047, NAT-052, NAT-057). The real DWC3 behaviour after a stretch with no
  polling while the kernel runs (0022 and 0023 survived 7.19 s with the loader idle, not with a kernel running), the engine DMA coherence with the kernel's caches, the fixed
  0.3 s service window and the time budget are untested on the S24; `docs/procedures/nat-052/README.md` lists them.
* If the kernel or the loader hangs, the 83 s watchdog is the failsafe (`SEC_UPLOAD`, an automatic restart after about 47 s in the one observation of 2026-11-11);
  Download Mode by keys is the fallback. NAT-051: a debugfs `clk_summary` read once sent this phone through `SEC_UPLOAD`; never repeated.
* The kernel runs XNU early boot code under the loader's MMU-off stub with the loader's vectors only while serviced; an exception while the kernel's vectors are installed
  is reported only by the stub's early-exception path. x0..x30 are not captured by the loader's exception vectors. A run with no host observation is inconclusive.
  RAM contents are volatile. A pass frame says the kernel's code ran up to that checkpoint; it does not say XNU boots.
* NAT-043 `done` is recorded under this run's window (see the preconditions); that bookkeeping is not part of the device protocol.

## Owner confirmation of the run (recorded before the launch)

At 2026-11-11T17:18:04Z the owner answered the question "Запускаю ОДИН нативный запуск образа loader-diag-xnu-ckpt3-usb (решение 0024, коммит 7681f98), чтобы компьютер получил по USB
сообщения самого ядра XNU (22 контрольные точки)…" with "Да, один запуск loader-diag-xnu-ckpt3-usb (Recommended)". The question named the RECOVERY SHA-256 prefix `a8161ccc…7d97`
(full hash in this file), the only partition written (RECOVERY, `/dev/block/sda18`, full readback), the single `adb reboot recovery`, the same USB monitor 1209:0001 and the same
111-operation HSI0 table as NAT-043 (nothing new), the start of the XNU kernel with a short text record received at each of 22 stops, that the kernel passes for the first
time beyond C checkpoint 11 (to 16, not further) with USB unpolled between the stops, the reset into Download Mode after 60 s, the restore of the stock RECOVERY (`96620b8b…`,
full-hash readback) and the Android check, that data, apps and settings are untouched, one run and no retry, the risk (a hang of the kernel or loader: a partial log, the 83 s
watchdog with `SEC_UPLOAD` and an automatic restart after about 47 s as on 2026-11-11, or Download Mode by keys), and the bookkeeping step: because the driver requires NAT-043
`done` and `task done` is possible only with the `native` permission open, in the same window, after the answer, the agent opens `native` citing this file, marks NAT-043 done
(evidence already committed in fa32ec6), claims the run's task, runs the driver, and closes `native` after the run's task is done.
