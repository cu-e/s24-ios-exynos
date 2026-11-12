# Root delivery without Android partitions (NAT-073, 2026-11-12)

Evidence kind: **source-review plus host arithmetic**. Numbers come from existing records of this S24 (the runtime device-tree facts, the loader's and the kernel's own logs of the NAT-068 run), from the loader and kernel sources in the tree, and from the measured size of the root image (IOS-010). Nothing here ran on the phone for this task. Items marked *(assumption)* are scenarios, not measurements. Reproduce the numbers with `python3 -I docs/procedures/nat-073/budget.py docs/procedures/nat-073/budget.json` (13 tests: `docs/procedures/nat-073/test_budget.py`).

## 1. Result

The root is the 2,475,712,512-byte `system.apfs` (2.31 GiB, IOS-010). It cannot ride in the RECOVERY image (96 MiB slot; the loader also rejects payload file ranges above 256 MiB) and no Android partition may hold it, so it must reach RAM from the host over the project's USB link before the kernel starts. Reading the loader and the NAT-068 log turned up three constraints that were not on the board:

1. **The kernel's RAM window is capped at 512 MiB in the loader** (`MAX_WINDOW`), and the log shows exactly that window (`win size=0x20000000`). A 2.31 GiB root cannot live in it. The device tree offers a free, contiguous 4908 MiB (0x8cb800000-0x9fe400000) if the loader merges the three touching 2 GiB memory nodes, which it does not do today.
2. **The kernel selects 16 KiB pages only when `memSize` exceeds 1 GiB** (`osfmk/arm/arm_init.c`). The NAT-068 kernel counted 131072 pages (110384 free + 20688 wired) = 512 MiB at 4 KiB: it ran with 4 KiB pages. The iPhone X userland is built for 16 KiB pages, so a window above 1 GiB is needed for that reason alone, before the root is considered.
3. **The loader clears the whole window with the MMU off at about 75 MB/s** (7.1 s per 512 MiB, UI flush included): 68 s for 4908 MiB, longer than the 57 s deadline and the 83 s watchdog allow. The clear must shrink, and a CPU copy or CPU checksum of GiB-scale data with the MMU off is out; the data has to arrive by device DMA straight into its final place.

**Recommendation (one path, two steps):** loader-staged RAM root over a **bulk-OUT endpoint** added to the proven NAT-041 DWC3 engine, with DMA into the window, a **bounded receive phase** (hard cap on the NAT-044 deadline reset, watchdog pet only before the cap), and a **large window with a small clear**. Do the window and watchdog work first, on a boot that needs no USB change (section 5, NAT-074/075), because it removes the unknowns every later step depends on (16 KiB pages, a 2.3 GiB md0, the first loader-side watchdog pet, the moved deadline). Then add the receiver (NAT-076/077). The kernel USB block device (option B) is the fallback if the measured bulk rate or the RAM left over turns out insufficient; it is not the first step.

## 2. RAM budget (acceptance 1)

| Fact | Value | Source |
| --- | --- | --- |
| DRAM in the runtime device tree | 8033 MiB in 7 nodes; the three nodes at 0x880000000, 0x900000000, 0x980000000 touch (6144 MiB) | `devices/e1s-fdt/2026-11-10/runtime.facts.json` (local) |
| Android MemTotal | 7.06 GiB | DEV-001 |
| Reserved blocks around the gap | below it, 0x880000000-0x8cb800000 (1208 MiB) holds cp_rmem, cp_rmem1, abox-rmem, gnss_rmem, log_platform/log_first/log_kevents, dnc-fw-mem and sec_rdx_bootdev, with free fragments that are each under 256 MiB (the budget tool finds none above that size); above it, el2_earlymem at 0x9fe400000 + 28 MiB | same |
| **Free contiguous gap** | **4908 MiB, 0x8cb800000-0x9fe400000** (one node alone gives at most 2048 MiB) | `budget.py` |
| Window the NAT-068 loader chose | 512 MiB at 0x9de400000, the top of the first node's gap; replaying the loader's `choose_window` rule on the device-tree facts gives the same base and size | loader log, `budget.py` |
| Kernel view of that window | 110384 free + 20688 wired pages = 131072 = 512 MiB at 4 KiB; wired = 81 MiB | kernel log |
| Payload that the loader copied | 11 segments, 26,705,920 bytes, 6.2 s for the copy phase including log lines and UI | loader log |
| Root | 2,475,712,512 B = 2361 MiB. A multiple of 4 KiB but **not of 16 KiB** (remainder 8192): pad to a 16 KiB multiple because the loader aligns the RAMDisk to 16 KiB | IOS-010 |

