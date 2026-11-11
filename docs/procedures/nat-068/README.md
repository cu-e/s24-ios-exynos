# NAT-068: native run of `loader-diag-xnu-ne1-usb` (decision 0028): the payload kernel ran the project's PID 1 on the phone

Evidence kind: **native-device**. Image and driver: NAT-067 (host-test). Decision 0028 (`docs/decisions/0028-nat067-loader-diag-xnu-ne1-usb-single-run-2026-11-12.md`, commit ea2fd85) was committed before the run.

## Result in one paragraph

The host computer received, by itself and with no camera, the whole chain again (analyser verdict **PASS**: 27 stop notes, the kernel's own return, its 23768-byte log in 249 records, HOLD, no drop, no exception) and the kernel text
shows that **PID 1 ran**: with the e1s touch and battery drivers switched off by boot-arg, `bsd_init` completed (`bsd_init: done`), the kernel printed `load_init_program: attempting to load /sbin/launchd`, exec'd the 16635-byte project probe that mockfs
serves from the md0 ramdisk, the probe printed `*** SWEET userspace: init running as PID 1 ***` and `SWEET probe: done, exiting` on the console (both lines reached the host), slept 1 s and exited with status 81 = 0x50 + PID 1. The kernel then panicked
with `initproc failed to start -- ... (signal 0, exit status 81 )`, which is the designed end of the probe run. `root.outcome` is `probe-ran-to-exit`: decision 0028's pass rule is met. This is the first user-mode process that the payload kernel has run on this S24 in this project's runs
(the probe is the project's test init, not Apple's launchd).

## What happened (host clock, UTC, 2026-11-11)

* Decision 0028 committed (ea2fd85) before the run; `native` opened citing it; NAT-068 claimed; preflight `ready-read-only`; battery 84 %. One launch: `session_nat067.py --image loader-diag-xnu-ne1-usb --out artifacts/nat-068/run-001 --execute`
  was not refused. RECOVERY (`/dev/block/sda18`) written and read back (`ae946b4b...2552d`), watcher and collector started before the single `adb reboot recovery` at T0 = 22:11:18.01.
* The phone left Android at T0+0.6 s; 1209:0001 enumerated at +26.7 s; it disappeared 57.2 s later (the loader's software deadline reset, +83.9 s); Download Mode (`04e8:685d`, iProduct `SAMSUNG USB`, bus 5 address 105) at +87.7 s, no owner action.
* Restore: `restore_stock.py restore --bus 5 --address 105` (pyusb venv python, one session) -> `awaiting-readback`; Android back on ADB with `sys.boot_completed=1` at about 22:13:36; `check_android.py`: recovery hash equals the pinned stock (`96620b8b...`), user data directories present;
  `assess`: pass (PIT validated, upload acknowledged, session end, reboot confirmed, Android booted, readback matches). Data, apps and settings were not touched.
* Collector: one boot of this image, 433 frames, 431 records, `dev_seq` contiguous, 0 drops, 0 faults, 1517 transfers, manifest `complete-received-stream` (184957 bytes); analyser run after both processes had exited (360 s windows).
* Slip, recorded for the record: while looking up options I ran `check_android.py --help`, which has no help flag and wrote its read-only Android check to a file named `--help` in the repository root (outcome pass, nothing on the phone changed);
  I deleted that stray file and ran the check again with the proper path. Both runs only read properties over ADB.

## What the kernel's own text shows (`run-001-kernel-log.txt`, sanitized; stamps are the kernel's, about 2.4 % inflated)

* The loader's first dump at checkpoint 21 was again 0 bytes; everything below comes from the second dump, taken at the kernel's return (reason 0, `x3=0`, note n=28): the panic path reached `loader_return()`, as in NAT-063 and NAT-066.
  The timed `loader_return_after=8` path is still untested.
* From 48.36 s on the kernel's clock: `bsd_init` calls up to `bsd_autoconf`, `Added memory device md0/rmd0 ... for 0000000000008000`, `BSD root: md0, major 1, minor 0`, `vfs_mountroot`, `VFS_ROOT`, `devfs_kernel_mount` (as in NAT-066), then the e1s display,
  ACPM, PMIC, keys drivers, **`e1s-touch: disabled (e1stouch=0)` and `e1s-battery: disabled (e1sbattery=0)`** (the abort of NAT-066 did not happen), `redwood-audio`, `siginit`, `bsd_utaskbootstrap`, `mountroot_post_hook`, `bsd_init: done`.
* Then `Serial keyboard started`, the VM swap subsystem (no swap file: no storage, expected), `load_init_program: attempting to load /sbin/launchd` at 48.649 s, and `pid 1 exited -- no exit reason available -- (signal 0, exit 81)` at 49.666 s:
  1.02 s on the stamp clock, which fits the probe's 1 s `select` (the analyser's `init_run_s` is 1.027). The kernel then tried to write a core of pid 1 (`failed to open core dump file ... error 2`: no filesystem to write to, expected) and panicked in
  the way NAT-064 predicted for an init that exits.
* The two lines the probe wrote reached the host, above the kernel message buffer in the same dump, via the image's console ring (`e1s-log: image-owned console ring, 1023 KiB`).

## Established, not established

* Established (native-device): the loader's ADT rebase put the ramdisk where the kernel expected it **and the parts of it that were executed are intact** (the probe printed its two lines and returned the status 0x50 + PID; the whole 16635-byte file was not checksummed on the phone); mockfs mapped `/sbin/launchd` to the raw Mach-O; the kernel exec'd an ad-hoc-signed Mach-O with `cs_enforcement_disable=1`
  (and, for `rd=md0`, without a root-auth step in the way); the thread scheduler, system-call entry/exit (`open`, `write`, `getpid`, `select`, `exit`), the timer (a 1 s `select` returned) and the console path worked; PID 1's console text reaches the host;
  with `e1stouch=0 e1sbattery=0` nothing else in `bsd_init` faulted; the log chain works with this payload (PASS).
* Not established: that the touch and battery drivers work (they were off by design; the touch driver's GPIO defect is still in the patch); the timed `loader_return_after=8` return (this run returned through the panic path again) and a PID 1 that stays alive
  (nothing in the log chain shows text while the kernel keeps running: the host sees the log only at the return); anything about the display other than the driver's report of the loader's framebuffer; the GPU; that Apple's launchd or any Apple userland runs.
  The probe is the project's test init and a QEMU/unicorn run of it is not hardware evidence.

## Files

`run-001-kernel-log.txt` (sanitized by NAT-066's `sanitize_run.py`: the builder account in the kernel version string, the ECID and the two UUIDs replaced, the binary stackshot tail cut), `run-001-analysis.json` (analyser output without the dump texts),
`run-001-usb-events.jsonl` (the watcher's log), `evidence.json`. The raw archive and the unsanitized log stay in the gitignored `artifacts/nat-068/`; the device inventory in the gitignored `devices/local-2026-11-12-nat068.json`.
The `device_id`/boot name in the analysis is the loader's per-run generated id (it differs between runs), not a hardware serial.

## Next

The question after "does PID 1 run?" is how a user-mode program shows something while it stays alive and how it reaches the display: see the tasks created after this one (NAT-069 onwards in the registry).
