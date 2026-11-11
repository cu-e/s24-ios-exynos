# 0027: One native run of loader-diag-xnu-md0-usb (2026-11-12)

Status: recorded by `claude-nat065-20261112-ramdisk` under decision 0019 (owner full-automatic mode) before the run. The file is committed before
any device access. The owner's standing statement (decisions 0025 and 0026: "launch yourself, without asking") is repeated at the end; for this run the agent
first tries to launch and asks only if the launch is refused. Promoted from `docs/procedures/nat-065/decision-draft.md`; the hashes below are those of the NAT-065
build-001/package-001 records (build-002/package-002 are identical rebuilds).

## Preconditions checked when this file was written

* NAT-063 is done (decision 0026, commit 559326c): the payload kernel ran freely after `arm_init`, the host received the kernel's own 19510-byte log by USB, and the kernel panicked in `IOFindBSDRoot`
  because `rd=md0` named a RAM device that did not exist (no ramdisk in the payload). Stock RECOVERY was restored and Android verified; `native` was closed.
* NAT-064 (source review, host-test) is done in commit 2ab84d6: how XNU gets a root device here (`/chosen/memory-map` `RAMDisk` property -> `mdevadd` -> `BSD root: md0` -> `vfs_mountroot`
  -> `load_init_program`), what the kernel prints, the inflated microsecond field, and what is not established.
* NAT-065 (the image, its driver `docs/procedures/nat-065/session_nat065.py`, analyser `analyze_nat065.py`, host-test) is done in the commit that adds this file's draft; its tests
  (24 + 52) and the mutation run are in `docs/procedures/nat-065/evidence.json`.
  NAT-039, NAT-043, NAT-046, NAT-052, NAT-058, NAT-059, NAT-060, NAT-062, NAT-063, NAT-064 and NAT-065 are done.
* The udev rule for 1209:0001 is installed (`host_access.py --check`); the phone is attached on ADB. The one-shot marker for this image does not exist.
* The registry steps of the run: in the same window, the agent opens `native` citing this file with `lab.py project permit`, claims NAT-066 under its own name, runs the driver,
  then `task done NAT-066` while `native` is open and closes `native` again.

## Scope

Exactly one image: `loader-diag-xnu-md0-usb` — NAT-062's `loader-diag-xnu-run-usb` (the loader, the stub, the USB log chain and the run-on at checkpoint 21 are unchanged) with a **different XNU payload: it carries a
16635-byte ramdisk, and the kernel command line is changed**. The loader Image differs from NAT-062's only in the six immediate words that carry the boot id and the image name.

* RECOVERY SHA-256 `c6f4a6e45806edf211ce7de16bf0882268b3f8d22f065a21e575bdb66b06f34d` (100663296 bytes,
  `artifacts/nat-065/package-001/loader-diag-xnu-md0-usb/recovery.img`, the file the driver reads; 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT + ramdisk) SHA-256 `60ca7fc9759efff584b9a13795a16b3a262310cd7823770a408fbac2109087ce`, 21878704 bytes at offset 2048.
* Loader-only `Image` SHA-256 `aa96893fb453dfee8bf2ce7f656f6ab2a94cb030aa700504d4ecf2698426d5dd` (307200 bytes).
* XNU payload (`SWEETXNU`) SHA-256 `131bc977e12e0a72d8f45320e53676e7e64fada56147e753e6015fac8bbc0941`, 21571504 bytes, built by the pinned `mkpayload.py --ramdisk` from NAT-020's inputs
  (build-003; pinned in `build.py`, recorded in `build.json` `nat065_pins`: base `payload.bin` `071bc632f7af0a6aa9b11a679c1d5a951ee80943be11669326949d0725caf544`, `kernel.no-storage`
  `7ceda59bdbedba4d32b80c319e35ec51fe766cf61daa648f80a0c42bbca3e407`, `e1s.adt` `1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e`, `mkpayload.py`
  `50c043e4033ceea682bd20134b5283c1abec51985d49609a3bce5ea0a4013ed7`, `mkinit.py` `2200a8b3225ffc42cbec33747d74fc3562012fb5a2882b8ab5795d453a90ce03`). The ramdisk is the probe init, `docs/procedures/nat-065/src/probe-init.S`
  (SHA-256 `e87b80759cb43f419e59a4370e65623634b0ad6f385f61faacefc593ae538e65`), a Mach-O of 16635 bytes, SHA-256 `b3decc846877fb1de608fcd2734e9c3cb5d2d4ed9e3388bf99d303a45e4761a6`.
  The ADT grows to 14008 bytes (a `/chosen/memory-map` `RAMDisk` property of 52 bytes is added); NAT-022's adt_size fix is not applied (the size is already a multiple of 8).