What the window must hold: the root as wired physical memory (md0 is physical memory, not paged), kernel text/data and its tables (81 MiB wired at 512 MiB; budgeted 120 MiB, an estimate that scales with memory), the page cache copies of the root files that get read (a read through the md0 device copies into the cache, so a touched page exists twice; no swap, no compressor backing store), and everything the iOS processes allocate.

| Window | Left after root and 120 MiB kernel *(estimate)* | Verdict |
| --- | --- | --- |
| 2048 MiB | -433 MiB | does not hold the root |
| 3072 MiB | 591 MiB | too tight for launchd, backboardd, SpringBoard and the page cache of the shared cache |
| 4096 MiB | 1615 MiB | possible; margin unknown |
| **4908 MiB (whole gap)** | **2427 MiB** | proposed: leaves room, and the root size can grow |

The size of the iOS working set is **not measured**; the margins above are arithmetic, and the first run with the real root answers whether they suffice. The root itself is a measured size, not an estimate. The donor's own comment puts the same file set at 2.5 GB with zlib (IOS-009 marks that as not reproduced; IOS-010 has since built 2,475,712,512 B). Pruning or a stronger stored format could shrink it, but the shared cache is one unit that dyld maps whole, and no compression ratio was measured for this task: not a delivery decision.

## 3. Time budget and the three clocks (acceptance 2)

Three independent bounds act on every native run of the current image family. The first draft of this document named only the watchdog; the run records show that the software deadline is what ended NAT-058 to NAT-068.

