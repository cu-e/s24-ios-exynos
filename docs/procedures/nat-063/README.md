# NAT-063: first native run of `loader-diag-xnu-run-usb` (decision 0026), 2026-11-11 20:25 UTC

Evidence kind: **native-device**. The XNU kernel on the S24 (SM-S921B/e1s) was allowed to run **freely past C checkpoint 21**, through `machine_startup`/`kernel_bootstrap`, the
startup tasks and the start of BSD, until it stopped by itself with a panic; the host computer received the kernel's own log text by USB without a camera and without owner action.
NAT-060 ended at checkpoint 21 (a hold by design); this run is the first observation of the kernel beyond it.

## What ran

* Decision `docs/decisions/0026-nat062-loader-diag-xnu-run-usb-single-run-2026-11-12.md` (decision 0019 protocol), committed (45d25fe) before any device access; the owner's confirmation
  ("яже говорил что ты можешь без этого хапроса х сам запускать САМ БЕЗ ЗАПРОСА ЗАПУСКАЙ") was recorded and committed (cb39822) before the run.
* Image: RECOVERY SHA-256 `a618b98ccbbc655ca20db2dfac033274582ccdc89d8f8b6128a635b8d48392ff` (NAT-062 `package-001`; `Image.payload`
  `c7863c99b2448dd1ea518a83dcfa90cb4e405b6445ddf3d4718e2c9be7e0aadd`), written to `/dev/block/sda18` only, full readback equal; one `adb reboot recovery` at
  2026-11-11T20:25:43.963Z (T0). Battery 84 %, 30.0 C.
* Driver `docs/procedures/nat-062/session_nat062.py --image loader-diag-xnu-run-usb --out artifacts/nat-063/run-001 --execute`, analyser `analyze_nat062.py` (run after the collector
  and the watcher had exited). Watcher started 0.3 s before T0, collector before T0, both before the reboot request.
* Registry steps in the same window: `native` opened citing decision 0026, NAT-063 claimed, `task done NAT-063` while `native` was open, `native` closed.
* Restore: the phone re-enumerated by itself as 04e8:685d `SAMSUNG USB` (never `SEC_UPLOAD`) at T0 + 79.7 s (NAT-044 deadline reset); NAT-013 `restore_stock.py restore` (venv python,
  one session) returned stock RECOVERY (`96620b8b...`); `check_android.py` read back the full-hash match, `boot_completed`, user 0 and the user-data directories; `assess` = pass with all
  stages (`session_end_confirmed`, `reboot_confirmed`, `android_booted`, `recovery_readback_matches`). Android was back at T0 + 124.6 s. No data, app or setting was touched.

## What the host observed (source: `run-001-usb-events.jsonl`, frame receive times in the archive)

| T0 + | Event |
|---|---|
| -0.3 s | watcher started; phone present as 04e8:6860 `SAMSUNG_Android` |
| +3.7 s | phone left the bus |
| +18.7 s | **1209:0001 appeared** (the NAT-041 monitor) |
| +36.3 s | first kernel stop note `CK n=1` |
| +38.4 / +38.8 s | `n=5` (asm checkpoint 5) / `n=6` (C checkpoint 11, MMU on) |
| +45.4 s | `n=22` (C checkpoint 16); `n=23` at +45.8 s (C checkpoint 17, after `arm_vm_init`) |
| **+47.4 s** | `n=27`: C checkpoint 21, final-stop bit; then `KL begin why=1 len=0 ...`, `KL end why=1 recs=0 bytes=0` at +47.43 / +47.44 s |
| **+49.1 s** | **`n=28`: the kernel handed control back by itself (reason 0, `x3=0x0`) 1.7 s after the last stop** |
| +49.15 .. +52.0 s | `KL begin why=2 len=19510 head=8192 tail=11318 gap=0 ...`, 204 records, `KL end why=2 recs=204 bytes=19510` |
| +53.0 s | `HOLD stage=0x51 code=0x223e` |
| +75.8 s | 1209:0001 left the bus (NAT-044 deadline reset, 57.1 s after enumeration, as in NAT-058/060) |
| +79.7 s | 04e8:685d `SAMSUNG USB` (Download Mode) |

## What the host received

