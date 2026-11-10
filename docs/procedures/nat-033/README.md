# NAT-033: the payload kernel from the checkpoint-5 resume to C checkpoint 11, in the model

Evidence category: **host-test** (an instruction-level model of the real payload bytes, checked against Unicorn where
it is extended). Nothing was built for, flashed to, run on or read from the phone, and no decision was requested.
The phone is in normal Android with stock RECOVERY. Everything below says what the *model* does; what the S24 does
after assembly checkpoint 5 is still unknown.

## Question

NAT-032 designed a resume at assembly checkpoint 5 (the stub sets `slot[2] = 11`, restores every register and
branches MMU-off to the kernel's own MMU-enable block at `0xfffffff00743e454`) but the model stopped at the first
SIMD instruction in `cpu_data_init`, 275 steps after the resume. Does the whole path to the first safe C
checkpoint (11) work in the model, and what does the stub see when it arrives there?

## Established (host-test)

1. **SIMD forms.** The direct-call closure of `cpu_data_init` and `PE_init_platform(0, boot_args)` (see
   `test_nat033.py::path_closure`, re-derived from the payload bytes on every run) contains 16 SIMD/FP instruction
   forms: `add and cmeq cmhi dup eor fmov ldr ldur movi orr stp str stur uminv ushl`. `simd.py` implements them in a
   subclass `SimdSim` of the NAT-030 interpreter (`kstart_sim.py` and `after5.py` are unchanged). Each of the 86
   distinct instruction words in the closure is executed in the model and in Unicorn on three random register/memory
   states plus edge values (all-ones, zero, 0x80 lanes, carries) and the x registers, SP, Q registers, a 128 KiB
   buffer and the PC are compared. A negative control (a deliberately wrong `cmhi`) makes the comparison fail, and
   the same code with correct semantics passes, so the comparison does discriminate. Forms outside the list (`abs`,
   `saddl`, `dup` element form, FP arithmetic) raise `SimFault("unsupported")` like the base class.
2. **The run.** With these, the model runs the real kernel from the entry to the C stop at checkpoint 11 two ways:
   - *reference*: `slot[2] = 11` from the start, nothing stops it earlier: 9411 steps;
   - *resumed*: `slot[2] = 5`, stop at assembly checkpoint 5 (8200 steps), then the NAT-032 resume (`x0..x3`, `x9..x11`
     clobbered with junk, `slot[2] = 11`, MMU-off branch to `site5 - 28`): 9433 steps.
   The two arrive at the stub with **identical** x registers, vector registers, system registers and RAM (every
   non-zero page); no taint violation (no read of a register the stop path clobbered). The 22 extra steps are the
   replay of the MMU-enable block and the checkpoint macro. The only system-register difference in the *write
   sequence* is two extra writes in the resumed run: the checkpoint macro's MMU-off write (`sctlr_el1 = 0x3454593c`,
   just before it branches to the stub) and the replayed MMU-on write (`0x3454593d`).
