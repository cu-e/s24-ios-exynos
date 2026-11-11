# NAT-066: first native run of `loader-diag-xnu-md0-usb` (decision 0027)

Evidence kind: **native-device** for what the phone sent; the attribution of the panic to a function is **source-review** (symbols of the pinned kernel + the driver patch), not yet re-measured.

## Result in one paragraph

The host computer received, by itself, the whole chain again (analyser verdict **PASS**: 27 stop notes, the kernel's own return, its 22994-byte log in 241 records, HOLD, no drop, no exception). The ramdisk reached the
kernel and became the root device: `Added memory device md0/rmd0 ... for 0000000000008000`, `BSD root: md0, major 1, minor 0`, `vfs_mountroot` and `VFS_ROOT` returned, `devfs_kernel_mount` ran, and the e1s display, ACPM, PMIC
and key drivers initialised. **PID 1 did not start.** The kernel panicked with a data abort in the e1s touch driver (`_e1s_touch_init`, called from `bsd_init`) before `load_init_program`; `root.outcome` is `other-panic`.
Decision 0027's pass rule for the run's question (`probe-ran-to-exit`) was **not** met; the task's own acceptance (one run under the protocol, host receives the kernel text, restore verified) is.

## What happened (host clock, UTC, 2026-11-11)

* Decision 0027 committed (08b75e8) before the run; `native` opened citing it; NAT-066 claimed; preflight `ready-read-only`; battery 84 %, 31.5 C. One launch: `session_nat065.py --image loader-diag-xnu-md0-usb --out artifacts/nat-066/run-001 --execute`
  was not refused. RECOVERY (`/dev/block/sda18`) written and read back (`c6f4a6e4...f34d`), watcher and collector started before the single `adb reboot recovery` at T0 = 21:37:37.29.
* The phone left Android at T0+3.6 s; 1209:0001 enumerated at +18.9 s; it disappeared 57.1 s later (the loader's software deadline reset); Download Mode (`04e8:685d`, iProduct `SAMSUNG USB`, bus 5 address 102) at +80.0 s, no owner action.
* Restore: `restore_stock.py restore --bus 5 --address 102` (pyusb venv python, one session) -> `awaiting-readback`; Android back on ADB at about +132 s, `sys.boot_completed=1`; `check_android.py`: recovery hash equals the pinned stock (`96620b8b...`);
  `assess`: pass (PIT validated, upload acknowledged, session end, reboot confirmed, Android booted, readback matches). Data, apps and settings were not touched.
* Collector: one boot of this image, 425 frames, 423 records, `dev_seq` and frame sequence contiguous, 0 drops, 0 faults, 2014 transfers, manifest `complete-received-stream` (174050 bytes); analyser run after both processes had exited.

## What the kernel's own text shows (`run-001-kernel-log.txt`, sanitized; stamps normalised by 1/1.024)

* The loader's first dump at checkpoint 21 was again 0 bytes (the live `kprintf` -> `loader_log` path is empty at that point); everything below comes from the second dump, taken at the kernel's return (reason 0, `x3=0`): the panic path
  reached `loader_return()`, as in NAT-063. The timed `loader_return_after=8` path is still untested.
* From about 40.27 s on the kernel's clock: `bsd_autoconf`, the 100 ms `!BSD` wait (the project's patch for `rd=md*`: 40.469 -> 40.593 is about 0.1 s real), then
  `Added memory device md0/rmd0 (01000000/0D000000) at FFFFFFF008974000 for 0000000000008000` (the ramdisk's 0x8000-byte vm size, at a kernel virtual address), `BSD root: md0, major 1, minor 0`,
  `bsd_init: vfs_mountroot`, `bsd_init: calling VFS_ROOT`, `bsd_init: calling devfs_kernel_mount`.
* Then the e1s drivers: `e1s-display: framebuffer 1080x2340 ... phys 0xfa200000` (the loader's framebuffer, sample words `0xffffffff`), `e1s-acpm: ... channel 2 queues are outside SRAM`, `e1s-pmic: ACPM is not available; PMIC stays untouched`,
  `redwood-touch: e1s platform; redwood hardware drivers are disabled`, `e1s-keys: watching volume-up at 0x12850064`.
* Then `panic(cpu 0 caller 0xfffffff007a7d6b8): Kernel data abort. at pc 0xfffffff0074a1444, lr 0xfffffff0074a1428`, `esr 0x96000005` (translation fault, level 1, a read at EL1), `far 0x00000000110300e4`, `x8 0x00000000110300e0`.
  No `SWEET userspace` banner, no `initproc` line: `load_init_program` was never reached.

## Why it panicked (source review; not re-measured)

* `pc` = `_e1s_touch_init + 0x174` and the frame above it is `_bsd_init + 0xa58` (symbols of the pinned `artifacts/nat-020/build-003/kernel.no-storage` via its Mach-O symbol table; the thread is `kernel_bootstrap_thread`).
* `far` is `E1S_GPP9_DAT` (`E1S_PERIC1_GPIO` 0x11030000 + 0xe4) and `x8` is `E1S_GPP9_CON` (+0xe0) in `references/s24-port/xnu/e1s/patches/0003-e1s-touch.patch`: `gpio_rd(vm_offset_t reg)` dereferences its
  argument directly, and `e1s_touch_init` passes those physical-address macros (`pin_set(E1S_GPP9_DAT, ...)`) instead of `gpp9 + 0xe4`; the `ml_io_map`ped bases `gpp9`/`gpa1` are computed and never used. A physical address is not mapped in the
  kernel's address space, hence the translation fault. This is a defect of the driver patch in this configuration, not of the loader, the ramdisk or the root path.
* The driver honours the boot-arg `e1stouch=0` (`e1s-touch: disabled`) and returns before touching anything. The battery driver (`e1s_battery_init`, later in `bsd_init`) maps its GPIO block with `ml_io_map` before use; its boot-arg is `e1sbattery`.

## Established, not established

* Established (native-device): the loader's ADT rebase put the RAMDisk property where the kernel could use it (the kernel configured `md0` over 0x8000 bytes at a kernel VA and made it the BSD root without a panic); `vfs_mountroot`
  returned and `VFS_ROOT` and `devfs_kernel_mount` ran; the kernel keeps running through the e1s display/ACPM/PMIC/keys driver init; the log chain works with a different payload (PASS, 22994 bytes).
* Not established: that the ramdisk **bytes** are intact at that address (mockfs has not yet read the Mach-O: that happens at exec); that mockfs maps `/sbin/launchd` to the raw Mach-O; that exec of an ad-hoc-signed init is permitted
  with `cs_enforcement_disable=1`; that PID 1's console text reaches the log; that `e1stouch=0` is sufficient (further drivers may fault after it); the timed return.

## Files

`run-001-kernel-log.txt` (sanitized: the builder account in the kernel version string, the ECID and the two UUIDs replaced, the binary stackshot tail cut, `sanitize_run.py`), `run-001-analysis.json` (analyser output without the dump texts),
`run-001-usb-events.jsonl` (the watcher's log), `evidence.json`. The raw archive and the unsanitized log stay in the gitignored `artifacts/nat-066/`; the device inventory in the gitignored `devices/local-2026-11-12-nat066.json`.

## Next

NAT-067 (host): the same image with `e1stouch=0` (and `e1sbattery=0`, a read-only driver that also touches GPIO) on the command line: no kernel rebuild, only the command-line field; decision 0028; NAT-068 would be its single run. The question stays the same:
does PID 1 run?