* One boot in the archive (boot-id tail = the image's FNV-1a-64), 386 frames, 384 records, `dev_seq` and frame sequence contiguous, 0 drops, 0 faults, 0 unread bytes; the manifest says
  `complete-received-stream`, 157879 bytes, 0 errors; analyser verdict **PASS** (`run-001-analysis.json`): *one boot of loader-diag-xnu-run-usb: 384 records, the 27 stop notes (n=1..27, final
  checkpoint 21), the kernel's log at the last stop (0 bytes long), the kernel's own return (reason-0 note n=28, x3=0x0), its log (19510 bytes long: 8192 + 11318 sent in 204 records, 0 not sent),
  then HOLD; no drop, nothing unread, no exception*.
* The reconstructed log (`run-001-kernel-log.txt`) is the sanitized copy: the account name inside the kernel version string, the ECID and the two UUIDs of the panic header are replaced by
  placeholders, and the binary stackshot data that ends the panic buffer is cut (it is kept in the gitignored `artifacts/nat-063/run-001/kernel-log.txt`). The analysis copy in this directory
  has the dump texts removed for the same reason.

## What the kernel did (from its own message buffer; `run-001-kernel-log.txt`)

Established by the text the phone sent (native-device):

* After `arm_init` the kernel carried on by itself: `kprintf initialized`, `Serial mode specified: 00000003`, `initialize_screen` (framebuffer `0xFA200000`, 1080x2340 panel geometry: `w=0x438 h=0x924`),
  then the interrupt controller: **`gic: v3, distributor ..., cpu 0's redistributor ..., virtual timer on PPI 27`** (distributor and redistributor mapped at kernel virtual addresses), `pmap_startup`, `vm_page_bootstrap`
  (110393 free pages), the kernel map layout and every zone range (`zone_init: map VM/RO/GEN0..GEN3/DATA`), `VM bootstrap done`.
* Kernel services: ATM, log queues/OSLog/Firehose, telemetry, the clutch scheduler, BANK, the Mach IPC tables, `kdp_core`, `Initializing serial KDP`, NVRAM (size 8192 bytes),
  `ulock`, minicrypto, the MAC framework with stand-in AMFI/Sandbox/vnguard, `PMRD` power management events, `GenericARMPE: platform "D22AP"`, `GenericARMCPU: cpu 0 (phys id 0x0) registered`.
* BSD: `bsd_init` calling `kauth_init` ... `vfsinit`, `mbinit` (64 MB pool), `dlil_init` (**kernel threads were created and each was scheduled at least once**), Skywalk self-tests (all PASSED),
  `loopattach` (`lo0` attached), `ether_family_init`, `net_init_run`, `inittodr`, `setconf`, then `cpu_start() cpu: 0` and
  `MiniIOMobileFramebuffer: display 1125x2436 on a panel of 1080x2340 (4320 bytes per row)`.
* Then a **panic**: `IOFindBSDRoot: specified root memory device, md0, has not been configured @IOKitBSDInit.cpp:841`. The boot-args in the panic header include `rd=md0` (and `cpus=1`,
  `serial=3`, `debug=0xc`, `loader_return_after=8`); no ramdisk exists for `md0`, so BSD cannot find a root device. The panic ran the kernel's own `loader_return()` (the timed return was set for 8 s but the
  kernel returned 1.7 s after the last stop, so the 8-second timer was **not** what returned it). The panic text also shows `Panicked task ... pid 0: kernel_task`, `33 threads` and
  `** Stackshot Succeeded **`: the kernel built a stackshot of its 33 threads on this phone.
* No exception stop, no `BAD_TTBR0`/`BAD_STATE` hold and no hardware watchdog bite: the kernel ran 1.7 s of host time after the last stop, handed back, the loader dumped and held, and the
  NAT-044 deadline reset ended the run as designed.

## What is not established

* **Timer interrupts.** The kernel reports a virtual-timer PPI and scheduled threads, but cooperative thread switches and the counter-based clock do not need timer interrupts; whether the GIC
  delivered one is not visible. The `loader_return_after` timer never came due (the panic came first), so the thread-call timer path is untested.
* **`pe_arm_map_interrupt_controller: failed to find the interrupt-controller`** and `pe_arm_init_debug: failed to find cpu-debug-interface` were printed (the generic code looked for nodes the ADT
  does not provide) although the GIC was found and mapped by another path; the effect is unknown.
* **Live console text.** The first dump (at checkpoint 21) is empty: `loader_log` held no live `kprintf` text then, and the second dump begins with the kernel's *message buffer* and *panic buffer*
  which `loader_return()` appends. Whether the live `serial_putc_crlf` -> `loader_log_putc` path is silent with `serial=3` or whether the text only reaches `loader_log` when `loader_return()`
  appends the message buffer is **not** resolved by this run (all 19510 bytes sent are those two buffers).
* The kernel's clock shows about 3.3 s from the first message buffer line (`36.88`) to the panic; the timestamps carry an unnormalised microsecond field in places (`39.1000184`), so they
  are not used as timing evidence. The host receive times above are the timing evidence.
* Anything the kernel did to peripherals other than the GIC, the timer and the framebuffer notes above. The kernel's access to MMIO was unbounded by review; no unexpected side effect was seen
  (Android returned normally, nothing was touched outside the RECOVERY slot). Repeatability: one run.
* Whether the display or GPU could be driven: the kernel only printed the framebuffer geometry.

## Next obstacle

The kernel needs a **root file system / ramdisk for `md0`** (or boot-args without `rd=md0` that let BSD finish without a root device) to get past `IOFindBSDRoot` into the `launchd` start-up,
console output and then the display/GPU path. That is host work on the payload (cmdline or a ramdisk placed in memory by the loader and described in the ADT/boot-args) plus another run of the same kind;
see the task cards created after this run.

## Files

`run-001-kernel-log.txt` (sanitized text), `run-001-analysis.json` (analyser output without dump texts), `run-001-usb-events.jsonl` (the watcher's log), `evidence.json`. The raw archive, the full
analysis, the driver output and the restore reports stay in the gitignored `artifacts/nat-063/`; their hashes are in `evidence.json`.
