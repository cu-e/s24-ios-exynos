# NAT-036: the resumable C-checkpoint image `loader-diag-xnu-ckpt3` (host work)

Evidence category: **source-review and host-test**. The image was built on the host and packaged into a RECOVERY image on the
host (hashes only); nothing was flashed, run or sent to the phone. The phone is in Android with the stock RECOVERY (verified
after run 009). Decision 0018 has not been requested; its question text is `decision-0018-question.md` (a draft, not a record).

Run 009 (decision 0017) was the first C-level XNU execution on the S24: `arm_init`, `cpu_data_init` and `PE_init_platform` ran to
C checkpoint 11 and the return stub held there. NAT-035 specified, in the instruction-level model, how a stub gives the kernel back
from a C stop, and found that the loader as built writes a boot-CPU `reg` the kernel's `cpu_init` rejects. NAT-036 turns both into
code and tests it as far as the host can: the loader fix, a compiled resumable stub with a selectable stop list, a one-frame pass
report that fits the display budget, and the candidate images.

## What the image does

`loader-diag-xnu-ckpt3` is `loader-diag-xnu-ckpt2` (NAT-022/NAT-034) with exactly three source changes to `loader.c`
(`test_nat036.py`, `Build`) and four new files; every other source file is byte-identical.

| Arrival at the stub | Action |
|---|---|
| assembly checkpoints 1-4 (`x2 = 2`, `x3 = n`, MMU off) | resume at the site's continuation with `slot[2] = n + 1`, as runs 008 and 009; the pass draws **one** frame instead of two |
| assembly checkpoint 5, MMU off | read and **capture the kernel's `TTBR0_EL1`** (validated: a table base, bits 11:1 clear, not zero); resume at `site5 - 28` with `slot[2] =` the first C stop, as run 009 |
| C checkpoint `n` in the list, MMU **on** (loader_jump's private `TTBR0`) | clear `loader_return_entered` by PA, store the next stop into `slot[2]`, restore the kernel's registers, SP and SCTLR, install the captured `TTBR0` through the kernel's own `_set_mmu_ttb`, return through `loader_jump`'s early-return epilogue |
| the last stop of the list | hold: the full report (`NAT036_MASK_FINAL`, bit 13, is set) |
| anything else (wrong order, wrong state, an exception `x2 = 1`, `x2 = 0`, a captured `TTBR0` that is not a table base, a C stop with the MMU off) | hold with the NAT-031 mask bits plus 12 (bad `TTBR0`), 14 (bad state); nothing is resumed |

The stop list is checked at install time (`nat036_list_ok`): non-empty, in the payload's program order `10, 11, 30-35, 12,
40-44, 13, 14, 15, 16`, nothing after checkpoint 16. Stops 17 and later are refused because the kernel's `TTBR0` changes in
`arm_vm_init` (NAT-035 section 2) and the stub only has the value captured at checkpoint 5. The installer also reads, from the
copied kernel image and before writing anything, that `loader_jump` (27 words), `_set_mmu_ttb` (4 words) and the flag byte are what
NAT-035 analysed, and refuses an image whose stub straddles a 2 MiB block (`loader_jump` maps one block around the stub).

### The loader patch (base: the NAT-020 build-003 loader source, GPL-2.0)

`loader.c:687` (after NAT-022's `patch_loader.py`): `adt_set_boot_cpu_mpidr(adt_pa, p->adt_size, (uint32_t)gi.mpidr)` becomes
`(uint32_t)(gi.mpidr & 0xffff)`. `gi.mpidr` is the raw `MPIDR_EL1` (bit 31 is RES1); the kernel's `ml_get_cpu_number_local`
compares the ADT value with `MPIDR_EL1 & 0xffff`. `patch_loader3.py` applies it together with the install-block change, each
with an exact-match replacement that fails if the text is not found. `AdtMask` compiles the patched expression and evaluates it, then
runs the kernel's own `ml_get_cpu_number_local` in the model: with the patched value the lookup returns CPU 0, with the loader
as built it reaches `_Assert` (NAT-035 4(b)).

### The resume sequence (`ckpt3_stub.S`)

The prologue and the assembly tail are NAT-034's text (`test_the_prologue_and_the_assembly_tail_are_nat034s_text`: the same
instructions apart from the symbol names and the one `cbnz x1, 2f` that selects the C tail). The C tail, with the MMU **off**
until the `msr sctlr_el1, x11` (only an `isb` and the final `br` follow it): load `x18..x28`, the arrival SCTLR (`x11` slot), the kernel SP and the three words of
`struct nat036_cres` (`x0` = captured `TTBR0`, `x30` = `loader_jump + 0x4c`, the gadget `_set_mmu_ttb`) from loader memory; `mov
sp, x10; dsb sy; tlbi vmalle1; dsb nsh; isb; msr sctlr_el1, x11; isb; br x12`. Nothing is loaded after the `msr`: with the MMU on
only the stub's 2 MiB block is mapped (`test_the_c_tail_loads_everything_it_needs_before_the_mmu_comes_back_on`). The `br` goes to a
kernel virtual address (TTBR1, unchanged by `loader_jump`); `_set_mmu_ttb` runs `dsb ish; msr ttbr0_el1, x0; isb; ret` and returns
into the epilogue `ldp x29, x30, [sp, #0x30]; add sp, sp, #0x40; ret`, i.e. to `loader_checkpoint`'s caller.

### The report

One frame per pass (kind 13, `MK_C3_PASS`: `data = (arrivals & 0xff) << 8 | (last & 0xff)`), a full redraw, a DECON0 kick and one
dwell. Because the kernel passes the stops in program order, the `(arrivals, last)` of any later pass accounts for every earlier
stop (`decode3.stops_missed`), so a camera that missed a frame loses nothing. The hold repeats the full report; the values the run
is about come first (stage, pass, regs, mask, list length, then the kernel's `SP`, its own `TTBR0`, `x1`, `x0`, then SCTLR, TTBR1,
VBAR, TCR, boot id), so a run cut off by the watchdog still shows them. An early exception (`x2 = 1`) shows ESR/ELR/FAR in place of
the register block. `decode3.py` reads the frames with NAT-022's decoder, unchanged.

## Display budget (computed from the frame counts; measured costs from runs 006-009)

The first pass starts about 27.5 s after the first frame (the five assembly passes of run 009 ended about 41 s after the run
started, at 2.7 s per two-frame pass); a frame costs 1.35 s (1.2 s dwell, measured) and the loader's watchdog ends the display at 83 s.
The kernel's own time between stops is not counted (a few thousand to about a million model steps, microseconds to milliseconds).

| Stop list | arrivals | passes end | `SP`/`TTBR0`/`x1`/`x0` all shown by | SCTLR/TTBR1/VBAR/TCR shown by | margin to 83 s |
|---|---|---|---|---|---|
| 17 stops (`11,30-35,12,40-44,13-16`) | 22 | 55.9 s | 77.5 s | 80.2 s | 5.5 s / 2.9 s |
| 9 stops (`11,30,35,12,44,13,14,15,16`) | 14 | 45.1 s | 66.7 s | 69.4 s | 16 s / 13 s |

One report round is 26 frames (35 s): neither list leaves room for a second round, and the 9-stop list keeps a margin that
absorbs a slower draw. `Ckpt3Marker.test_display_budget_*` pins both rows. These are budgets, not measurements of this image.

## What the host tests show (`test_nat036.py`, 56 tests, 54 without `NAT036_LONG=1`, which adds the two long chains)

Run with an interpreter that has capstone and unicorn and `zig`, `cc` on PATH (`make check` does not run this file).

* **Words**: the 27 + 4 hard-coded instruction words, the three addresses and the epilogue offset equal the payload's bytes and its own
  symbol table; the flag byte is zero in the copied image.
* **Ckpt3Host** (host build, alignment sanitizer, real payload bytes): the list rule against an independent statement for every
  list of up to three entries over a 25-symbol alphabet; every install refusal (list, block, each word table, flag, the NAT-031
  site checks) writes nothing; the decision table for the whole walk, the TTBR0 validation (eight bad values), every unexpected
  arrival holds, a C stop before checkpoint 5 or out of order holds, a repeated last stop never resumes; the two stores write exactly
  one aligned word and exactly one byte.
* **C3Chain** (the compiled stub, `ckpt.c` and `ckpt3.c` compiled with the loader's flags, run by the NAT-033/035 model on the
  payload from its entry): assembly stops 1-5, the cp5 resume, then 11, 30-35 and 12 resumed by the compiled stub itself; the kernel's
  state at the last `loader_jump` entry (all system registers, SP, NZCV, DAIF, `x0`, `x1`, `x18..x30`) and the RAM outside the
  loader equal a run of the same loader that was never stopped, and the stop-by-stop log (arrival counts, last checkpoint, SCTLR M
  clear at assembly stops and set at C stops, captured `TTBR0`) is what the stub reports.
* **C3LongChain** (`NAT036_LONG=1`; 116 s for the 17-stop list, 272 s for the 9-stop candidate list under load): all stops to checkpoint
  16 with every register the tail does not restore (`x2..x30`) overwritten with junk and tainted after each decision: equal to an
  uninterrupted run, no read of a clobbered register, RAM identical, DAIF all-masked at every entry, one `loader_jump` entry per stop.
  The 9-stop run is a different run of the kernel from the 17-stop one (checkpoints 31-34 and 40-43 are passed without stopping). The model needs the three ID registers `cpu_init` reads (`ccsidr_el1`,
  `clidr_el1`, `id_aa64dfr0_el1`) assumed 0 from checkpoint 16 on (`Assumed(id_zero=True)`, as in NAT-035); both runs use it.
* **C3Controls**: every restore/set-up instruction of the C tail (13 of them) replaced by a `nop` in turn is detected (translation or
  alignment fault, external abort, or a read of a clobbered register); with `x18..x28` replaced by distinct values at the first C
  arrival (the kernel's own may be equal, which hides a swapped slot) they all come back at the gadget; the stack frame is exactly the
  31 registers plus the SP and no store leaves it. The six barrier/maintenance instructions are not detected: with a model
  that has no caches, TLB or barriers their removal changes nothing (`test_the_barriers_cannot_be_checked_in_the_model` records
  that, instead of claiming a test).
* **AdtMask**, **Ckpt3Marker** (the real `mk_ckpt3_*` against a fake DECON0, decoded independently), **Build** (reproducible twice;
  header and payload; the loader source differs from `ckpt2` in three hunks and every other file is identical; no SIMD register in
  the NAT-036 functions or the stub; `scan_unaligned` finds nothing; the stub, stack, log and `_end` lie in one 2 MiB block at the
  three S-Boot bases seen, `0x800a0000`, `0x80180000`, `0x801a0000`; `_end` < `0x40000`).
* **Mutation check** (`test_support/mutate_nat036.py`, 81 textual mutants of `ckpt3.c`, `ckpt3_stub.S`, `markerlib3.c`, `marker3.h`:
  list rule, install checks, word tables, decision table, the cp5 TTBR0 validation, the two cache-maintained stores, the prologue,
  every slot and instruction of the C tail, every frame of the report). Two partial runs found six weak tests, each closed by a test
  that fails on the mutant (a vacuous block-straddle case, a prologue that kept the C bit, a stack frame one slot too small, `x28`
  restored from the `x27` slot (the kernel's own `x27` and `x28` are equal at the stops, so only distinct injected values show it), the
  kernel `TTBR0` frame piece equal to the `TTBR1` piece in the harness, a pass that did not redraw in full (every `DRAW` event looked
  right; only the framebuffer shows stale bands)). Last full run: 81 mutants, 80 killed and that last one surviving; after its test
  was added it and the five others that had once survived were re-run: all killed (`artifacts/nat-036/logs/mutation-full.log`,
  `mutation-rerun-survivors.log`). The final text checks (cache-maintenance order of the two stores, the 1..4 routing, the stub's
  barrier sequence) pass. The mutation "list: NULL accepted" is killed by a segfault of the host test process, not by an assertion. The
  checks cannot see anything the model does not model: removing a `dsb`, `isb` or `tlbi` changes nothing there.

## What is not established

* **Everything on the phone.** The compiled C tail has never run on hardware. Run 009 proved the prologue, the MMU-off stores and
  the assembly resume; the C tail adds the MMU turn-on with the private table, the branch to a kernel virtual address and the kernel's
  `_set_mmu_ttb`. The model has no caches, no TLB, no barriers, no exceptions and no real memory attributes.
* **Caches and the TLB.** The flag and `slot[2]` stores use `dc civac` before and after (as the decision-0017 store that worked); the
  tail issues `tlbi vmalle1` (local) between the MMU-off loads and the `msr`. A stale entry for the loader's block after the kernel's
  `TTBR0` is back is harmless only if the kernel never touches those addresses; unverified on hardware.
* **DAIF** is not restored by any primitive; the model has it all-masked at every stop and the stub assumes it.
* **The panic path** (`PE_panic_hook`, `loader_return`, `psci_smp_stop_others`, `redwood_*_quiesce`) is still not analysed and may
  write device registers. With the ADT fix the model passes `cpu_init`, but other hardware differences (the real ID registers, the
  real MPIDR, the counter, the framebuffer geometry, timers) are assumed in the model (`Assumed.assumed`) and a different value could
  still reach a panic.
* **Checkpoints 17-21** are refused in the list: the model blocks on `cnt v0.8b` before 17 and the kernel's `TTBR0` changes after
  `arm_vm_init`.
* **The captured `TTBR0` is a model value until the phone reports it.** The stub validates the shape and the report shows it
  (`MK_C3_KTTBR0_*`); the model's value `0x9e15ae000` sits next to the measured `TTBR1` `0x9e15af000`.
* A pass frame says the kernel's code ran up to that checkpoint; it does not say XNU boots.

## Files

* `src/ckpt3.h`, `src/ckpt3.c`, `src/ckpt3_stub.S`: the decision code (host-buildable with `NAT031_HOST`), the C entry, the stub.
* `src/marker3.h`, `src/markerlib3.c`: the kind-13 frame and the two report routines (`markerlib3.c` includes NAT-022's `markerlib.c`
  unmodified and is compiled instead of it).
* `patch_loader3.py`, `build.py`: the loader patch and the image build (`--stops` selects the list).
* `decode3.py`: the report decoder (wraps NAT-022's `decode.py`).
* `test_nat036.py`, `test_support/{host_mk3.c,nat036_mock.c,nat036_mock.ld,mutate_nat036.py}`.
* `decision-0018-question.md`: the draft question; `evidence.json`: provenance, commands, exit codes, hashes.

Run: `<venv>/bin/python -I docs/procedures/nat-036/test_nat036.py` (61 s; `NAT036_LONG=1` 441 s on the loaded host) and
`<venv>/bin/python docs/procedures/nat-036/test_support/mutate_nat036.py` (many minutes; indices select mutations).