3. **Arrival state at the stub** (both runs): `x0` = `loader_log` PA `0x9e1f90a00`, `x1` = 0 (the length passed is
   `loader_log_len`: the kernel logged nothing), `x2` = 2, `x3` = 11, `x5` = stub PA; MMU **on**, DAIF masked;
   `SCTLR_EL1` `0x3454593d`, `TCR_EL1` `0x22a51a251a`, `TTBR1_EL1` `0x9e15af000` (the kernel's), `TTBR0_EL1`
   `0x9e2279000` (loader_jump's private table, inside the RAM window, not the kernel's bootstrap `0x9e15ae000`),
   `VBAR_EL1` `0xfffffff007437000`, `MAIR_EL1` `0x0c08044f00bb44ff`, `CPACR_EL1` `0x300000` (FPEN = 3, written by the
   kernel at `0x9e183e4c0`, after the replayed block and before any SIMD instruction), `loader_return_entered` = 1.
4. **The executed path** (not only statically reachable): 67 function entries, 23 distinct functions, in order:
   `arm_init` → `arm_set_kernel_tbi` → `memmove` → `loader_checkpoint(10)` → `cpu_data_init` → `PE_init_platform` and its
   callees (`__strlcpy_chk`, `strlen`, `SecureDTInit`, `pe_identify_machine`, `pe_arm_get_soc_base_phys`,
   `SecureDTFindEntry`/`find_entry`, `SecureDTLookupEntry`, `pe_init_debug`, `PE_parse_boot_argn`, `PE_boot_args`,
   `PE_i_can_has_debugger`, `SecureDTGetProperty`) → `loader_checkpoint(11)` → `loader_jump` → `gic_v3_irq_quiesce`
   (the zero-pointer early return) → `PE_parse_boot_argn` (the `bootcpu` parse) → the stub. No function with `panic` in
   its name, no `ml_io_map`/`pmap_map`, `psci`, `redwood` or GIC-init call. The model raises `external-abort` for any
   physical access outside the RAM window, so the run also proves **no MMIO access** on the path (in the model).
   `loader_log_len` = 0, so there is no log text.
5. **System registers written** (reference run, in order, `pc` of each in `c11.json`): `daifset`, `vbar_el1`
   (physical, the kernel's bootstrap vectors), `tpidrro_el0`, `tpidr_el0`, `tcr_el1`, `ttbr0_el1`, `ttbr1_el1`,
   `mair_el1`, `vbar_el1` (virtual), `sctlr_el1`, `cpacr_el1`, `tpidr_el1`; then in C `daifset`, `tcr_el1`, `ttbr0_el1`
   (loader_jump, where the stub is entered). 15 writes, none of them an unexpected register.
6. **SIMD instructions that actually ran**: 39 (`cmhi eor fmov ldr ldur movi orr stp str stur uminv`); `add and cmeq
   dup ushl` are implemented and cross-checked but sit on branches this run does not take. Five accesses on the path
   are not naturally aligned: two 16-byte vector accesses (`stur q` at `0xfffffff00742e354`, `ldr q` at
   `0xfffffff007443280`, both to odd addresses) and three 8-byte general-register loads (`ldr x6, [x1], #8` in
   `memmove` at `0xfffffff007ad8e34`). The model records the page attribute of each: all five hit TTBR1 pages whose
   MAIR byte is `0xff` (Normal write-back), and `SCTLR_EL1.A` is 0, so they are legal. On Device memory they would
   fault.

## What the model does not show

- **Caches and coherence.** The model has none. Data the kernel writes MMU-off (Device-like) and reads MMU-on
  (Normal write-back), the loader's `slot[2]` write and the stub's instruction fetch are all coherent by construction.
  The NAT-032 civac sequence is designed for this, but a coherence bug would be invisible here.
- **TLB, exceptions, timers, interrupts.** Any fault would, on the S24, vector to the kernel's own handlers at
  `VBAR_EL1`; their panic path (`loader_return` → `psci_smp_stop_others`, `redwood_*_quiesce`) is not analysed.
- **Boot arguments and device tree.** The model builds `boot_args` and the ADT as `loader.c` (NAT-022) does, with
  the `boot_args` base measured in run 007. What the loader actually passes on the phone was not read back.
  **Correction (NAT-035, 2026-11-11):** that sentence was overstated. The NAT-030 `Sim` wrote only the memory fields of
  `boot_args` (`deviceTreeLength` `0x4000`, no `Video`, no `CommandLine`) and never wrote the ADT bytes: the ADT region
  was zero, so every SecureDT lookup failed in the model, `pe_arm_get_soc_base_phys` returned 0 and `pe_identify_machine`
  returned early. The checkpoint-11 arrival state listed here is unchanged when the real inputs are used (NAT-035
  `loader_inputs.py`: the loader's patched ADT, `deviceTreeLength` 13960, `Video`, `CommandLine`; the same `x0`..`x3`,
  `TTBR0/1`, `TCR`, `VBAR` as run 009 measured), but a model run that continues past checkpoint 11 with the zero ADT
  is not meaningful (NAT-035 saw a `brk #0x1206` UBSan trap in `wfe_timeout_configure` that only the zero ADT caused).
  See `docs/procedures/nat-035/README.md`.
- **The stub's physical placement.** The model's stub stand-in `0x9e2e00000` lies inside the RAM window; the real
  loader is near `0x801a0000`, outside the kernel's TTBR0 identity range. Whether the stub, its stack and `loader_log`
  lie inside `loader_jump`'s private 2 MiB block is **not** established (the block is Normal write-back, MAIR byte 0).
- **SCTLR bits 5 and 7.** Run 008 read `0x3454599c`; the model has `0x3454593c` at checkpoint 5. Bit 5 (CP15BEN) and
  bit 7 (ITD) differ; the hypothesis that they are architecture-fixed on a core without AArch32 EL0 is unverified.
- **FP/SIMD.** The model has no FPCR/FPSR and no trap for `CPACR_EL1.FPEN`; the SIMD semantics are checked against
  Unicorn, an independent implementation of the architecture, not against the S24 core.

## Updated unknowns (NAT-032 list)

Closed *in the model*: the SIMD gap (cp10→cp11 runs end to end), the resume equals the uninterrupted run, FPEN is set
by the kernel itself on the resumed path, the five unaligned accesses are to Normal memory, no MMIO or panic call is
on the path. Still open on the S24: everything in the previous section, plus whether `loader_checkpoint(10)` is
reached at all (it is the first C code after the resume) and whether the kernel's second MMU enable behaves as in the
model after the loader's `dc civac` sequence.

## Proposal: NAT-034 (image, host-tested) and decision 0017

Not started; it needs its own task, host tests and an image-specific owner decision. Requirements:

1. Run-008 loader plus: the checkpoint-5 resume exactly as NAT-032 (restore all registers and SP and `x21`,
   `slot[2] = 11` under `dc civac; dsb; str; dsb; dc civac; dsb`, branch MMU-off to `0xfffffff00743e454` /
   PA `0x9e183e454`); a **C-arrival prologue** that clears `SCTLR_EL1.M` (read-modify-write) before touching memory
   outside `loader_jump`'s private block; a hold at checkpoint 11 that reports `x0`/`x1` (log PA and length), `SCTLR`,
   `TCR`, `TTBR0/1`, `VBAR`, using a new mask bit.
2. NAT-031 object code stays byte-identical (new files or `#ifdef`s); extend the compiled-chain test with a cp5 → cp11
   chain and add a one-shot marker for the session driver.
3. The decision must state: image hashes, device access, the risk (a hang or a fault into the kernel's own vectors;
   a reboot into Download Mode, which is how runs 001-008 ended), recovery (NAT-013 restore of stock RECOVERY with
   the pyusb venv, Android verified afterwards), and "Not granted" (anything past cp11, resumable C checkpoints,
   MMIO, GPU, a second run).
4. Later separate tasks: resumable C checkpoints, a log transport that does not need video, GPU bring-up.

## Files

- `simd.py`: `SimdSim`, the SIMD forms and the page-attribute diagnostic `attr_of`.
- `c11.py`: the reference and resumed runs, the arrival state, the function sequence; `--out FILE` writes JSON
  (`artifacts/nat-033/c11.json`, gitignored).
- `test_nat033.py`: 14 tests (form list derived from the payload, 86-word Unicorn comparison, negative control, both
  runs and their comparison). Needs capstone and unicorn (a scratch virtualenv outside the repository); the system
  `python3 -I` skips them. `make check` does not run it.
- `evidence.json`: provenance, commands, hashes.

Run: `<venv>/bin/python -I docs/procedures/nat-033/test_nat033.py` and
`<venv>/bin/python -I docs/procedures/nat-033/c11.py --out artifacts/nat-033/c11.json`.
