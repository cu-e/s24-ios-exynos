# NAT-035: resuming the payload kernel from a C-checkpoint stop (host model)

Evidence category: **source-review and host-test**. Nothing was built into an image and nothing was run on the phone.
The phone is in Android with the stock RECOVERY (verified after run 009). Decision 0018 has not been requested.

Run 009 (decision 0017) was the first C-level XNU execution on the S24: the kernel's `arm_init`, `cpu_data_init` and
`PE_init_platform` ran to C checkpoint 11 and the return stub held there. That stop is final: the loader's stub cannot
give the kernel back, so every further observation point costs one phone run. Run 008 had the same problem at
assembly checkpoint 5 and NAT-034 solved it with a resume (`slot[2] = 11`, MMU-off branch to the kernel's own
MMU-enable block). NAT-035 asks the same question for the C stops: what must a stub do to hand the kernel back from
`loader_jump`, and does the kernel then run on as if it had never stopped?

## What is established

### 1. What `loader_checkpoint` / `loader_jump` change (source review + model, anchored on run 009)

`loader_checkpoint(n)` (`0xfffffff00744f3c0`) compares `slot[2]` with `n` and, on a match, tail-branches to
`loader_jump` (`0xfffffff00744f1cc`) with `x0 = 2`, `x1 = n`. `loader_jump` builds a `0x40` byte frame
(`[sp+8]` = original TCR, `[sp+0x10..0x18]` = x0/x1, `[sp+0x30..0x38]` = the caller's x29/x30), sets the byte
`loader_return_entered` (`0xfffffff007d77009`; if it is already 1 the function takes its early-return epilogue at
`+0x4c`: `ldp x29, x30, [sp, #0x30]; add sp, sp, #0x40; ret`), calls `gic_v3_irq_quiesce` (a no-op: `gicd_base` is 0),
writes the private L1/L2 tables and cleans them, masks DAIF, installs the private `TTBR0_EL1` (`tlbi vmalle1`) and
`br x5` to the stub with `x0 = loader_log PA`, `x1 = log length`, `x2 = 2`, `x3 = n`.

Between `loader_jump`'s entry and the stop the model changes only these (loader-equal inputs): `TTBR0_EL1` (kernel
`0x9e15ae000` -> private `0x9e2279000`), the flag byte, `x0..x3`, the frame, `x29/x30`. `TCR`, `SCTLR`, `TTBR1`,
`VBAR`, `MAIR`, DAIF, `x18`, `x19..x28` and SP are unchanged. Run 009 measured on the phone the private `TTBR0`
(`0x9e2279000`), `TTBR1` `0x9e15af000`, TCR low half `0xa51a251a`, VBAR low half `0x7000`; the kernel's own `TTBR0`
was never read on the phone (model: `0x9e15ae000`, adjacent to the measured `TTBR1`).

Where each original value comes back from:

| State | After `loader_jump` | Recovered from |
|---|---|---|
| `loader_return_entered` | 1 | the stub clears it by PA (`dc civac` around the store) |
| `TTBR0_EL1` | private table | captured at the checkpoint-5 stop (MMU off, intact); after `arm_vm_init+0xc18` from the global it loads |
| `TCR_EL1` | written back unchanged (`EPD0` already 0; the original is also in `[sp+8]`) | nothing to restore (low half measured in run 009: `0xa51a251a`) |
| TLB | `tlbi vmalle1` for the private table | the stub flushes once more before the `msr`; a stale entry for the loader's block is the residual risk |
| DAIF | all masked | not recoverable by the stub; the model has it all-masked at every stop reached |
| `gic_v3_irq_quiesce` | no-op (`gicd_base` is 0) | nothing to restore |
| `x0..x3`, `x4..x17` | arguments / scratch | dead across the call (the model poisons them and finds no read) |
| `x29`, `x30` | frame values | the epilogue reloads them from `[sp+0x30..0x38]` |
| `SP`, `x18`, `x19..x28`, `SCTLR_EL1` | unchanged at the stop | saved by the stub on entry, restored on exit |

