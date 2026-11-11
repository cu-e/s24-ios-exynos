# Decision draft: one native run of `loader-diag-xnu-run-usb` (NAT-062) — NOT a decision, NOT requested

Status: **draft text only.** Nothing was asked of the owner and nothing was run. Decision number **0026** is taken when this is promoted (0018 stays reserved).
It is written in the form of decision 0025; once NAT-062 is done the agent copies it to
`docs/decisions/0026-nat062-loader-diag-xnu-run-usb-single-run-<date>.md` (the glob the NAT-062 driver looks for: `*-nat062-loader-diag-xnu-run-usb-single-run-*.md`; the file must
name both hashes below and the words `decision 0019`), fills every `<...>`, commits it before any device access and appends the run-time owner confirmation, as decisions 0021-0025 did.

## Preconditions (a missing one means the file is not promoted and the run does not start)

1. NAT-060 is done with PASS (the host received 27 kernel stop notes to C checkpoint 21, past `arm_vm_init`; commit 78ebfed) — met.
2. NAT-062 is done: the image, a session driver and an analyser, host-tested (derivation, command line, C host build of the dump code, parser, run layer, mutants).
3. The registry `native` permission is set by `lab.py project permit` citing the promoted file only when the run starts, and closed after.
4. The phone is attached on ADB, battery above 50 % and below 42 C, nothing else on the host USB root hub used for the run, the udev rule for 1209:0001 installed.

## Scope

Exactly one image: `loader-diag-xnu-run-usb` — the NAT-059 image (`loader-diag-xnu-ckpt4-usb`) with two changes. **The XNU kernel is no longer held at C checkpoint 21: it is resumed and runs on by itself.**

* RECOVERY SHA-256 `a618b98ccbbc655ca20db2dfac033274582ccdc89d8f8b6128a635b8d48392ff` (100663296 bytes,
  `artifacts/nat-062/package-001/loader-diag-xnu-run-usb/recovery.img`, the file the driver reads; 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT) SHA-256 `c7863c99b2448dd1ea518a83dcfa90cb4e405b6445ddf3d4718e2c9be7e0aadd`, 21861984 bytes at offset 2048.
