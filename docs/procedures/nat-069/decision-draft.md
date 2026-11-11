# 0029: One native run of loader-diag-xnu-ne2-usb (2026-11-12) — DRAFT

Status: draft written by `claude-nat065-20261112-ramdisk` in NAT-069 (host-test). To be promoted unchanged, apart from this status paragraph, to
`docs/decisions/0029-nat069-loader-diag-xnu-ne2-usb-single-run-2026-11-12.md` and committed **before any device access** (the NAT-069 driver reads that file from the tree and refuses without it).
Decision 0019 (owner full-automatic mode) applies. The owner's standing statements (decisions 0025 and 0026: "launch yourself, without asking") are repeated at the end; for this run the agent first tries to launch and asks only if
the launch is refused. Hashes below are those of `artifacts/nat-069/build-001` / `package-001` (`build-002` is an identical rebuild).

## Why this run (the question, the observable, the decision)

The critical path to a real iOS lock screen (`docs/strategy/2026-11-12-ios-critical-path.md`) needs, at milestone 4, a way for a user process to put frames on the physical panel. The one fact that decides **which** way is whether the display engine
that S-Boot/the loader left running scans out the very framebuffer the kernel console draws into (physical `0xfa200000`, 1080x2340, stride 4320, reported on hardware in NAT-068). Nothing measured says so yet.

* **Question:** do the display engine registers (DECON, DECON0 windows, RDMA channels, DSIM0/1, DCPHY0, DPU_MIPI_PHY_CON) describe a running pipeline that reads the loader's framebuffer?
* **Observable:** the `e1s-display:` lines the pinned patch `0010-e1s-display.patch` prints when `e1sdisp=2`, parsed by `analyze_nat069.py` into `display.fork`.
* **Decision it feeds:** `scans-loader-framebuffer` → milestone 4 uses the framebuffer-copy path through `MiniIOMobileFramebuffer` and UI-003 (a full DECON/DSIM bring-up) stays off the critical path; `pipeline-idle`, `decon-running-no-enabled-rdma`,
  `scans-other-buffer` or `rdma-reads-framebuffer-decon-idle` → UI-003 (or a closer look at the named register) moves ahead of the first SpringBoard attempt; `cannot-map`, an abort or a hang → a loader-side power/clock step or a window-by-window bisection image comes first.
  The reading is of register values at one moment; whether the panel shows CPU writes to that buffer is a separate fact, not decided by this run.

## Preconditions checked when this file was written

* NAT-068 is done (decision 0028, commit 59123c0): the payload kernel ran the project's probe as PID 1 on this phone (`root.outcome` `probe-ran-to-exit`, exit status 81) and the host received the whole log chain by itself (PASS). That run also printed the
  default `e1sdisp=1` report: `e1s-display: framebuffer 1080x2340 depth 32 stride 4320 phys 0xfa200000`, first sample words `0xffffffff 0xffffffff 0 0` (`docs/procedures/nat-068/run-001-kernel-log.txt`). Stock RECOVERY was restored and Android verified; `native` was closed.