### 2. The resume sequence (executable specification: `cresume.c_resume`)

The stub is entered with the MMU on, the private `TTBR0` installed and `SP` = the `loader_jump` frame. It
1. saves `SP`, `x18`, `x19..x28` and `SCTLR_EL1` into loader-owned memory (it cannot use the kernel stack with the MMU off);
2. clears `SCTLR_EL1.M|C` (as the run-009 stub does) and draws its report;
3. with the MMU off clears `loader_return_entered` by physical address with `dc civac` before and after (the
   precedent is the `slot[2]` store of decision 0017) and writes the next checkpoint into `slot[2]`;
4. restores `x18..x28`, SP and `SCTLR_EL1` (M|C on; the private table still maps the stub's 2 MiB block);
5. executes `tlbi vmalle1; dsb; isb`, sets `x0` = the kernel's `TTBR0`, `x30` = `loader_jump + 0x4c` and branches to
   the kernel's own `_set_mmu_ttb` (`0xfffffff0074428bc`: `dsb ish; msr ttbr0_el1, x0; isb; ret`) from kernel
   virtual-address code, so the stub's identity mapping is not needed after the `msr`;
6. `_set_mmu_ttb` returns into the early-return epilogue of `loader_jump`, which reloads `x29/x30` from the frame
   and returns to `loader_checkpoint`'s caller in `arm_init`.

The kernel's `TTBR0` is captured by the stub at the **checkpoint-5 stop** (MMU off, value intact) and kept in loader
memory. It is valid until `arm_vm_init` replaces it at `arm_vm_init+0xc18` (a `set_mmu_ttb(*(0xfffffff0071ac3e0) &
0xffffffffffff)` call; `arm_vm_init` precedes checkpoint 17). A stop after that point needs the value read from that
global. The complete set of `TTBR0` writers in the kernel's high text is `_set_mmu_ttb` (callers: `common_start`,
`arm_vm_init`, `pmap_switch_internal`, `pmap_clear_user_ttb`, `pmap_clear_user_ttb_internal`) and `_loader_jump`
(`test_ttbr0_writers`).

### 3. Model results

Model: NAT-030/033 interpreter with the loader-equal inputs of `loader_inputs.py` (section 4a) and `cresume.py`.

* **A resume chain equals an uninterrupted run.** cp5 stop -> resume (NAT-034) -> stops 11, 30, 31, 32, 33, 34, 35, 12,
  40, 41, 42, 43, 44, 13, 14, 15, 16 (17 stops, 1,084,182 steps) against an uninterrupted run to 16 (1,053,360 steps):
  the kernel's state at the last `loader_jump` entry is identical (all system registers, SP, NZCV, DAIF, `x0`, `x1`,
  `x18..x30`), RAM is byte-identical, no read of a clobbered register (the stub's scratch `x0..x17`, `x29`, `x30` are
  filled with a poison value and tainted), and DAIF is "all masked" at every entry. `evidence_runs.py`, about 5 min;
  `test_nat035.py` runs the same comparison for the 15 stops up to 14 (90k steps).
* **Negative controls** (`test_nat035.py`, `NegativeControls`): without clearing the flag, or without the next `slot[2]`,
  the next stop never comes (step limit); without restoring SP the run faults in the epilogue; without the callee-saved
  registers `x19..x28` differ and the kernel reads poison (22 reads in 11 -> 30 -> 31); without `x18` it differs
  (`x18 = 0x3004000` is live); without restoring `TTBR0` (junk value, or the private table left) the entry state
  differs in `TTBR0_EL1` only.
* **`TTBR0` is not observable in this stretch.** With it left private or junk the kernel runs on unchanged through
  checkpoint 31, because nothing between 11 and 16 uses a low virtual address. The restore is a precaution for the
  stops after `arm_vm_init` and for hardware behaviour the model lacks, not something the model shows to be needed.