| Bound | Constant | Where | What it does when it fires |
| --- | --- | --- | --- |
| Loader **software deadline** (NAT-044 `nat044_tick`, polled from the loader's wait loops) | `deadline_s` 60 (NAT-058); the phone left the bus 57.1-57.2 s after USB enumeration in NAT-058/060/063/066/068; the build refuses `deadline_s > wdt_s - 20` | `docs/procedures/nat-044` | writes the Download request to the PMU and resets: **`SAMSUNG USB` (Download Mode) at +80-88 s with no owner action**, which is what NAT-013 restore needs (NAT-046) |
| Hardware **watchdog** | armed once by the loader with 83 s (`s5e_wdt_arm(&w, 83)`); counter 0xffff, divider 128, prescaler 256 at the cited 25.6 MHz = 83.8848 s nominal, not calibrated on the phone | NAT-019/020 `guard.c` | the baseline of NAT-001-009 ended here: **`SEC_UPLOAD` at about +95 s, gone at about +118 s, Download Mode only by the owner's keys** (NAT-046). The failsafe, not the planned exit |
| Kernel **timed return** `loader_return_after` | 8 s in decision 0028; this path has never run (the kernel panicked, which returns through `loader_return()`) | NAT-063/066/068 | returns control to the loader so the log dump and then the deadline reset follow |

The NAT-068 timeline (host clock): left Android at T0+0.6 s, enumerated at +26.7 s, deadline reset at +83.9 s (26.7 + 57.2), Download Mode at +87.7 s. Loader counter (25.6 MHz): zero begin 21.5 s, zero end 28.6 s (7.1 s), handoff 36.2 s; cleaning the data cache over the 512 MiB window took 0.088 s (6.1 GB/s), so about 0.8 s for 4908 MiB. The kernel's own clock reads about 48.6 s at `load_init_program` and PID 1 exits 1.0 s later; NAT-064 notes that kernel stamps cannot be compared with host receive times, so this document does not turn them into an offset. The log is read from the kernel's return dump only: **nothing is visible while the kernel runs**.

USB so far: high speed, EP0 control only, polled by the loader, 1517 transfers for 185 KB in NAT-068, all device-to-host. **No host-to-device throughput has been measured on this phone.** NAT-020's binary check lists `s5e_wdt_pet` and `s5e_wdt_disarm` as forbidden symbols in the loader, so "arm once, never pet" is enforced on purpose. `s5e_wdt_pet` (`src/native/watchdog/s5e9945.c`) is unit-tested against simulated registers in NAT-007 and has never run on the S24: a pet is an untested hardware behaviour and a deliberate change to that rule, to be recorded in the new decision.

Transfer time of 2,475,712,512 bytes at assumed rates:

| Path | Rate *(assumption)* | Transfer | Fits the existing 57 s deadline? |
| --- | --- | --- | --- |
| EP0 control-OUT, pessimistic | 2 MB/s | 1238 s | no |
| EP0 control-OUT, optimistic | 15 MB/s | 165 s | no |
| Bulk-OUT, low | 25 MB/s | 99 s | no |
| Bulk-OUT, donor figure | 28 MB/s | 88 s | no |
| Bulk-OUT, high | 40 MB/s | 62 s | no |

The 28 MB/s figure is the donor's, for another device and controller; the control-OUT range is my bound from 64-byte high-speed control packets, not a measurement. Nothing fits the existing deadline and watchdog, so **delivery needs a receive phase with its own bounds**:

* For the delivery image the 57 s deadline becomes a hard cap on the receive phase (proposed 300 s from enumeration, a constant in the image and named in its decision file). At the cap, the existing reset to Download Mode fires exactly as in NAT-046, so the planned exit keeps the property NAT-013 relies on.
* The hardware watchdog is petted from the same polled loop at most every 30 s and **only while the cap has not passed**. A wedged loop (no polling) lets the 83 s watchdog fire and end in `SEC_UPLOAD`, as the baseline did: the failsafe keeps its known, owner-assisted outcome. If the pet itself does not reload the counter on this SoC, the first run ends the same way. That is a real cost (owner key presses for a restore) and the reason the pet is exercised first in a run with no transfer (NAT-075).
* Worst case on the planned path: the cap plus the reset-to-Download time (about 300 + 30 s). On the failsafe path: 83.9 s after the last pet, then the SEC_UPLOAD behaviour of the baseline.
* A final pet just before the handoff gives the kernel a full period. NAT-071's kernel-side keepalive is separate and still required for any run that outlasts the kernel's boot.

## 4. Options (acceptance 2: what to write, host tests, failure mode)

| | A2 bulk-OUT into the window (recommended) | A1 EP0 control-OUT `WRITE_MEM` | B kernel USB block device | C smaller root, on-demand |
| --- | --- | --- | --- | --- |
| Idea | Loader receives the root over a new bulk-OUT endpoint by DMA into the window before the kernel starts; RAMDisk = {address, length} in the ADT | Same, but over a vendor control request with up to 65535 bytes of data stage | The kernel owns the DWC3 and serves block reads to md-like device; the host answers on demand | Prune the root and fetch the rest lazily |
| Write | A variant of the NAT-041 `usbmon` under NAT-076's own path (NAT-041 is not edited): configuration with one bulk-OUT endpoint, DEPCFG/DEPXFERCFG, TRB ring with two chained TRBs of up to 16 MiB each, XferComplete handling, `rx_bytes`/`rx_trbs`/`rx_errors` in `GET_INFO`; loader receive loop with pet and hard cap; ADT RAMDisk; host sender | One new vendor request on the existing engine: the data stage TRB points at the destination | Port the polled engine to a kernel thread (MMIO mapping, DMA buffers, a block driver, cache coherence with the MMU on), kernel-side watchdog keepalive, request protocol | Root composer (IOS-008, now unscoped) plus B |
| Host-testable | Yes: the NAT-041 model gets the endpoint; the sender is tested against it; the pet and cap against a fake clock | Yes, same model | Partly: protocol and block logic with a fake device; the kernel driver only on the phone | Composer: yes |
| Rate | 25-40 MB/s *(assumption)*, 62-99 s | 2-15 MB/s *(assumption)*, 165-1238 s | on demand, about the working set, unknown | smaller image, same mechanism |
| Failure mode | Short transfer or lost host: the cap fires the NAT-044 reset into Download Mode; a wedged loop falls to the watchdog and SEC_UPLOAD (owner-assisted restore); a corrupt image is caught by PID 1's digest, not by the loader | same | A stall inside the kernel is invisible until the watchdog fires; hardest to diagnose | as B |
| Cost vs value | Moderate; one proven engine extended | Smallest change, rate likely too low | Largest; only needed if RAM or rate fails | Not a delivery mechanism |

Integrity: USB carries CRC-16 per packet. The loader must not read the root back (reads with the MMU off are slow; at the measured write rate a 2.3 GiB read would take about 33 s *(assumption: reads no faster than writes)*). The end-to-end check belongs to PID 1: hash `/dev/rmd0` with the MMU on and print the digest, compared on the host with the image's SHA-256. The loader only reports counters and a head/tail sample.

## 5. Recommendation and first implementation tasks (acceptance 3)

Order chosen so that each run answers one question and nothing waits on the USB receiver for the unknowns that do not need it.

| Task | Scope | What | Done when |
| --- | --- | --- | --- |
| **NAT-074** | host | Loader and image builder: (a) `choose_window` merges touching DT memory nodes and takes the cap from a constant of 4908 MiB class (not a boot-arg); window harness `docs/procedures/nat-006/window_harness.c` extended with the real device-tree facts; (b) clear only the first 64 MiB of the window plus segment BSS (the rest is left to the kernel, which zero-fills pages on allocation; this is a source-review claim to confirm on the phone) and clean the whole window by VA (0.8 s); (c) NAT-044 deadline replaced by a hard cap constant, watchdog pet from the polled loop every 30 s only before the cap, final pet before the handoff, NAT-020's forbidden-symbol rule amended for `s5e_wdt_pet` only in this image and recorded in the decision; (d) ADT `/chosen/memory-map/RAMDisk` = {16 KiB-aligned address, 2,475,712,512 + 8192} while only the 16,635-byte probe PID 1 is physically present at the start of the region; payload header `mem_size`/boot_args `memSize` = the window; kernel boot-args unchanged except the attempt tag | image built reproducibly; harness gives base 0x8cb800000 size 4908 MiB on the device-tree facts and rejects a gap below 256 MiB; static checks show the cap and the pet in the emitted code; decision draft with the pass rule |
| **NAT-075** | native, one run, own decision file | "Big window, big md0, no transfer": does the kernel boot with a 4908 MiB window, advertise 16 KiB pages (pages x 16 KiB = window in `vm_page_bootstrap`), accept a 2.3 GiB md0 and still run the probe PID 1; does the pet reload the watchdog (the run is held past the 83.9 s nominal expiry by the cap of 150 s chosen for this run, then the cap fires the reset to Download Mode); what is the boot time and the wired-page count | host receives the log; `win size`, page count, `Added memory device md0 ... for` the 16 KiB-aligned size, probe lines, pet counter in the loader log; restore and Android check |
| **NAT-076** | host | Bulk-OUT receiver in the NAT-041 engine and model, with tests including seeded defects as in NAT-041, plus the host sender (`tools/ios/root_send.py`: resumable by offset, 8 MiB writes, checks `rx_bytes`) | all engine/model/sender tests pass; mutation run; descriptors and endpoint registers cited to the pinned vendor driver |
| **NAT-077** | host | Probe PID 1 that hashes `/dev/rmd0` (SHA-256) and prints the digest and elapsed time; decision draft for the first delivery run | static Mach-O builds with the project toolchain; digest of a known file read back through the host build of the kernel's mockfs/md path |
| NAT-078 | native | Delivery run: the sender streams the real root; observable: rate, `rx_bytes`, PID 1 digest equals the image's SHA-256 | first measured host-to-device rate; first full-size root in RAM |

Exact loader and boot-arg changes (NAT-074): no new kernel boot-arg; window size, clear size, pet period and hard cap are constants in the loader image and in the decision file; the current deadline path of NAT-044 stays the exit. The command line keeps `rd=md0`; `e1stouch=0 e1sbattery=0` stay until their defects are fixed. NAT-071's kernel-side keepalive is separate and still required for runs that outlast the PID 1 boot.

## 6. Unknowns this document does not close

* Whether the kernel boots with a 4908 MiB window and 16 KiB pages (NAT-075). Static reading shows the page-size rule, not the boot.
* Whether skipping the full clear is safe for this kernel (NAT-075).
* Whether `topOfKernelData` handling is fine with a 2.3 GiB static region ahead of the free pages (NAT-075 reserves the same size without data).
* The host-to-device USB rate of this phone and host controller (NAT-078, or earlier if NAT-076's engine is first exercised with a small pattern).
* The iOS working set against the 2427 MiB margin.
* That the pet reloads the S5E watchdog as the simulated registers say (NAT-075); if it does not, that run ends in SEC_UPLOAD and needs the owner's keys.
* Whether the NAT-044 deadline code can be given a longer cap without touching its reset path (NAT-074 reads `docs/procedures/nat-044`; it does not edit it, it builds a variant under its own path).