* NAT-069 (this task; host-test) built the image, derived its driver, extended the analyser with the display reading, and tested them: `test_nat069.py` 39 tests OK (0 skipped), `mutants.py` 63 of 65 mutants killed (2 equivalent: D9, M10, 0 survived),
  `make check` result in `docs/procedures/nat-069/evidence.json`. NAT-039, NAT-043, NAT-046, NAT-052, NAT-058, NAT-059, NAT-060, NAT-062, NAT-063, NAT-064, NAT-065, NAT-066, NAT-067, NAT-068 and NAT-069 are done (the driver's registry gate checks exactly these).
* The udev rule for 1209:0001 is installed (`host_access.py --check` exit 0); the phone is attached on ADB with the battery above the driver's floor. The one-shot marker for this image (`artifacts/nat-069/native-attempt-loader-diag-xnu-ne2-usb-used.json`) does not exist.
* The registry steps of the run: in the same window the agent opens `native` citing this file with `lab.py project permit`, claims NAT-070 under its own session name, runs the driver, then `task done NAT-070` while `native` is open and closes `native` again.

## Scope

Exactly one image: `loader-diag-xnu-ne2-usb` — NAT-067's `loader-diag-xnu-ne1-usb` (the loader, the stub, the USB log chain, the run-on at checkpoint 21, the same kernel, the same ADT, the same 16635-byte probe-init ramdisk) with **one change to the
kernel command line: the tag and one appended boot-arg**. The name has the same length as NAT-067's on purpose; the loader Image therefore differs from the one that ran in NAT-068 only in five immediate words that carry the boot id and the image name
(`test_nat069.py`, `Payload`); the XNU payload differs from NAT-067's only in the command-line field at offset 0x48 (11 bytes: one tag digit and ` e1sdisp=2`); the ramdisk is byte-identical.

* RECOVERY SHA-256 `5abd894377a46bf67dcd17b494ef548944ee6201eea583b17a56f26a48c5b0de` (100663296 bytes, `artifacts/nat-069/package-001/loader-diag-xnu-ne2-usb/recovery.img`, the file the driver reads; 19634 4 KiB pages differ from the stock RECOVERY).
* Packaged `Image.payload` (loader + XNU payload + ADT + ramdisk) SHA-256 `192de4b60fc690f7bcd1f4cf45d75f224e1c39f6e70961015e56634e6ec84ac0`, 21878704 bytes at offset 2048.
* Loader-only `Image` SHA-256 `dd0f4812559749b9571329b766f67441872ee23ed8375b2fbdbcc3ef41edb42f` (307200 bytes; NAT-067's was `5c11c7477bb2dd285b5081bbeb01ce97bf0cc1725d0c41b8b3cbef707a13a99e`).
* XNU payload (`SWEETXNU`) SHA-256 `a969f7d22d05de170b32ff649e8c6a43684219fca503a3ec41cbdee5ebe56a2b`, 21571504 bytes (`build.json` `nat065_payload`; the key keeps NAT-065's name and describes this image), built by the
  pinned `mkpayload.py --ramdisk` from the NAT-020 inputs pinned in `build.json` `nat065_pins` (base `payload.bin` `071bc632f7af0a6aa9b11a679c1d5a951ee80943be11669326949d0725caf544`, `kernel.no-storage`
  `7ceda59bdbedba4d32b80c319e35ec51fe766cf61daa648f80a0c42bbca3e407`, `e1s.adt` `1ef36896e28d30ebd76e94b2f2c4074ae75f5cf860360d9c6b401673ab2dbd0e`, `mkpayload.py`
  `50c043e4033ceea682bd20134b5283c1abec51985d49609a3bce5ea0a4013ed7`, `mkinit.py` `2200a8b3225ffc42cbec33747d74fc3562012fb5a2882b8ab5795d453a90ce03`). The ramdisk is NAT-065's probe init (`docs/procedures/nat-065/src/probe-init.S`),
  a Mach-O of 16635 bytes, SHA-256 `b3decc846877fb1de608fcd2734e9c3cb5d2d4ed9e3388bf99d303a45e4761a6`.
* Built by `docs/procedures/nat-069/build.py` (SHA-256 `ee6dff26b71c750c1b4c58e2df1a2ebc5616e9ef7d3592bbb813be037d3c3c64`), which loads NAT-065's `build.py` (`f2f964c068efa17f988752dee547d72dd1b0eaaec0d1344e924f8b13bf7698d8`) and replaces three values (the same mechanism as NAT-067's `build.py` `bbc882c282fd4543f46981e35c178b9e1e0d4e6bf45528f0b53c02dd19c68230`);
  packaged by NAT-047's wrapper of NAT-044's `package.py` (`artifacts/nat-069/package-001/package.json`, SHA-256 `ddf8f4e5f3d0f15f55c1a2e9913841573edbba3a0e5063a56a2816046ca0c56d`, and the per-image record `loader-diag-xnu-ne2-usb/package.json`, SHA-256 `42155be0eba12c8a98bd25c9686e6103638a574c064129b01e808316bbf24af9`). Driver `session_nat069.py`
  (`70ddbee120323cc1908c659f1aae7f5e8046a1f94379f1712f1343c1fab824c9`, derived from NAT-067's `937978d2bc10e680139e15a97eb605c2f29c0c55a8f757721d51daea352332c4` by `derive.py` `b1f46131b98601b19821c40a483349856c97bbd3ef3883aa9fd912c9d796f952`), analyser `analyze_nat069.py`
  (`af7b00b88e18822ae9497dd3177bc3547293bcf3ad2dbd4c88abbf4729b101bb`, a wrapper over NAT-065's `analyze_nat065.py` `b4b9d2f9440aa354dd2c8d0f1c99fe328669d92a763f4fdc3ea22e49a72c5569` and NAT-062's `analyze_nat062.py` `32343921482250dd40bcfaf960bb05cac9697a3d1a7f86213e0402efa27af551` plus the display reading). The loader sources (NAT-036/041/045/047/052/059/062) are those of decisions 0027 and 0028, unchanged.
* **Change in the kernel command line** (exactly, 237 bytes, under the 256-byte field):
  `rd=md0 e1sufs=0 e1sufs_probe=0 ufsrw=0 ufs_write=0 sweethw=0 e1s.hold=0 nat_attempt=NAT069-md0 debug=0xc serial=3 cpus=1 keepsyms=1 -v loader_return_after=8 launchdsuffix=release cs_enforcement_disable=1 e1stouch=0 e1sbattery=0 e1sdisp=2`.
  Against NAT-067's line (the one that made PID 1 run in NAT-068): `nat_attempt=NAT067-md0` becomes `NAT069-md0`, and ` e1sdisp=2` is appended. `e1sdisp` is parsed by `e1s_display_probe()` of the pinned patch
  (`references/s24-port/xnu/e1s/patches/0010-e1s-display.patch`, SHA-256 `8aed03f1544d1b4920dfe702c93b96de603ca2ab555a85c550bec4b2698af033`): the default 1 prints the framebuffer report (what NAT-068 saw), 2 additionally runs `e1s_display_pipeline()`.
* Stop list, deadline reset, the 83 s watchdog, the engine service windows and the `KL` dumps at the last stop and at the return: exactly as in decisions 0026, 0027 and 0028.

Sequence (the protocol of 0021-0028 and of the NAT-069 driver `session_nat069.py --image loader-diag-xnu-ne2-usb`): gates (this file naming both hashes and decision 0019, the registry incl. NAT-063..069 done, the udev rule, the collector self-test,
the device checks, the watcher self-test); one-shot marker; full-image write to RECOVERY (`/dev/block/sda18`) only; full readback; the USB event watcher and the NAT-041 collector (pyusb venv python) started detached and confirmed running; one `adb reboot recovery`;
the run; then restore of the pinned stock RECOVERY (SHA-256 `96620b8bbb6ed871690069d646f5b91039be86811f26371728209b29d3babf67`) with the NAT-013 tool and the pyusb venv python on a device whose iProduct is `SAMSUNG USB` (never `SEC_UPLOAD`),
full-hash readback and an Android check. A failure after the write and before the reboot restores stock and does not reboot. No retry.

What the image does, in order: exactly as 0028 up to `devfs_kernel_mount`. **New on hardware:** immediately after `devfs_kernel_mount` (before the PMIC init) `e1s_display_probe()` prints the framebuffer report and then, because `e1sdisp=2`, maps seven display register
windows with `ml_io_map` and **only reads** them (a static check of the patch source, `test_nat069.py` `Kernel`: the function's only calls are `ml_io_map`, `e1s_display_read` — one 32-bit load — and `printf`; no store through any mapped pointer; every offset lies inside its window) and prints
the values. Afterwards the run is NAT-068's: the touch and battery drivers return early, `load_init_program` execs the project's probe as PID 1, it prints its two lines, exits with status 81, the kernel panics and returns the log.

## Device access granted (and nothing else)

As in decisions 0026-0028 (the PMU window, `pd_hsi0` window, CMU_TOP reads, CMU_HSI0, SYSREG_HSI0, USB control/PHY, DWC3 and the 111-operation ladder — none added by the loader — plus what the kernel's own code does after checkpoint 21: EL1 system registers,
the TLB and caches, RAM inside the loader's window, and whatever MMIO the kernel maps and touches). **New relative to 0028: read-only 32-bit loads (a few dozen) from these physical windows**, mapped by the kernel with `ml_io_map` as device memory:

| window | physical base | size mapped | what is read |
| --- | --- | --- | --- |
| DECON0 main | `0x19100000` | `0x4000` | four instances at `0x1000` steps: version, frame counter, global control, operation mode |
| DECON0 windows | `0x19110000` | `0x10000` | start/end position and secure control of up to 16 windows |
| DECON0 window control | `0x19130000` | `0x10000` | the enable word of 16 windows |
| DMA0 (RDMA) | `0x19900000` | `0x8000` | four channels: enable, input control, source width/height/stride, base address |
| DSIM0 | `0x190B0000` | `0x300` | version, four link status words, MIPI/D-PHY status, clock control |
| DSIM1 | `0x190C0000` | `0x300` | the same eight words |
| DCPHY0 | `0x190E0100` | `0x700` | PLL status (`+0x40`) and master clock lane control (`+0x300`) |
| DISP_SS | `0x19021000` | `0x1000` | DPU_MIPI_PHY_CON (`+0x08`) |

The register layout is the one the pinned patch assumes (offsets from the UI-007 derivation of the DECON0/DPP boot window from pinned Samsung source); it is not a Samsung-documented map and was never executed on this phone. **Not known, and the reason this is a run:** whether these blocks are
clocked and powered in the state the loader leaves. A read of a gated block can come back as a synchronous external abort (the kernel panics through its normal path and the log returns, as with NAT-066's GPIO abort), as an asynchronous SError (also a panic, possibly later), or hang
the bus so that nothing returns until the 83 s watchdog resets the phone. No display register is written. The bound is the 83 s watchdog, the loader's deadline reset, the 8 s `loader_return_after`, and entry-point stubs for the UFS code (NAT-020).
No storage device and no partition other than RECOVERY is written by the loader, and the kernel's code is not claimed unable to touch a block device. The host opens only USB 1209:0001 and reads `/sys/bus/usb/devices`; the NAT-013 restore opens the Download Mode device.

## Pass/fail, fixed in advance

Observation is by the host only (collector archive under `artifacts/nat-070/` and the USB event log; no camera, nothing for the owner to do), judged by `docs/procedures/nat-062/analyze_nat062.py` (the chain) and `docs/procedures/nat-069/analyze_nat069.py` (the NAT-065 `root` reading and
the `display` reading), **both unchanged after the run**. The kernel's text is written to a local file by the analyser (`--log-out`) and checked for personal data before anything of it is committed.

* The chain verdict is judged as in decisions 0026-0028 (27 `CK` notes, `KL` dump at the last stop, the kernel's own return, the second dump, `HOLD`, no drop, no exception).
* **PASS (this run's question): chain PASS and `display.fork` is a complete reading** — one of `scans-loader-framebuffer`, `rdma-reads-framebuffer-decon-idle`, `scans-other-buffer`, `pipeline-idle`, `decon-running-no-enabled-rdma`. The fork is the finding;
  it is taken to the decision named above, together with the numbers in `display.decon`, `display.windows`, `display.rdma`, `display.dsim`, `display.dcphy`.
* `root.outcome` is reported next to it: `probe-ran-to-exit` is expected (NAT-068 reproduced with the probe unchanged). Any other outcome is a finding (a regression caused by the extra reads, or a different fault) and is analysed before anything else is attempted; it does not by itself cancel a PASS of the display question.
* Informative, not PASS: `cannot-map` (`ml_io_map` refused a window; the refused window is the finding), `pipeline-partial` (the read stopped or the text was cut: the last parsed line is the finding), `framebuffer-only` (the boot-arg was not honoured), `no-display-text`.
  An abort or SError note with `esr/elr/far`: the values are the finding; symbolicate with the pinned kernel's symbol table (as in NAT-066) to name the window.
* A hang (no kernel return, the dumps empty, the phone reset by the watchdog at about 83 s): undetermined for the display question; it says that one of the seven windows is not safely readable in this state. The next step is then a bisection image reading one window per run, and the
  decision above waits for it.

A result other than PASS is evidence, not a reason to run again.

## Not granted

Any other image or partition, a second run, any write to a display register or any other MMIO, MMIO from the loader beyond the above, ACPM/SMC calls from the loader, GPU bring-up, kexec, flashing anything but RECOVERY, GPT, EFS, keys, erase/factory reset, boot chain changes, and any use of `sudo`
or the udev rule by the agent. The boundary of decision 0002 is unchanged: Android, apps, settings, accounts and user data stay intact. This run does not authorise driving the panel, changing what it shows, or leaving the kernel running.

## Known limits disclosed

* Host tests and source review only for the new part: the display register reads have never run on this phone. **Unknown, each with the check that resolves it (this run):** whether the seven windows are readable in the loader's power/clock state; what the registers contain;
  whether the register layout the patch assumes matches the silicon; the other limits of decision 0028 (the timed `loader_return_after=8` return and a PID 1 that stays alive are still untested: NAT-071/NAT-072).
* **The kernel runs unobserved**, as in decisions 0026-0028. A hang, an abort, a reset or a `SEC_UPLOAD` / automatic restart are possible outcomes; the 83 s hardware watchdog ended the loader phase in NAT-068 (reset at +83.9 s, Download Mode at +87.7 s, no owner action). If the phone comes back to
  Android by itself, the driver's `--restore` is the same restore; Download Mode by keys is the fallback. NAT-051: a debugfs `clk_summary` read once sent this phone through `SEC_UPLOAD`; never repeated.
* A pass says: the display engine's registers, read once by the payload kernel, had these values. It does not say that the panel shows the framebuffer, that the kernel can draw frames the panel presents, that Apple's launchd or any Apple userland runs, and says nothing about the GPU.
  The synthetic readings in the host tests are rendered from the patch's format strings and are not measurements.
* Host-test evidence: `docs/procedures/nat-069/evidence.json`.

## Owner's standing authorisation (no run-specific confirmation is recorded)

No answer from the owner about this particular image exists, and none is asked for. The owner's standing statements are recorded in decisions 0025 and 0026: on 2026-11-12 the owner wrote "яже говорил что ты можешь без этого хапроса х сам запускать САМ БЕЗ ЗАПРОСА ЗАПУСКАЙ"
(verbatim, typos included; in English: "I already said you can launch without this question, launch it YOURSELF WITHOUT ASKING"). That statement is read as covering runs of this kind (one native image per decision file under the protocol of decision 0019, written only to RECOVERY and
restored from the pinned stock image). It does not widen the list of what is not granted above or the boundary of decision 0002; each run still gets its decision file naming its hashes, which the driver requires. For this run the agent first tries to launch without asking
and asks only if the launch is refused.

## Promotion checklist (draft only; delete this section when promoting)

* Check every hash in this file against `artifacts/nat-069/package-001/package.json` / `build-001/build.json` with `sha256sum` before promoting (NAT-069's `evidence.json` records them).
* The driver's gate needs the RECOVERY hash, the Image.payload hash and the words `decision 0019` in the promoted file.
