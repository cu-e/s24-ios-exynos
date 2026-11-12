# NAT-074 design addendum: layout of the big-window loader variant

Evidence kind: **source-review**. Read from the NAT-065 build tree (`artifacts/nat-065/build-001/loader-diag-xnu-md0-usb/source/`, gitignored; the loader chain is NAT-020 build-003 + NAT-022/026/044/047/052/059/062/065 patches) and the project's `IOKitBSDInit.cpp`. Nothing here ran on the phone. This file supplements the registry acceptance criteria of NAT-074 (the registry cannot amend them); the strategy document is `docs/strategy/2026-11-12-root-delivery.md`.

## What the loader does today (line numbers of the NAT-065 `loader.c`)

* `choose_window` (l. ~340-400): each `/memory` node separately; gap size capped by `MAX_WINDOW` = 512 MiB (l. 324, 353); window = top of the largest gap.
* `p->mem_size` (payload header, from the ADT `/chosen/dram-size`, 0x20000000 in `e1s.adt`): rejected above 4 GiB (l. 526); `win_size = min(win_size, p->mem_size)` (l. 550).
* Kernel segments go to `win_base + (vmaddr - virt_base)`; `kernel_end` is the end of the last segment including the ramdisk segment that `mkpayload.py` appends (l. 563, 664).
* ADT is copied to `adt_pa = kernel_end`; `boot_args` at the next 16 KiB boundary; `topOfKernelData = boot_args + 16 KiB` (l. 700-735). **The kernel treats everything above `topOfKernelData` as free memory.** Anything that must survive (md0's ramdisk today) sits below it, as a payload segment.
* `adt_rebase_ramdisk` adds `win_base - p->phys_base` to the phys word of `RAMDisk`/`RAMDisk1` (l. 713); `adt_set_dram` / `adt_set_pram` write the dram range and the PRAM at the top of the window (1 MiB below the end).
* The whole window is zeroed with the MMU off in 16 MiB steps with a UI flush each (l. 624-652), segment BSS is zeroed per segment (l. 669), and the whole window is cleaned by VA (l. 774).

## Layout for the big root (first-run values)

```
win_base                                                       win_end = win_base + 4096 MiB
| kernel segs | md0 probe (16 KiB pad) | RAMDISK1 RESERVE (2,475,720,704 B, not cleared, no file bytes) | ADT | boot_args | ... free ... | PRAM |
                                       ^ kernel_end (16 KiB aligned)                                    ^ topOfKernelData
```

* `RAMDisk1` property in the ADT = `{ rd1_pa, 2,475,720,704 }` where `rd1_pa` is the 16 KiB-aligned `kernel_end` seen by `mkpayload.py` (payload virtual layout), rebased by the loader like the existing ramdisk. `mkpayload.py` has no reserve-only mode: it needs a small patch (`--ramdisk1-reserve SIZE`: add the property and advance `kernel_end`, add no segment). Record base SHA and licence of the pinned file as for every local patch.
* The loader adds the reservation to `kernel_end` for placing the ADT and boot_args (`adt_pa = kernel_end + reserve`), so `topOfKernelData` lies above the reserved range. The payload's own segment table never mentions the reserve, so nothing is copied or zeroed there.
* `p->mem_size` (ADT `dram-size`) becomes 4 GiB in the payload build; the loader's `MAX_WINDOW` becomes 4096 MiB; `choose_window` sorts and merges touching `/memory` nodes before the gap search.
* Clear: `[win_base, win_base + 256 MiB)` and the top 2 MiB (PRAM), never the reserve. Everything the kernel allocates later is zero-filled by the VM on allocation (source-review claim, confirmed or refuted by NAT-075). The clear is bounded by arithmetic: 258 MiB at 75 MB/s is about 3.6 s.
* Clean by VA over the whole window (about 0.7 s for 4096 MiB at the measured 6.1 GB/s).
* Deadline: the NAT-044 `deadline_s` becomes a hard cap constant; `nat044_tick` also pets the watchdog every 30 s only while the cap has not passed. NAT-020's `inspect_binary.py` forbids the `s5e_wdt_pet` symbol; the variant needs its own, narrower rule (the symbol is allowed exactly once, called from `nat044_tick`, and the cap constant is checked) so the property is still enforced.

## Why md1 and not a bigger md0

* md0 stays exactly what ran in NAT-068, so a failure of the new run is attributable to the window/reserve/pet changes, not to a changed root device.
* The root is a different kind of object from the boot ramdisk: PID 1 is Mach-O served by mockfs from md0; the delivered APFS is a data volume for a later kernel mount.
* `RAMDisk1` support exists in the pinned `mkpayload.py` and in the project's `IOKitBSDInit.cpp`; it has never run on the phone.

## Host tests this design needs (NAT-074 acceptance)

1. Window harness (nat-006) on the real FDT with the variant `choose_window`: base 0x8fe400000, 4096 MiB; the old rule still gives 0x9de400000 / 512 MiB for comparison; a gap under 256 MiB is rejected; touching nodes merge, a hole between nodes does not.
2. Layout arithmetic in a Python model that reads the built payload header and the ADT: reserve inside the window, 16 KiB alignment, ADT and boot_args above the reserve, `topOfKernelData` above it, PRAM inside the window, nothing overlapping the loader image, framebuffer or payload.
3. Instruction-level model (unicorn, as NAT-044) of `nat044_tick`: pets at 30 s steps before the cap, stops pets at the cap, fires the reset path at the cap; a mutant run over the comparison direction, period, cap constant and clear sizes.
4. Binary check: the built loader contains exactly one call to `s5e_wdt_pet`, from `nat044_tick`.

## Consequences for the sibling tasks (their registry text predates this design)

* NAT-075 says "big md0": read it as "big md1 next to the unchanged md0"; the observable is `Added memory device md1` with the 16 KiB-aligned size, while md0 and the probe lines are the NAT-068 baseline.
* NAT-077 and NAT-078 say `/dev/rmd0`: read `/dev/rmd1`. The probe stays the md0 PID 1 and hashes `/dev/rmd1`.