* **The kernel's `TTBR0` does not map the loader.** The kernel's own `TTBR0` tables (model, at checkpoint 11) have an
  invalid level-1 descriptor for the `0x80000000` range, so after the restore a stale TLB entry for the loader's block
  could only matter if the kernel touched those addresses (it would fault without it). Not tested on hardware.

### 4. Findings that change the plan

**(a) The NAT-030/033 model never had the loader's inputs.** The ADT region was zero, there was no `Video` or
`CommandLine`, `deviceTreeLength` was `0x4000` (the loader writes 13960). `loader_inputs.py` builds them as `loader.c`
does: the payload's ADT patched with the real `adt_patch.c` (compiled with gcc, run in the loader's order: boot-CPU
MPIDR, dram, pram, ramdisk rebase), `boot_args` with Revision/Version 2, `virtBase`, `physBase`, `memSize`,
`topOfKernelData`, `Video`, `deviceTreeP`, `deviceTreeLength`, `CommandLine` after `cmdline_xnu()`, `memSizeActual`.
The ADT SHA-256 in the model is `a4bedc3e2b2f5e3d777c54f206c5196ab8557dc9df56897aba14753d4a5c1df3` (13960 bytes). With
these inputs the model's checkpoint-11 arrival still equals what run 009 measured (`test_arrival_equals_hardware`:
`x0` low 48 bits `0x9e1f90a00`, `x1` 0, `x2`/`x3` 2 and 11, `TTBR0` `0x9e2279000`, `TTBR1` `0x9e15af000`, TCR low half
`0xa51a251a`, VBAR low half `0x7000`; SCTLR `0x3454593d` vs hardware `0x3454599d`, bits 5 and 7 only). The NAT-033
sentence "the model builds boot_args and the ADT as loader.c does" was overstated; it now carries a correction note.
Model-only artifacts of the zero ADT (for example a `brk #0x1206` UBSan trap in `wfe_timeout_configure`:
`timebase_frequency_hz` stayed 0) disappear (`test_kernel_reads_the_timebase_from_the_adt`: the kernel stores the
ADT's 25600000).

**(b) The loader as built will panic the kernel in `cpu_init`.** `loader.c:687` calls
`adt_set_boot_cpu_mpidr(adt_pa, size, (uint32_t)gi.mpidr)`, which writes the **whole** 32-bit register into the boot
CPU's `reg`. The kernel's `ml_get_cpu_number_local` (`0xfffffff0074410c8`) compares the topology's `phys_id` with
`MPIDR_EL1 & 0xffff`. Bit 31 of `MPIDR_EL1` is RES1 (per the Arm ARM; not re-read in this task; the model's own
value `0x80000000` has it), so the two never match, the function returns -1 and `machine_routines.c:1335`
`cpu_id <= (unsigned int)ml_get_max_cpu_number()` fails inside `cpu_init`, about 2,500 instructions after checkpoint 15.
In the model the kernel's own code does exactly that (`AdtBootCpuReg`, and `evidence_runs.py` `as_built`: stored
`phys_id` `0x80000000`, `MPIDR & 0xffff` `0x0`, first `_Assert` at step 1,044,051, then `panic_trap_to_debugger` ->
`PEInitiatePanic` -> `PE_panic_hook` -> `DebuggerTrapWithState`). The real boot CPU's MPIDR is not known (no run read
it back), but bit 31 makes the outcome independent of it. Fix (not applied; the loader source is NAT-022's): pass
`(uint32_t)(gi.mpidr & 0xffff)`. With the masked value the lookup returns 0 (`test_masked_reg_the_lookup_finds_cpu_0`)
and the model goes on. **A phone run that resumes past checkpoint 15 with the loader as built should be expected to
reach the kernel's panic path** (see "not established").

**(c) Where the model stops.** Loader-equal inputs plus the masked `reg`: checkpoints 11, 30-35, 12, 40-44, 13, 14, 15
(1,041,586 steps; the 950k steps between 14 and 15 are kernel loops that were not examined) and 16 are reached with
these labelled assumptions (`Assumed.assumed` records every use): `cntkctl_el1` = 0, `cntvct_el0`/`cntpct_el0` = a
counter advancing 1000 per read, `daif` read = `0x3c0` when the model's all-masked flag is set, `ccsidr_el1` =
`clidr_el1` = `id_aa64dfr0_el1` = 0 (hardware facts the model does not have; they feed cache-geometry globals).
Checkpoints 17-21 are not reached: the model has no `cnt v0.8b` (SIMD popcount in `sched_update_pset_load_average`,
before 17).

## What is not established

* The compiled stub. `c_resume` is Python acting on the model: it fixes the sequence and what is preserved, not the
  assembly. Caches (the flag and `slot[2]` stores rely on `dc civac`, as in decision 0017, which worked in run 009),
  the TLB (the stub flushes before the `msr`, nothing after it can), exceptions and timers are not modelled.
* DAIF is not restored by any primitive. The model has one boolean (all four masked); every stop reached has it set.
  A kernel that enters `loader_jump` with interrupts unmasked would come back masked.
* `x18` is live (`0x3004000`) and must be preserved; any other register the compiled stub touches must be saved too.
* `TTBR0` after `arm_vm_init` (see 2). Stops 17+ also need the model to run them.
* Beyond a stop the kernel is on the phone's real hardware: ID registers, the real MPIDR, the counter, the
  framebuffer geometry are assumed here (`ASSUMED_MPIDR`, `ASSUMED_FB`; the loader reads them at run time and run 009
  did not report them).
* The panic path (`PE_panic_hook`, `loader_return`, `psci_smp_stop_others`, `redwood_*_quiesce`) is still not analysed
  and may write device registers. Finding (b) makes it the likely outcome of an unfixed run past checkpoint 15.
* The display budget: five asm passes ended about 41 s after the run start (2.7 s per pass) and the watchdog fires at
  83 s, so roughly 15 further passes fit; the 17 stops above do not, without shorter reports or fewer stops (a decision
  for the image, not for this task).

## What this means for the next step (decision question, not asked)

A next image would (1) fix finding (b) in the loader, (2) give `loader_return`'s stub the resume of section 2 with a
selectable list of stops, (3) hold at the last stop it reaches. Its first run could cover checkpoints 11 to 15 and stop
before `cpu_init` is entered again, or run `cpu_init` with the fix and see whether the kernel gets to checkpoint 16.
The next stop after 11 in program order is checkpoint 30 (1,935 model steps later); the order is 11, 30-35, 12, 40-44,
13-21. The on-screen report such an image needs is the run-009 frame protocol (kind/idx/data16/crc8) with one short
pass per stop carrying the checkpoint number, the stop's `SP` and the state words that identify it, and the full report
only at the last stop; the 2.7 s a pass takes is what limits the stop count.
That image needs its own decision (0018): image-specific hashes, the stops it uses, the new hazard (kernel code from
checkpoint 11 on runs on the phone and a fault reaches the unanalysed panic path), the watchdog budget and the
recovery path. NAT-036 covers the host work (loader fix, resumable stub source, host tests); no phone action is part of it.

## Files

* `loader_inputs.py`: `LoaderEqual` (the loader's ADT and `boot_args` in the model), `describe()`; `adt_reg=` selects the
  value written into the boot CPU's `reg` (default: the loader's, the whole MPIDR).
* `cresume.py`: `Assumed`, `c_resume`, `chain`, `reference`, `compare`, `compare_entry`.
* `test_nat035.py`: 23 host checks (about 45 s with a scratch virtualenv that has capstone; `make check` does not run it).
* `evidence_runs.py`: the long runs behind sections 3 and 4(b) (`artifacts/nat-035/runs.json`, gitignored).
* `evidence.json`: provenance, commands, exit codes, hashes.

Run: `<venv>/bin/python -I docs/procedures/nat-035/test_nat035.py` and `<venv>/bin/python -I docs/procedures/nat-035/evidence_runs.py`.