* Built by `docs/procedures/nat-065/build.py` (SHA-256 `f2f964c068efa17f988752dee547d72dd1b0eaaec0d1344e924f8b13bf7698d8`), packaged by NAT-047's wrapper of NAT-044's `package.py`
  (`artifacts/nat-065/package-001/package.json`), repository commit: the one that adds this decision's draft and the NAT-065 tools. The loader is re-derived from NAT-052 + NAT-059 + NAT-062's `patch_run62.py`,
  unchanged (SHA-256): NAT-062 `patch_run62.py` `b51f9d2f3306cbb5b686fcb0b8552218cee3c84f11efd74ff301c52e8955337a`, `build.py` `2acef6448d9207c4143e0fa73bc1d420fbb5a28fb89a07e01499bad97bf36b24`,
  `src/glue62.h` `6d903add9b84dbdee16035ea296acd9f13aa94929814eaf85eb6a7dff2867473`, `src/glue62_impl.h` `6bc5898470d0c2933f4de95fa093932a6b25cf2160b3850cd94ac1e8d00aa688`; NAT-059 `patch_ckpt59.py`
  `e3a31b9293384ded995262d092939720a1c37e7922c11aa22c6565182f8ab333`, `build.py` `ecdf3229c912af4351f7dd7a53a4107482806260de25698af9df1bba053991d9`; NAT-052 `patch_ckpt52.py`
  `732bcf9ec53b73687d10c1096966d1fc3e6c0e94d4e9c9417c98fe2fcde1d60f`, `src/glue52.h` `ef4c55e9b45d3e940eede78912f7c07169bfe8ffa73895e350859bf9842e2a9d`, `src/glue52_impl.h`
  `2b11850d5972f080ea938b3abbd6a6a66b34c47df4bcf9cedd15aaa7b5f8a192`; NAT-036 `ckpt3_stub.S` `32ad7a8c0ceab9d619c7e0aebceec9d166bbd1e971361104e6132ab9cb90c7d3`; NAT-047 `markerlib47.c`
  `97fac0a7f8c8376ee4be37232cd35d468ef832463acda317d35ec2d3477feebc` (the other NAT-036/041/045/047 sources are listed with hashes in `build.json`).
* **Change in the kernel command line** (exactly, 203 bytes, under the 256-byte field):
  `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT065-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1`.
  Against NAT-062's line: `nat_attempt=NAT062-run` becomes `NAT065-md0` and ` launchdsuffix=release cs_enforcement_disable=1` is appended (`rd=md0` was already there; there was no ramdisk behind it).
* **Change in the loader's ADT patch** (code that has never run on hardware): `adt_rebase_ramdisk` in `adt_patch.c` adds `win_base - phys_base` (the distance between the window the loader copied
  the payload to and the physical base the payload was linked for) to the physical address in the 16-byte (address, size) value of the `RAMDisk` property, so that the ramdisk is where `ml_static_ptovirt(phys)` expects it. It is exercised on the host by a compiled copy of the
  same C file (ASAN/UBSAN, `test_nat065.py`), not on the phone.
* Stop list, deadline reset, the 83 s watchdog, the engine service windows and the `KL` dumps at the last stop and at the return: exactly as in decision 0026.

Sequence (the protocol of 0021-0026 and of the NAT-065 driver `session_nat065.py --image loader-diag-xnu-md0-usb`): gates (this file naming both hashes and decision 0019, the registry incl.
NAT-063/064/065 done, the udev rule, the collector self-test, the device checks, the watcher self-test); one-shot marker `artifacts/nat-065/native-attempt-loader-diag-xnu-md0-usb-used.json`; full-image write to
RECOVERY (`/dev/block/sda18`) only; full readback; the USB event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running; one `adb reboot recovery`; the run; then
restore of the pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose iProduct is
`SAMSUNG USB` (never `SEC_UPLOAD`), full-hash readback and an Android check. A failure after the write and before the reboot restores stock and does not reboot. No retry.

What the image does, in order: exactly as 0026 up to the kernel's return to run freely after checkpoint 21 and the dump at checkpoint 21. **New on hardware, if the kernel gets that far:**
`IOFindBSDRoot` finds `rd=md0`, takes the `RAMDisk` property, configures `md0` (a RAM block device over the 16635-byte image) and prints `BSD root: md0, major …, minor …`; `vfs_mountroot` tries APFS and then
the project's mockfs, which maps `/sbin/launchd` to the raw Mach-O; `load_init_program` execs it as PID 1 in user mode with `launchdsuffix=release cs_enforcement_disable=1`. The probe opens `/dev/console`, writes one banner line,
calls `select` for 1 s, writes one line, and calls `exit(0x50 + getpid())`. PID 1 exiting makes the kernel panic ("initproc failed to start … exit status 81"), which reaches `loader_return()`; the log is dumped again. The probe makes
only these system calls: `open`, `write`, `getpid`, `select`, `exit`. It maps no memory, opens no device other than `/dev/console`, and touches no storage.

## Device access granted (and nothing else)

