# 0025: One native run of loader-diag-xnu-ckpt4-usb (2026-11-11)

Status: recorded by `claude-nat059-20261111-session` under decision 0019 (owner full-automatic mode) before the run. The file is committed before
any device access; an owner confirmation for the run itself is appended to it before the launch (the auto-mode classifier refuses an unconfirmed
native launch, see decisions 0021-0024). Nothing here is run until that confirmation is recorded. Promoted from
`docs/procedures/nat-059/decision-draft.md`; the numbers and hashes below are those of the NAT-059 package-002/build-002 records (package-003/build-003 are identical rebuilds).

## Preconditions checked when this file was written

* NAT-058 is done with PASS (decision 0024, commit 235b7dd): the computer received all 22 kernel stop notes of `loader-diag-xnu-ckpt3-usb` to C checkpoint 16 by itself, the stub's resume
  worked 21 times on the phone, the kernel's `TTBR0` at checkpoint 5 was measured as `0x9e15ae000` (the NAT-035 model value), stock RECOVERY was restored and Android verified.
* NAT-059 (the image, its driver `docs/procedures/nat-059/session_nat059.py` and analyser `analyze_nat059.py`, host-test; 20 + 21 tests, 27 of 27 mutants killed) is done in commit 6c15454.
  NAT-039, NAT-043, NAT-046, NAT-052 and NAT-058 are done.
* The udev rule for 1209:0001 is installed (`host_access.py --check` exit 0). Phone attached on ADB, battery 84 %, 29.7 C. The one-shot marker for this image does not exist.
* The registry steps of the run: in the same window, after the owner's answer, the agent claims NAT-060 under its own name, opens `native` citing this file with `lab.py project permit`,
  runs the driver, then `task done NAT-060` while `native` is open and closes `native` again.

## Scope

Exactly one image: `loader-diag-xnu-ckpt4-usb`.

* RECOVERY SHA-256 `60147f1f6190c688b89ea63ac1f56816e977db692eb3864bf2aaa404ea868dd1` (100663296 bytes,
  `artifacts/nat-059/package-002/loader-diag-xnu-ckpt4-usb/recovery.img`, the file the driver reads; `package-003` holds the identical RECOVERY; 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT) SHA-256 `3bb6e5d14368ef3627288f44aeff9c00c1e510915395db5988de600402b0af20`, 21857888 bytes at offset 2048.
* Loader-only `Image` SHA-256 `4af99c079e151c446a7a3644788b00492b98910298ac68954c60707f5acc0e1b` (303104 bytes).
* Built by `docs/procedures/nat-059/build.py` (NAT-052's build plus `patch_ckpt59.py`; `artifacts/nat-059/build-002/build.json`, rebuilt identically as `build-003`), packaged by NAT-047's wrapper of NAT-044's
  `package.py` (`artifacts/nat-059/package-002/package.json`), repository commit `6c15454`. Sources (SHA-256): `patch_ckpt59.py`
  `e3a31b9293384ded995262d092939720a1c37e7922c11aa22c6565182f8ab333`, `build.py` `ecdf3229c912af4351f7dd7a53a4107482806260de25698af9df1bba053991d9`; derived `ckpt3.c`
  `03a5256080571f54607ad5f41c8f9cded905b51888680b373c9d6dc64ece32b7`, `ckpt3.h` `7d2f834d9859771c1c164a3c2c842a4b7abcabb5c096562b4232270d72501600`, unchanged `ckpt3_stub.S`
  `32ad7a8c0ceab9d619c7e0aebceec9d166bbd1e971361104e6132ab9cb90c7d3`; everything else as in decision 0024 (NAT-036/041/045/047/052 sources, hashes in `build.json`).
* Stop list: the five assembly stops plus `11,30,31,32,33,34,35,12,40,41,42,43,44,13,14,15,16,17,18,19,20,21` (27 arrivals); the stub holds at checkpoint 21.
  Loader deadline reset 60 s, 83 s watchdog, engine service window 0.3 s per pass — all as in 0024.

Sequence (the protocol of 0021-0024 and of the NAT-059 driver `session_nat059.py --image loader-diag-xnu-ckpt4-usb`): gates (this file naming both hashes and decision 0019, the
registry, the udev rule, the collector self-test, the device checks, the watcher self-test); one-shot marker `artifacts/nat-059/native-attempt-loader-diag-xnu-ckpt4-usb-used.json`;
full-image write to RECOVERY (`/dev/block/sda18`) only; full readback; the USB event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running;
one `adb reboot recovery`; the run; then restore of the pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb
venv python on a device whose iProduct is `SAMSUNG USB` (never `SEC_UPLOAD`), full-hash readback and an Android check. A failure after the write and before the reboot restores stock and
does not reboot. No retry.

What the image does, in order: exactly as 0024 up to C checkpoint 16 (measured by NAT-058). **New on hardware:** after checkpoint 16 the kernel's `arm_vm_init` runs (it replaces the
kernel's `TTBR0_EL1` with the table `_invalid_ttep`; the stub gives back that table, read by physical address after a cache clean, at each later stop instead of the one measured at
assembly checkpoint 5), and the kernel then runs `patch_low_glo`, `PE_consistent_debug_inherit`, `serial_init`, `kernel_startup_initialize_upto`, the console and boot-arg code,
`PE_init_printf`, `cpu_machine_idle_init`, `PE_init_platform` (with `vm_initialized` set), `ml_map_cpu_pio`, `cpu_timebase_init`, `kptimer_curcpu_up`, `PE_init_cpu`, `fiq_context_init`,
the SecureDT lookups and `early_random`, up to C checkpoint 21, each stop giving one `CK` note over USB; at checkpoint 21 it queues `HOLD` and the reset follows at the deadline.