* Loader-only `Image` SHA-256 `1abdaf3a4716dc45f6828092c1e058a1a10f07bc4af6c473eff45cc7a28dd29a` (307200 bytes).
* Built by `docs/procedures/nat-062/build.py` (NAT-059's build, then `patch_run62.py`, then the command-line patch; `artifacts/nat-062/build-001/build.json`, rebuilt identically as `build-002`), packaged
  by NAT-047's wrapper of NAT-044's `package.py` (`artifacts/nat-062/package-001/package.json`), repository commit `<commit of NAT-062>`. Sources (SHA-256): `patch_run62.py`
  `b51f9d2f3306cbb5b686fcb0b8552218cee3c84f11efd74ff301c52e8955337a`, `build.py` `2acef6448d9207c4143e0fa73bc1d420fbb5a28fb89a07e01499bad97bf36b24`, `glue62.h`
  `6d903add9b84dbdee16035ea296acd9f13aa94929814eaf85eb6a7dff2867473`, `glue62_impl.h` `6bc5898470d0c2933f4de95fa093932a6b25cf2160b3850cd94ac1e8d00aa688`; the stub `ckpt3_stub.S` is unchanged
  (`32ad7a8c0ceab9d619c7e0aebceec9d166bbd1e971361104e6132ab9cb90c7d3`); everything else as in decision 0025 (NAT-036/041/044/045/047/052/059 sources, hashes in `build.json`).
* Stop list: the five assembly stops plus `11,30,31,32,33,34,35,12,40,41,42,43,44,13,14,15,16,17,18,19,20,21` (27 arrivals), exactly as in decision 0025. Loader deadline reset 60 s after arm
  (about T0 + 81 s, polled only from the loader's wait loops), 83 s hardware watchdog, engine service window 0.3 s per pass — as in 0025.
* **Change 1 (the loader):** at the last stop (C checkpoint 21) the stub first sends the stop's `CK` note as before, then dumps the kernel's own console log (`loader_log`, the array that
  `kprintf` output is collected in, NAT-061) as TEXT records over the same USB engine (`KL begin ...`, `KL <offset> <escaped text>`, `KL end ...`; the newest 8192 bytes, then the oldest 8192;
  paced: after each 8 KiB of records the stub polls the engine for 0.5 s so the host can read the 32 KiB ring), and then **resumes the kernel with no further stop** (`slot[2] = 0`; the stub gives back
  the same TTBR0, SP, SCTLR and registers it gave at every earlier stop) instead of holding. The dump is read only if the registers `x0`/`x1` that the kernel's `loader_jump()` passes are exactly
  the PA of the payload's `loader_log` symbol and a length that fits the array; otherwise `KL refused` is sent and nothing is read.
* **Change 2 (the kernel command line):** the payload's NUL-padded command line field is patched (a plain byte change; the header has no checksum): `nat_attempt=NAT020-83s` becomes `nat_attempt=NAT062-run`
  and ` loader_return_after=8` is appended. The kernel's `loader_return_timer_init` (a `thread_call` entered at `STARTUP(EARLY_BOOT, RANK_LAST)`) then calls, after 8 s, `redwood_var_save_on_return()`,
  `redwood_adreno_stop()`, `redwood_wifi_stop()`, `redwood_adsp_stop()` and `loader_return()`, which hands control back to the loader (reason 0, the log in `x0`/`x1`). On such an arrival the loader sends
  the log again (the newest 32 KiB, then the oldest 8 KiB) and holds as before.

Sequence (the protocol of 0021-0025 and of the NAT-062 driver `session_nat062.py --image loader-diag-xnu-run-usb`): gates (this file naming both hashes and decision 0019, the registry incl. NAT-060 and
NAT-062 done, the udev rule, the collector self-test, the device checks, the watcher self-test); one-shot marker `artifacts/nat-062/native-attempt-loader-diag-xnu-run-usb-used.json`; full-image write to
RECOVERY (`/dev/block/sda18`) only; full readback; the USB event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running; one `adb reboot recovery`; the run; then
restore of the pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose iProduct is
`SAMSUNG USB` (never `SEC_UPLOAD`), full-hash readback and an Android check. A failure after the write and before the reboot restores stock and does not reboot. No retry.

What the image does, in order: exactly as 0025 up to C checkpoint 21 (measured by NAT-060, 27 notes). **New on hardware:** the dump of the kernel's log at checkpoint 21 (the first time the kernel's own text is
read), and then the kernel runs on by itself from the end of `arm_init`: `machine_startup` -> `kernel_bootstrap` -> the startup tasks (scheduler, timers, the `thread_call` machinery, VM/IPC/IOKit
initialisation up to wherever it gets) for up to the 8 s of `loader_return_after`. Whatever the kernel prints meanwhile lands in `loader_log` and is sent at its return; if it never returns, the log of
checkpoint 21 is all the text there is.

## Device access granted (and nothing else)

The table of decisions 0022-0025 (PMU window, `pd_hsi0` window, CMU_TOP reads, CMU_HSI0, SYSREG_HSI0, USB control/PHY, DWC3, the 111-operation ladder) — **none added by the loader** — plus what the kernel's own code does
between checkpoint 21 and its return or the deadline: EL1 system registers, the TLB and caches, RAM inside the loader's window, **and whatever MMIO the kernel maps and touches from now on without any stop to
bound it**. The kernel's `loader_return_timer_init` needs the generic timer and the GICv3 (ADT `gic` node: GICD `0x10200000`, GICR `0x10240000`): the timer interrupt, interrupt-controller register
writes and a `SYSREG`/ICC enable are expected; the framebuffer `0xfa200000` (the loader's), `pram` `0xbff00000` and the stubbed UFS node `sweet-ufs` (`0x17100000`) are in the ADT. The static reach of the kernel
code after checkpoint 21 is **not bounded** by the review (thousands of functions, indirect calls not followed); the bound is the 83 s watchdog, the loader's 60 s deadline reset, the 8 s `loader_return_after`
and the entry-point stubs of the payload (29 register-only stubs for the UFS code, NAT-020), which is containment by entry-point denial and not a proof (`redwood_var_save_on_return()` returns at once unless the
stubbed `redwood_ufs_init()` ran). No storage device and no partition other than RECOVERY is written by the loader; the kernel's code is not claimed to be unable to touch any block device. On the host side the run opens only USB 1209:0001 and
reads `/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive under `artifacts/nat-063/` and the USB event log; no camera), judged by `docs/procedures/nat-062/analyze_nat062.py` **unchanged after the run**. Coverage is
shown, not assumed: watcher `start` and the collector's first `poll` before the reboot, the collector's terminal status, and the raw files. The kernel's text is written to a local file by the analyser
(`--log-out`); it is checked for personal data before anything of it is committed.

* PASS: one boot with this image's id and banner, the loader log and both ladder summaries `err=0`, the 27 `CK` notes `n=1..27` as in NAT-060, **one complete `KL` dump of the kernel's log at checkpoint 21
  (`why=1`) after the n=27 note, then a reason-0 note (`x2=0x0`: the kernel handed control back by itself), one complete `KL` dump after it (`why=2`) and `HOLD`**, zero drops, nothing unread, no exception.
* PARTIAL: the stop notes and the first dump arrive but the kernel does not hand control back (`NO RETURN`): the first dump is then the kernel's own text up to checkpoint 21 and **the absence of a return is the
  finding** (timers or the scheduler do not run, the kernel hung, or it reset). Also PARTIAL: a dump that is refused, cut by the deadline reset or damaged in transit (named in the verdict); a return dump that is
  incomplete.
* EXCEPTION: a note with `esr/elr/far` or a loader exception record: the values are the finding.
* FAIL: no enumeration of 1209:0001 although the loader ran, or enumeration with no readable record. Undetermined: no host observation or a host log that does not cover the window.

USB return timing alone is never a message of the run. The return path (reset at the deadline, then NAT-013 restore) is judged as in NAT-046; its failure does not change the log verdict.
A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, the fault variants, MMIO from the loader beyond the above, ACPM/SMC calls from the loader, GPU bring-up, kexec, flashing anything but RECOVERY, GPT,
EFS, keys, erase/factory reset, boot chain changes, and any use of `sudo` or the udev rule by the agent. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user
data stay intact.

## Known limits disclosed

* Source review and host tests only for the new part (NAT-061/NAT-062): nothing after checkpoint 21 has run on this phone; the dump code and the resume at the last stop are tested in a host build of the C and in
  the unicorn-based simulators of NAT-036/NAT-047, which are not an Exynos model.
* **The kernel now runs unobserved.** A hang, an abort, a reset or a `SEC_UPLOAD` / automatic restart are possible outcomes (a debugfs read once sent this phone through `SEC_UPLOAD` and an automatic restart after
  about 47 s, 2026-11-11; the 83 s hardware watchdog on this phone has not been observed to end a hung run, NAT-021 never ran). The loader's deadline reset is polled only from its own wait loops, so a kernel
  that never returns is cut by the 83 s watchdog, not the 60 s deadline. If the phone comes back to Android by itself, the driver's `--restore` is the same restore; Download Mode by keys is the fallback.
  NAT-051: a debugfs `clk_summary` read once sent this phone through `SEC_UPLOAD`; never repeated.
* `loader_return()` and the `redwood_*` quiesce calls run kernel code that nobody has reviewed end to end; whether `kprintf` text reaches `loader_log` on this SoC has not been measured (the first dump
  measures it); timer interrupts may not work, in which case no return arrives (PARTIAL, `NO RETURN`).
* Timing budget: the final dump takes about 1.5 s, the kernel 8 s, the return dump about 4 s, about T0 + 70 s against the loader's reset at about T0 + 81 s.
* A pass says the payload's kernel ran past `arm_init` and returned control by itself with a log; it does not say XNU boots to user space, and it says nothing about devices or the GPU.
* Host-test evidence for the image: `docs/procedures/nat-062/evidence.json` (tests, mutants, hashes).

## Owner confirmation of the run (recorded before the launch)

<to be appended after the owner's answer to the single question naming the image, decision 0026, the commit, both hashes, the one partition written, the single `adb reboot recovery`, the first
free run of the kernel past `arm_init` with whatever MMIO and timer/GIC access it does, the possible hang until the 83 s watchdog, the reset into Download Mode, the restore of the stock RECOVERY and the Android
check, and the bookkeeping steps; not yet recorded>