As in decision 0026: the PMU window, `pd_hsi0` window, CMU_TOP reads, CMU_HSI0, SYSREG_HSI0, USB control/PHY, DWC3 and the 111-operation ladder — none added by the loader — plus what the kernel's own code does after
checkpoint 21: EL1 system registers, the TLB and caches, RAM inside the loader's window, and whatever MMIO the kernel maps and touches (as measured by NAT-063, it ran to `IOFindBSDRoot` and the panic without a reset).
**New:** the kernel now also runs the BSD-layer code after `IOFindBSDRoot` — `mdevadd`, `vfs_mountroot`, the exec of a user-mode Mach-O, the scheduler with a user thread, system-call entry/exit and the panic path
with a user process involved — and the probe's few system calls (above). Reachable code after that point is not bounded by the review. The bound is the 83 s watchdog, the loader's deadline reset, the 8 s
`loader_return_after`, and entry-point stubs for the UFS code (NAT-020). No storage device and no partition other than RECOVERY is written by the loader, and the kernel's code is not claimed unable to touch a block
device. The host opens only USB 1209:0001 and reads `/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive under `artifacts/nat-066/` and the USB event log; no camera), judged by `docs/procedures/nat-062/analyze_nat062.py` (the chain) and
`docs/procedures/nat-065/analyze_nat065.py` (`root`), **both unchanged after the run**. The kernel's text is written to a local file by the analyser (`--log-out`) and checked for personal data before
anything of it is committed.

* The chain verdict is judged as in decision 0026 (27 `CK` notes, `KL` dump at the last stop, the kernel's own return, the second dump, `HOLD`, no drop, no exception). `root.outcome` is a reading of the received text:
  * **PASS (this run's question): `root.outcome == "probe-ran-to-exit"`** — the kernel text shows `BSD root: md0`, the panic "initproc failed to start … exit status 8N" (N = the PID, 1 expected) — i.e. the ramdisk reached
    the kernel, was mounted, and the probe ran as PID N in user mode and exited by itself. The banner text in the log is *not* required (whether PID 1's console writes reach `loader_log` is itself unknown).
  * Informative, not PASS: `probe-no-console` (exit status 96: PID 1 ran but `/dev/console` could not be opened — the console is then the next problem), `init-exited-other` / `init-killed` (the number is the finding; for a signal,
    the code-signing/exec policy or a fault in user mode), `root-device-missing` (the NAT-063 panic again: the ramdisk did not reach `mdevadd`; the loader's rebase or the memory-map property is wrong), `other-panic` (its first line
    is the finding), `no-panic-text` (a cut or missing log).
  * A failed mount makes the kernel retry with 5 s sleeps and no panic: the run then ends by the timed return (PARTIAL) or by the deadline reset; the missing panic text is the finding.
* EXCEPTION: a note with `esr/elr/far` or a loader exception record: the values are the finding. FAIL: no enumeration of 1209:0001 although the loader ran. Undetermined: no host observation.

A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, MMIO from the loader beyond the above, ACPM/SMC calls from the loader, GPU bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain
changes, and any use of `sudo` or the udev rule by the agent. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact.

## Known limits disclosed

* Host tests and source review only for the new part: nothing about the ramdisk has run on this phone. **Unknown, each with the check that resolves it (this run):** whether the ramdisk bytes land where `ml_static_ptovirt(phys)` expects
  them (the loader rebase has never executed on hardware); whether `vfs_mountroot` accepts the raw Mach-O through mockfs; whether an ad-hoc-signed init may be exec'd (`cs_enforcement_disable=1` is passed, never tested);
  whether PID 1's console writes reach `loader_log` live (not required for PASS); the absolute kernel clock rate; the timed `loader_return_after=8` return and the `redwood_*_stop` paths (NAT-063 returned through the panic path,
  not through the timer); the `pe_arm_map_interrupt_controller` warning seen in NAT-063 is not explained.
* **The kernel runs unobserved**, as in decision 0026. A hang, an abort, a reset or a `SEC_UPLOAD` / automatic restart are possible outcomes; the 83 s hardware watchdog has not been observed to end a hung
  run on this phone (NAT-021 never ran). If the phone comes back to Android by itself, the driver's `--restore` is the same restore; Download Mode by keys is the fallback. NAT-051: a debugfs `clk_summary` read once sent this
  phone through `SEC_UPLOAD`; never repeated.
* A pass says: a user-mode program shipped by this project was run by the payload kernel on this phone and the host received the evidence. It does not say that Apple's launchd or any Apple userland runs, and says nothing about
  the console/display or the GPU. The probe is not Apple's launchd; QEMU/unicorn runs of the probe are not hardware evidence.
* Host-test evidence: `docs/procedures/nat-065/evidence.json`.

## Owner's standing authorisation (no run-specific confirmation is recorded)

No answer from the owner about this particular image exists, and none is asked for. The owner's standing statements are recorded in decisions 0025 and 0026: on 2026-11-12 the owner wrote "яже говорил что ты можешь без этого хапроса х сам запускать САМ БЕЗ ЗАПРОСА ЗАПУСКАЙ" (verbatim, typos included; in English:
"I already said you can launch without this question, launch it YOURSELF WITHOUT ASKING"). That statement is read as covering runs of this kind (one native image per decision file under the protocol of decision 0019, written
only to RECOVERY and restored from the pinned stock image). It does not widen the list of what is not granted above or the boundary of decision 0002; each run still gets its decision file naming its hashes, which the driver
requires. For this run the agent first tries to launch without asking and asks only if the launch is refused.