## Device access granted (and nothing else)

The table of decisions 0022-0024 (PMU window, `pd_hsi0` window, CMU_TOP reads, CMU_HSI0, SYSREG_HSI0, USB control/PHY, DWC3, the 111-operation ladder) — **none added by the loader** —
plus what the kernel's own early code touches up to checkpoint 21: EL1 system registers, the TLB and caches, RAM inside the loader's window, and **now also whatever MMIO the kernel maps
through `ml_io_map` after `vm_initialized`**. The ADT in the payload (16 nodes) puts `arm-io` ranges (`0 -> 0x10000000`, size `0xf0000000`) and a `gic` node (`reg` `0x200000/0x10000`,
`0x240000/0x140000` = GICD `0x10200000`, GICR `0x10240000`) in front of that code: kernel interrupt-controller register access is possible and is part of what is granted. The ADT has
no UART node and the storage node `sweet-ufs` (`0x17100000`) is used by IOKit, which this list does not reach. The static reach of the kernel code from the stops is **not bounded** by
the review (3000-5900 functions, indirect calls not followed); the bound is the stop list and the 83 s watchdog, not a proof. No storage device and no partition other than
RECOVERY is written by the loader; the kernel's code is not claimed to be unable to touch any block device. On the host side the run opens only USB 1209:0001 and reads
`/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive under `artifacts/nat-060/` and the USB event log; no camera), judged by `docs/procedures/nat-059/analyze_nat059.py` **unchanged after the run**.
Coverage is shown, not assumed: watcher `start` and the collector's first `poll` before the reboot, the collector's terminal status, and the raw files.

* PASS (kernel progress over the transport): one boot with this image's id and banner, the loader log and both ladder summaries `err=0`, the 27 `CK` notes `n=1..27` with the checkpoints this
  image has at each position and no gap, the `kttbr0=` value constant up to checkpoint 16 (`0x9e15ae000` in NAT-058) and, for 17..21, one common table base that differs from the checkpoint-5 one and is 4 KiB aligned, the final-stop bit at
  `n=27` (checkpoint 21) **and** the `HOLD` record, zero drops, nothing unread, no exception.
* PARTIAL: the channel works but the notes end earlier or have gaps or the `HOLD` is missing: the last note names how far XNU got and the missing next call is the finding (the stop after a
  silence is where the kernel hung, faulted without the stub's report, or reset); BAD_TTBR0 (mask bit 12) and BAD_STATE (bit 14) holds are named as such.
* EXCEPTION: a note with `esr/elr/far` or a loader exception record: the values are the finding.
* FAIL: no enumeration of 1209:0001 although the loader ran, or enumeration with no readable record. Undetermined: no host observation or a host log that does not cover the window.

USB return timing alone is never a message of the run. The return path (reset at the deadline, then NAT-013 restore) is judged as in NAT-046; its failure does not change the log verdict.
A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, the fault variants, MMIO from the loader beyond the above, ACPM/SMC calls from the loader, GPU bring-up, kexec, flashing anything but RECOVERY, GPT,
EFS, keys, erase/factory reset, boot chain changes, and any use of `sudo` or the udev rule by the agent. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user
data stay intact.

## Known limits disclosed

* Source review and host/simulator tests only for the new part (NAT-059): the kernel between checkpoints 16 and 21 is not modelled; the assumption that nothing else changes the kernel's `TTBR0` between 17 and
  21 is not proven. Everything the 0024 limits say about the engine, the 0.3 s window and the unpolled gaps stays; NAT-058 showed 22 stops at about 0.4 s each with zero drops.
* `PE_init_platform` etc. may perform GIC/other MMIO with the kernel's own mappings (see above), which no earlier run has done; a hang, an abort or a reset there is a possible outcome. The 83 s watchdog is the
  failsafe (`SEC_UPLOAD`, an automatic restart after about 47 s in the one observation of 2026-11-11); Download Mode by keys is the fallback. NAT-051: a debugfs `clk_summary` read once sent this phone
  through `SEC_UPLOAD`; never repeated.
* A pass frame says the kernel's code ran up to checkpoint 21 under the loader's MMU-off stub; it does not say XNU boots, and it says nothing about devices, interrupts or the GPU.
* Host-test evidence for the image: `docs/procedures/nat-059/evidence.json` (tests, mutants, hashes).

## Owner confirmation of the run (recorded before the launch)

On 2026-11-11 (late evening, host time; recorded after midnight 2026-11-12) the owner answered the question "Запускаю ОДИН нативный запуск образа loader-diag-xnu-ckpt4-usb (решение 0025, коммит 9724d0a), чтобы компьютер получил
по USB сообщения ядра XNU уже ПОСЛЕ arm_vm_init: 27 контрольных точек, до C-точки 21…" with "да запцскай я разрешаю запускать их без разрешения окгда угодно если устройство доступно" (verbatim, typos included;
in English: "yes, launch it, I allow launching them without asking whenever the device is available"). The question named the RECOVERY SHA-256 prefix `60147f1f…8dd1` (full hash in this file), the only partition written
(RECOVERY, `/dev/block/sda18`, full readback), the single `adb reboot recovery`, the same USB monitor 1209:0001 and the same 111-operation HSI0 table as NAT-043/NAT-058 (nothing new from the loader), that the kernel
passes `arm_vm_init` for the first time and runs `serial_init`, `PE_init_platform`, `ml_map_cpu_pio`, `PE_init_cpu`, `early_random` with the possibility of kernel access to interrupt-controller registers
(GIC by the ADT: `0x10200000`/`0x10240000`; not statically bounded, disclosed here), the reset into Download Mode after about 60 s, the restore of the stock RECOVERY (`96620b8b…`, full-hash readback)
and the Android check, that data, apps and settings are untouched, one run and no retry, the risk (hang or exception of the kernel: a partial log, the 83 s watchdog with `SEC_UPLOAD` and an automatic
restart as on 2026-11-11, or Download Mode by keys), and the service steps in the same window: open `native` citing this decision, claim NAT-060, run the driver, close `native` after `task done`.

The second half of the answer is a standing statement of the owner about such runs ("I allow launching them without asking whenever the device is available"). It is recorded here as the owner's words. It is
read as covering runs of this kind (one native image per decision file under the protocol of decision 0019, written only to RECOVERY and restored from the pinned stock image) and does not widen the list
of what is not granted above or the boundary of decision 0002; each run still gets its decision file naming its hashes, which the driver requires.
