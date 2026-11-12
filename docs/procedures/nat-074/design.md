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

## Implementation addendum (2026-11-12, after the variant was built; supersedes the passages above where they differ)

Evidence kind stays **source-review** for the design and **host-test** for the tests below. Files: `make_variant.py` (loader hunks), `patch_mkpayload.py` (payload), `build.py` (the chain), `test_nat074.py` (window, 13 tests), `test_model.py` (compiled code, 28 tests), `mutants.py` and `mutants_model.py`.

* **Clear plan is three spans, not "low 256 MiB".** The low-256-MiB design would have missed the area directly above `topOfKernelData` (ADT, boot_args, the first kernel allocations). `nat074_clear_plan()` returns `[win_base, kernel_end − reserve)`, `[kernel_end, +64 MiB)` (cut where the top span starts) and `[mem_end − 2 MiB, mem_end)`. For the built payload: 73.48 + 64.00 + 2.00 = **139.48 MiB** (0x8fe400000–0x902d7c000, 0x996684000–0x99a684000, 0x9fe200000–0x9fe400000), about 1.9 s at the measured 75.3 MB/s. The loader's progress counter `zero_bytes` therefore ends at 146,259,968 — the NAT-075 analyser must expect that number, not 4096 MiB. The registry text "clear ≤ 64 MiB" and the 4908 MiB figure are superseded by this and by the 4096 MiB cap (the window is limited by the loader's own `mem_size > 4 GiB` refusal, not by the free gap).
* **The reserve sits in the payload's own `kernel_end`.** The first draft said the loader adds the reservation; what is built is simpler: `mkpayload74.py --ramdisk1-reserve N` advances `kernel_end` past md0's pages by N and adds the `RAMDisk1` ADT property with no segment, so the loader's existing placement (ADT at `kernel_end`, boot_args on the next 16 KiB) puts `topOfKernelData` above the reserve with no loader change. Host check: `PayloadLayout` (RAMDisk1 `{pa, 2,475,720,704}`, adjacent to md0's 0x8000, no segment touches it, payload file < 128 MiB, header `mem_size` 4 GiB, the ADT's own `dram-size` untouched, `adt_off`/`adt_size` 8-aligned).
* **`adt_size` needs NAT-022's fix.** Two added RAMDisk properties are 104 bytes, leaving the ADT 4 bytes off a multiple of 8, which the loader refuses. `build.py` applies the checked `fix_payload.fix` (zero padding, no segment overlap), as it was applied to the NAT-020 payload (14060 → 14064).
* **The NAT-020 binary rule applies only inside `recovery_guard`.** `inspect_binary.py` forbids `s5e_wdt_pet`/`s5e_wdt_disarm` calls only there; nothing in it needs a "narrower rule". The variant keeps that rule as is (tested: `recovery_guard` has one `bl s5e_wdt_arm` after `mov w1,#0x53` and no pet/disarm) and adds a whole-binary rule: exactly one `bl s5e_wdt_pet`, inside `nat074_pet()`, which is entered by tail-branch only from `nat044_tick` and `nat074_final_pet`, and `nat074_final_pet` is called once from `loader_main`.
* **The NAT-047 margin rule cannot hold for a cap the pet outlives; it is replaced, not dropped.** `build.py` requires watchdog 83 s (read from `guard.c`), pet period + 20 s ≤ 83 s, pet < cap ≤ 600 s, and restores NAT-047's rule after the build. The first run uses cap 150 s, pet 30 s.
* **What the pet can and cannot show.** `hold_seconds()` does not poll `nat044_tick`; `mk_hold` after the kernel returns (`loader_return_after=8`) does. A run in which the kernel hangs therefore pets in `mk_hold` until the cap and then takes the unchanged NAT-044 reset path (INFORM2, INFORM3 = DOWNLOAD, CMD 0x8, REBOOT 2). A refused reset (read-back mismatch) leaves the watchdog unpetted, so it still ends the run with SEC_UPLOAD after at most 83 s: the pet never keeps a run alive beyond its own reset path. The pet's effect on the S24's windowed watchdog (`timer[4] = 2·count`) is **unobserved**: NAT-075's observable is "returns to Download Mode at ~150 s" (pet works) versus "SEC_UPLOAD at ~83 s" (pet insufficient).
* **Tests as built.** `test_model.py` runs the compiled `loader.elf` of the variant in unicorn: `nat074_clear_plan` against an independent model on a grid of layouts and on the built layout; the real `recovery_guard` then the real `mk_hold` loop with the NAT-044 register model (pets at 30/60/90/120 s, none at or after 150 s, reset sequence unchanged, no pet after a refused reset, `nat074_final_pet` before/after the cap, unarmed, armed==0 with a cap, watchdog that failed to arm); capstone checks of the call graph and of the cache-maintenance site count against the NAT-065 loader (`dc civac` count equal); `struct nat044` offsets compiled by the C compiler; the pure rules of `build.py`; the payload layout. It is a model without caches, MMU or real memory attributes.
* **Not covered by any host test (stated so the hardware run is read correctly).** `loader_main`'s own layout check (`reserve layout does not fit the window`) is compiled but not executed on the host; `build.py check_layout` states the same facts about the built payload, and a failed check would stop the loader before XNU with that text. WDT behaviour, 16 KiB-page boot with a 4 GiB window, the kernel's mapping of a 2.3 GiB reserve, host→device USB rate and an APFS mount are hardware unknowns for NAT-075 and later tasks.
