# 0028: One native run of loader-diag-xnu-ne1-usb (2026-11-12)

Status: recorded by `claude-nat065-20261112-ramdisk` under decision 0019 (owner full-automatic mode) before the run. The file is committed before any device access (the driver reads it from the tree). The owner's standing statement (decisions 0025 and 0026: "launch yourself, without asking") is repeated at the end; for this run the agent first tries to launch and asks only if the launch is refused. Promoted from `docs/procedures/nat-067/decision-draft.md` (NAT-067, commit d24667b); the hashes below are those of the NAT-067 build-001/package-001 records (build-002 is an identical rebuild).

## Preconditions checked when this file was written

* NAT-066 is done (decision 0027, commit 732f371): the host again received the whole log chain (PASS: 27 stop notes, the kernel's own return, 22994 bytes of kernel text, `HOLD`, no drop, no exception). The ramdisk reached the kernel
  and became the BSD root (`Added memory device md0/rmd0 ... for 0000000000008000`, `BSD root: md0, major 1, minor 0`, `vfs_mountroot` and `VFS_ROOT` returned, `devfs_kernel_mount` ran). **PID 1 did not start**: the kernel took a data abort
  (`esr 0x96000005`, `far 0x110300e4`, a physical GPIO address) at `_e1s_touch_init + 0x174`, called from `bsd_init`, before `load_init_program`. Stock RECOVERY was restored and Android verified; `native` was closed.
* The abort is a defect of the e1s touch driver patch in this configuration (`gpio_rd` dereferences physical-address macros instead of the `ml_io_map`ped base; source review of
  `references/s24-port/xnu/e1s/patches/0003-e1s-touch.patch` plus the pinned kernel's Mach-O symbol table, see `docs/procedures/nat-066/README.md`), not a defect of the loader, the ramdisk or the root path.
* NAT-067 (this task; host-test) built the image, derived its driver and analyser, and tested them: `test_nat067.py` 24 tests OK (0 skipped), `mutants.py` 36 of 37 mutants killed (1 equivalent: D9), `make check` result in `docs/procedures/nat-067/evidence.json`.
  NAT-039, NAT-043, NAT-046, NAT-052, NAT-058, NAT-059, NAT-060, NAT-062, NAT-063, NAT-064, NAT-065, NAT-066 and NAT-067 are done (the driver's registry gate checks exactly these).
* The udev rule for 1209:0001 is installed (`host_access.py --check` exit 0); the phone is attached on ADB with the battery above the driver's floor. The one-shot marker for this image (`artifacts/nat-067/native-attempt-loader-diag-xnu-ne1-usb-used.json`) does not exist.
* The registry steps of the run: in the same window the agent opens `native` citing this file with `lab.py project permit`, claims NAT-068 under its own session name, runs the driver, then `task done NAT-068` while `native` is open and closes `native` again.

## Scope

Exactly one image: `loader-diag-xnu-ne1-usb` — NAT-065's `loader-diag-xnu-md0-usb` (the loader, the stub, the USB log chain, the run-on at checkpoint 21, the same kernel, the same ADT, the same 16635-byte probe-init ramdisk) with **one change to the
kernel command line: the tag and two appended boot-args**. The name has the same length as NAT-065's on purpose; the loader Image therefore differs from the one that ran in NAT-066 only in the six immediate words that carry the boot id and the image name
(`test_nat067.py`, `Payload`); the XNU payload differs from NAT-065's only in the command-line field at offset 0x48; the ramdisk is byte-identical.

* RECOVERY SHA-256 `ae946b4be577b8179ad55f8c43bc4c9ca8afc50c25c131f6823f99d98ea2552d` (100663296 bytes, `artifacts/nat-067/package-001/loader-diag-xnu-ne1-usb/recovery.img`, the file the driver reads; 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT + ramdisk) SHA-256 `9fd29fb999dab902f63f04d9f01313be9171c55d539de86cf4dd20c3f18c9cda`, 21878704 bytes at offset 2048.
* Loader-only `Image` SHA-256 `5c11c7477bb2dd285b5081bbeb01ce97bf0cc1725d0c41b8b3cbef707a13a99e` (307200 bytes; NAT-065's was `aa96893fb453dfee8bf2ce7f656f6ab2a94cb030aa700504d4ecf2698426d5dd`).
* XNU payload (`SWEETXNU`) SHA-256 `8e333b896beb7adc9835a350b75a14858d73e379e38f9ac0f3f917e5ba1294da`, 21571504 bytes (`build.json` `nat065_payload`; the key keeps NAT-065's name and describes this image), built by the
  pinned `mkpayload.py --ramdisk` from the NAT-020 inputs pinned in `build.json` `nat065_pins` (base `payload.bin` `071bc632f7af0a6aa9b11a679c1d5a951ee80943be11669326949d0725caf544`, `kernel.no-storage`
  `7ceda59bdbedba4d32b80c319e35ec51fe766cf61daa648f80a0c42bbca3e407`, `e1s.adt` `1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e`, `mkpayload.py`
  `50c043e4033ceea682bd20134b5283c1abec51985d49609a3bce5ea0a4013ed7`, `mkinit.py` `2200a8b3225ffc42cbec33747d74fc3562012fb5a2882b8ab5795d453a90ce03`). The ramdisk is NAT-065's probe init (`docs/procedures/nat-065/src/probe-init.S`,
  SHA-256 `e87b80759cb43f419e59a4370e65623634b0ad6f385f61faacefc593ae538e65`), a Mach-O of 16635 bytes, SHA-256 `b3decc846877fb1de608fcd2734e9c3cb5d2d4ed9e3388bf99d303a45e4761a6`.
* Built by `docs/procedures/nat-067/build.py` (SHA-256 `bbc882c282fd4543f46981e35c178b9e1e0d4e6bf45528f0b53c02dd19c68230`), which loads NAT-065's `build.py` (`f2f964c068efa17f988752dee547d72dd1b0eaaec0d1344e924f8b13bf7698d8`) and replaces three values;
  packaged by NAT-047's wrapper of NAT-044's `package.py` (`artifacts/nat-067/package-001/package.json`, SHA-256 `aa547063d81205987a36f41251e3e7b9ac0be4294089533a9b4c55e34edf87e9`, and the per-image record `loader-diag-xnu-ne1-usb/package.json`, SHA-256 `53c14ffd3886d23ee1d35ad7c6447ad9f88408a15e4336457becd8b86c5ca540`). Driver `session_nat067.py`
  (`937978d2bc10e680139e15a97eb605c2f29c0c55a8f757721d51daea352332c4`, derived from NAT-065's `1cf8939bc75b90fbdd48b3765f1af814060ecf0d5c2d8cfc482f6d1754aa0caa` by `derive.py`), analyser `analyze_nat067.py`
  (`a8c068c72384886f7aa99da7c9c8d4e2c4f9563536771420c65ac160801c8b3f`, a wrapper over NAT-065's `analyze_nat065.py` `b4b9d2f9440aa354dd2c8d0f1c99fe328669d92a763f4fdc3ea22e49a72c5569` and NAT-062's `analyze_nat062.py`
  `32343921482250dd40bcfaf960bb05cac9697a3d1a7f86213e0402efa27af551`). The loader sources (NAT-036/041/045/047/052/059/062) are those of decision 0027, unchanged.
* **Change in the kernel command line** (exactly, 227 bytes, under the 256-byte field):
  `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT067-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0`.
  Against NAT-065's line: `nat_attempt=NAT065-md0` becomes `NAT067-md0`, and ` e1stouch=0 e1sbattery=0` is appended. `e1stouch=0` makes `e1s_touch_init` print `e1s-touch: disabled` and return before it maps or reads any register (the abort of NAT-066);
  `e1sbattery=0` does the same for the battery driver, which maps the GPP8 block and bit-bangs two pins from a kernel thread. Both names are the ones the pinned patches parse with `PE_parse_boot_argn` (checked on the patch sources by `test_nat067.py`, `Kernel`).
* Stop list, deadline reset, the 83 s watchdog, the engine service windows and the `KL` dumps at the last stop and at the return: exactly as in decisions 0026 and 0027.

Sequence (the protocol of 0021-0027 and of the NAT-067 driver `session_nat067.py --image loader-diag-xnu-ne1-usb`): gates (this file naming both hashes and decision 0019, the registry incl. NAT-063..067 done, the udev rule, the collector self-test,
the device checks, the watcher self-test); one-shot marker; full-image write to RECOVERY (`/dev/block/sda18`) only; full readback; the USB event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running; one `adb reboot recovery`;
the run; then restore of the pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose iProduct is `SAMSUNG USB` (never `SEC_UPLOAD`),
full-hash readback and an Android check. A failure after the write and before the reboot restores stock and does not reboot. No retry.

What the image does, in order: exactly as 0027 up to `devfs_kernel_mount` and the display/ACPM/PMIC/keys driver init (all observed on hardware in NAT-066). **New on hardware, if the kernel gets that far:** the touch and battery drivers return early;
`bsd_init` goes on after them (everything between `e1s_touch_init` and `load_init_program` has never run on this phone: unknown further drivers and services, the rest of `bsd_init`); `load_init_program` execs the project's probe (mockfs maps `/sbin/launchd` to the raw Mach-O) as
PID 1 in user mode with `launchdsuffix=release cs_enforcement_disable=1`. The probe opens `/dev/console`, writes one banner line, calls `select` for 1 s, writes one line, and calls `exit(0x50 + getpid())`; PID 1 exiting makes the kernel panic
("initproc failed to start … exit status 81"), which reaches `loader_return()`; the log is dumped again. The probe makes only these system calls: `open`, `write`, `getpid`, `select`, `exit`. It maps no memory, opens no device other than `/dev/console`, and touches no storage.

## Device access granted (and nothing else)

As in decisions 0026 and 0027: the PMU window, `pd_hsi0` window, CMU_TOP reads, CMU_HSI0, SYSREG_HSI0, USB control/PHY, DWC3 and the 111-operation ladder — none added by the loader — plus what the kernel's own code does after checkpoint 21: EL1 system registers,
the TLB and caches, RAM inside the loader's window, and whatever MMIO the kernel maps and touches (measured: NAT-063 and NAT-066 ran to the BSD layer and a kernel panic without a reset).
**New relative to 0027:** with the touch and battery drivers off, the kernel runs the code after them: the rest of `bsd_init`, `load_init_program`, the exec of a user-mode Mach-O, the scheduler with a user thread, system-call entry/exit, and the panic path with a
user process involved — and the probe's few system calls. Reachable code after that point is not bounded by the review. The bound is the 83 s watchdog, the loader's deadline reset, the 8 s `loader_return_after`, and entry-point stubs for the UFS code (NAT-020).
No storage device and no partition other than RECOVERY is written by the loader, and the kernel's code is not claimed unable to touch a block device. The host opens only USB 1209:0001 and reads `/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive under `artifacts/nat-068/` and the USB event log; no camera), judged by `docs/procedures/nat-062/analyze_nat062.py` (the chain) and the NAT-065 `root` reading through
`docs/procedures/nat-067/analyze_nat067.py`, **both unchanged after the run**. The kernel's text is written to a local file by the analyser (`--log-out`) and checked for personal data before anything of it is committed.

* The chain verdict is judged as in decisions 0026 and 0027 (27 `CK` notes, `KL` dump at the last stop, the kernel's own return, the second dump, `HOLD`, no drop, no exception). `root.outcome` is a reading of the received text:
  * **PASS (this run's question): `root.outcome == "probe-ran-to-exit"`** — the kernel text shows `BSD root: md0`, the panic "initproc failed to start … exit status 8N" (N = the PID, 1 expected) — i.e. the kernel got past the e1s driver init, the
    probe ran as PID N in user mode and exited by itself. The banner text in the log is *not* required (whether PID 1's console writes reach `loader_log` is itself unknown).
  * Informative, not PASS: `probe-no-console` (exit status 96: PID 1 ran but `/dev/console` could not be opened — the console is then the next problem), `init-exited-other` / `init-killed` (the number is the finding; for a signal, the code-signing/exec
    policy or a fault in user mode), `root-device-missing` (the NAT-063 panic again), `other-panic` (its first line is the finding: another driver or service faulting after the touch driver — symbolicate it with the pinned kernel's symbol table, as in NAT-066),
    `no-panic-text` (a cut or missing log).
  * A failed mount makes the kernel retry with 5 s sleeps and no panic: the run then ends by the timed return (PARTIAL) or by the deadline reset; the missing panic text is the finding.
* EXCEPTION: a note with `esr/elr/far` or a loader exception record: the values are the finding. FAIL: no enumeration of 1209:0001 although the loader ran. Undetermined: no host observation.

A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, MMIO from the loader beyond the above, ACPM/SMC calls from the loader, GPU bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain changes, and any use of `sudo`
or the udev rule by the agent. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Host tests and source review only for the new part: nothing after `e1s_touch_init` in `bsd_init` has run on this phone. **Unknown, each with the check that resolves it (this run):** whether other e1s drivers or services fault later in `bsd_init`;
  whether the ramdisk **bytes** are intact at their kernel address and whether mockfs serves them as `/sbin/launchd` (nothing has read them yet); whether an ad-hoc-signed init may be exec'd (`cs_enforcement_disable=1` is passed, never tested; the root is
  `rd=md0`, for which `bsd_rooted_ramdisk()` skips `FSIOC_KERNEL_ROOTAUTH`, source review in NAT-064); whether PID 1's console writes reach `loader_log` live (not required for PASS); the absolute kernel clock rate; the timed `loader_return_after=8` return and
  the `redwood_*_stop` paths (NAT-063 and NAT-066 both returned through the panic path, not through the timer).
* **The kernel runs unobserved**, as in decisions 0026 and 0027. A hang, an abort, a reset or a `SEC_UPLOAD` / automatic restart are possible outcomes; the 83 s hardware watchdog has not been observed to end a hung run on this phone. If the phone comes back to
  Android by itself, the driver's `--restore` is the same restore; Download Mode by keys is the fallback. NAT-051: a debugfs `clk_summary` read once sent this phone through `SEC_UPLOAD`; never repeated.
* A pass says: a user-mode program shipped by this project was run by the payload kernel on this phone and the host received the evidence. It does not say that Apple's launchd or any Apple userland runs, and says nothing about the console/display or the GPU.
  The probe is not Apple's launchd; QEMU/unicorn runs of the probe are not hardware evidence. Disabling the touch and battery drivers by boot-arg removes those drivers' functions from this run; it is a bring-up step, not a fix of the touch patch.
* Host-test evidence: `docs/procedures/nat-067/evidence.json`.

## Owner's standing authorisation (no run-specific confirmation is recorded)

No answer from the owner about this particular image exists, and none is asked for. The owner's standing statements are recorded in decisions 0025 and 0026: on 2026-11-12 the owner wrote "яже говорил что ты можешь без этого хапроса х сам запускать САМ БЕЗ ЗАПРОСА ЗАПУСКАЙ"
(verbatim, typos included; in English: "I already said you can launch without this question, launch it YOURSELF WITHOUT ASKING"). That statement is read as covering runs of this kind (one native image per decision file under the protocol of decision 0019, written only to RECOVERY and
restored from the pinned stock image). It does not widen the list of what is not granted above or the boundary of decision 0002; each run still gets its decision file naming its hashes, which the driver requires. For this run the agent first tries to launch without asking
and asks only if the launch is refused.
