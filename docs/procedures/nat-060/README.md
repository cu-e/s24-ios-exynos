# NAT-060: first native run of `loader-diag-xnu-ckpt4-usb` (decision 0025), 2026-11-11

Evidence kind: **native-device**. On 2026-11-11 the host computer received, by itself and without a camera, the text notes of the XNU kernel's own boot code **past
`arm_vm_init`** on the S24 (SM-S921B/e1s): all 27 stops of the image's list, ending at C checkpoint 21 (the last checkpoint of `arm_init`), then the loader's `HOLD`
record. NAT-058 ended at checkpoint 16, the call before `arm_vm_init`; this is the first observation of the kernel beyond it.

## What ran

* Decision `docs/decisions/0025-nat059-loader-diag-xnu-ckpt4-usb-single-run-2026-11-11.md` (decision 0019 protocol), committed (9724d0a) before any device access; the owner's
  confirmation ("да запцскай я разрешаю запускать их без разрешения окгда угодно если устройство доступно") was recorded and committed (00d5342) before the run.
* Image: RECOVERY SHA-256 `60147f1f6190c688b89ea63ac1f56816e977db692eb3864bf2aaa404ea868dd1` (NAT-059 `package-002`; `Image.payload`
  `3bb6e5d14368ef3627288f44aeff9c00c1e510915395db5988de600402b0af20`), written to `/dev/block/sda18` only, full readback equal; one `adb reboot recovery` at
  2026-11-11T19:02:35.544Z (T0).
* Driver `docs/procedures/nat-059/session_nat059.py --image loader-diag-xnu-ckpt4-usb --out artifacts/nat-060/run-001 --execute`; analyser
  `docs/procedures/nat-059/analyze_nat059.py` (unchanged since NAT-059's commit 6c15454, run after the collector and watcher had exited). Before the run the preflight
  printed `ready-read-only-registry-closed` (every gate except the native permit); the watcher (start at T0 - 0.2 s) and the collector (0.089 s before T0) were running
  before the reboot request. Battery 84 %, 29.6 C.
* Registry steps in the same window: `native` opened citing decision 0025, NAT-060 claimed, `task done NAT-060` while `native` was open, `native` closed.
* Restore: the phone re-enumerated by itself as 04e8:685d `SAMSUNG USB` (never `SEC_UPLOAD`) at T0 + 85.1 s; NAT-013 `restore_stock.py restore` (venv python, bus 5 address 96,
  one session) returned stock RECOVERY (`96620b8b...`); `check_android.py` read back the full-hash match, `boot_completed`, user 0 and the user-data directories; `assess` = pass with all
  six stages. No data, app or setting was touched.

## What the host observed

| T0 + | Event (source: `run-001-usb-events.jsonl`, frame receive times in the archive) |
|---|---|
| -0.2 s | watcher started; phone present as 04e8:6860 `SAMSUNG_Android` |
| +3.5 s | phone left the bus |
| +24.0 s | **1209:0001 appeared**; first frame (boot record) received at +24.0 s |
| +24 .. +41 s | loader text and stage records (`loader_main` .. `pre_jump`) |
| **+41.7 s** | **first kernel stop note `CK n=1`** |
| +44.5 / +44.9 s | `n=5` (the kernel built its table, MMU still off) / `n=6` (C checkpoint 11, MMU on) |
| +51.5 s | `n=22`: C checkpoint 16, the last stop of NAT-058 (now a normal stop: the kernel is resumed) |
| **+51.9 s** | **`n=23`: C checkpoint 17, the first stop after `arm_vm_init`** |
| **+53.5 s** | **`n=27`: C checkpoint 21, final-stop bit (`mask=0x203e`)** |
| +54.8 s | `HOLD stage=0x51 code=0x203e` |
| +81.2 s | 1209:0001 left the bus (the NAT-044 deadline reset, 57.2 s after enumeration as in NAT-058) |
| +85.1 s | 04e8:685d `SAMSUNG USB` (Download Mode) |

## What the host received (`run-001-ck-log.txt`, raw `artifacts/nat-060/run-001/archive/`)

* One boot in the archive (boot-id tail `820ed530d82ad5fe`, the image's FNV-1a-64), 177 frames, 175 records, `dev_seq` and frame sequence contiguous, 0 drops, 0 faults;
  the manifest says `complete-received-stream`, 49240 bytes, 0 errors; analyser verdict **PASS** (`run-001-analysis.json`).
* Banner `NAT047 loader-diag-xnu-ckpt4-usb deadline_s=60 fault=0`, both ladder summaries `err=0`, the eight stage records, then 27 notes `n=1..27` whose checkpoint
  values are exactly the list of the image (`1,2,3,4,5,11,30..35,12,40..44,13..16,17,18,19,20,21`), then `HOLD`.

| n | checkpoint | MMU | SP | `kttbr0=` (TTBR0 given back) |
|---|---|---|---|---|
| 1-4 | asm 1-4 | off | loader SP, then `0xfffffff008060000` | 0 |
| 5 | asm 5 | off | `0xfffffff008060000` | `0x9e15ae000` |
| 6-22 | C 11, 30-35, 12, 40-44, 13-16 | on (`sctlr=0x3454599d`) | `0xfffffff00805fef0` | `0x9e15ae000` |
| **23-27** | **C 17, 18, 19, 20, 21** | on (same SCTLR) | `0xfffffff00805fef0` | **`0x9e2d7c000`** |

* **Established by the notes:** the kernel returned from `arm_vm_init` and ran `patch_low_glo`, `PE_consistent_debug_inherit`, `serial_init`, `kernel_startup_initialize_upto`, the
  console/boot-arg code, `PE_init_printf`, `PE_init_platform`, `ml_map_cpu_pio`, `cpu_timebase_init`, `PE_init_cpu`, `fiq_context_init`, the SecureDT lookups and `early_random`, each
  stop arriving at the host with the kernel's registers at the stop. No exception note and no `BAD_TTBR0` or `BAD_STATE` hold.
* The value the stub read from `_invalid_ttep` after `arm_vm_init` is `0x9e2d7c000`; in the payload file that location holds 0, so `arm_vm_init` really ran and stored the table.
  Stops 23-27 have the same value, as the patch assumed (the assumption "nothing else changes the kernel's `TTBR0` between checkpoints 17 and 21" was not contradicted: the kernel
  carried on from each stop with the given-back `TTBR0` and reached the next).
* SCTLR, SP and VBAR (`0xfffffff007437000`, the kernel's) are the same at every C stop, 6 through 27.
* The kernel code ran with the ADT's `gic` node and `arm-io` ranges in place: whether `PE_init_platform` mapped or touched the interrupt controller is not visible in the notes.

## What is not established

* What the kernel does after checkpoint 21: `arm_init` returns into `machine_startup` -> `kernel_bootstrap`; the payload has no checkpoint there and the loader holds at 21 by design,
  so whether the kernel would continue on its own is untested.
* Anything the kernel did to peripherals between 16 and 21 (the interrupt controller in particular), whether its console output (`serial=3` in the cmdline) went anywhere, display,
  GPU or storage. Repeatability (one run).

## Next obstacle

The kernel's early boot is observed to checkpoint 21. Further progress needs checkpoints (or another observation point) in the code that follows `arm_init`: `machine_startup`,
`kernel_bootstrap`, the startup tasks and the first IOKit steps, in the same payload build with the same resume model; or letting the kernel run on and relying on the loader's
exception vectors and a console path. See the task cards created after this run.
