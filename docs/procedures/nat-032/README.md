# NAT-032: what the payload kernel runs after assembly checkpoint 5, and how to resume past it

Evidence kind: source-review plus host-test (real payload bytes decoded with capstone; the NAT-030
instruction-level model). Nothing here ran on the phone, no image was built and no decision was requested.
Date: 2026-11-11. Owner: claude-nat032-20261111-cpath.

Inputs (local, not committed): `artifacts/nat-020/build-003/payload.bin` (SHA-256 `071bc632...caf544`, the bytes the
loader copies), `artifacts/nat-020/build-003/kernel.no-storage` (symbol names only),
`artifacts/nat-029/payload-analysis.json` (slot, sites, checkpoint tables). Run 008 (decision 0016,
`docs/procedures/nat-022/native-attempt-008-evidence.json` and its README section) is the only hardware evidence used.

Files: `after5.py` (static reach + the model run, `--out FILE` writes `artifacts/nat-032/reach-after5.json`),
`test_nat032.py` (15 host checks), `evidence.json`.

```
capvenv/bin/python -P docs/procedures/nat-032/test_nat032.py      # needs capstone; skips (and says so) without it
capvenv/bin/python -P docs/procedures/nat-032/after5.py --out artifacts/nat-032/reach-after5.json
```

`make check` does not run this directory (it has no capstone); the system `python3 -I` skips every case.

## What this task answers

Run 008 showed the kernel's own start code reaching assembly checkpoint 5 on the phone and the loader's return
stub holding there. The next useful step is to continue past it, so one camera recording shows more than one new
fact. This note says what the kernel executes between checkpoint 5 and the first safe C checkpoint, what the model
does and does not cover, and a resume design that was checked in the model. It does not authorize anything.

## Established (host)

1. **The resume does not need a trampoline.** The stop at checkpoint 5 clears `SCTLR_EL1.M` and branches to the
   loader's stub in the loader image (PA about `0x801a0000`, NAT-022 README), which is **outside** the kernel's TTBR0
   identity range `0x9e1400000..0x9fe200000` (NAT-030 README). Two earlier ideas therefore do not work:
   NAT-029's "the stub restores `SCTLR_EL1.M` and branches to the site's continuation" (with M set the next instruction
   fetch is at the stub's VA, which the kernel's TTBR0/TTBR1 do not map: a translation fault into the kernel's own
   vectors, not a controlled resume), and a trampoline in the 725 NOP words
   after the kernel's entry. Both are superseded by this: the stub restores every live register and the SP (the
   existing stub frame already does), keeps `SCTLR_EL1` as it is (M clear), and branches **MMU off** to the kernel's
   own code 28 bytes before the checkpoint-5 macro, `0xfffffff00743e454` (PA `0x9e183e454`). That is the kernel's
   `movk x0 ...; msr sctlr_el1, x0; isb; cbnz x21` block, which turns the MMU on itself from code that is mapped
   in the identity range, then runs the checkpoint-5 macro, which no longer stops because slot[2] has a different
   number. (`test_resume_reenables_the_mmu_and_skips_the_stop`.)
2. **Differential check in the model.** Stop at 5, clobber and taint x0..x3 and x9..x11 with a junk value, write
   slot[2] = 11, set the PC to `site5 - 28`, run to the first C checkpoint. The result equals the uninterrupted run
   (no stop at all, slot[2] = 11) in all general registers, all system registers and every non-zero RAM page, for
   two different junk values, with no taint violation (nothing after the resume reads a clobbered register before
   writing it). (`test_resumed_state_equals_the_uninterrupted_state`, `test_no_read_of_a_clobbered_register`.)
3. **Negative controls.** Resuming at `site + 60` with the MMU still off (the obvious "skip the macro") fails in the
   model; resuming with slot[2] unchanged stops again at 5; resuming with a wrong `x21` (the boot-CPU flag
   `cbnz x21` reads) takes the other path or faults. So `x21` must be restored exactly. The stub already restores
   x0..x30. (`test_obvious_resume_at_site_plus_60_leaves_the_mmu_off_and_fails`,
   `test_resume_with_slot_unchanged_stops_again`, `test_resume_needs_x21_preserved`.)
4. **From the resume to the call of `loader_checkpoint(10)`: 275 model steps**, three system-register writes
   (`sctlr_el1 = 0x3454593d` at PA `0x9e183e464`, `cpacr_el1 = 0x300000` at `...e4c0`, `tpidr_el1 = 0` at `...e4c4`) and
   three calls: `arm_set_kernel_tbi`, `memmove`, `loader_checkpoint` (x0 = 10).
   (`test_call_sequence_from_the_resume_to_c_checkpoint_10`.) Run 008 measured `SCTLR_EL1 = 0x3454599c` at
   checkpoint 5 (M cleared by the stop), against the model's `0x3454593c`: only bit 5 (`CP15BEN`: model 1, hardware 0)
   and bit 7 (`ITD`: model 0, hardware 1) differ, both AArch32-EL0 controls; the hypothesis recorded in run 008 is
   that they are architecture-fixed on a core without AArch32 EL0 (not verified). The other three registers
   matched exactly. The resumed block rewrites `SCTLR_EL1` from the kernel's own constant `0x3454593d`, so whatever
   the core does with those two bits happens again on the resume; this is the only place where the resumed state
   is not identical to the model's. It stays under the unknowns.
5. **C checkpoint order.** C numbers (10..21, 30..35, 40..44) are disjoint from the assembly numbers 1..5.
   In `arm_init` the program order after the resume is: 10 (`+0x468`), `cpu_data_init` (`+0x478`),
   `PE_init_platform(0, boot_args)` (`+0x484`), 11 (`+0x48c`), then 30... The model stops at the first SIMD
   instruction (`cpu_data_init+0x10`, `movi v0.16b, #0`; it has 17 SIMD instructions). Everything after cp10 is
   review-only in this project. **Checkpoint 10 is not a safe stop**: a stop there faults on the NULL
   `PE_state.bootArgs` in the model; **checkpoint 11 is the first safe C stop**.
6. **`loader_checkpoint(n)`** is `nop; nop; ldr x8,[slot+0x10]; cmp x8,x0; b.ne ret; mov x1,x0; mov w0,#2; b
   loader_jump; ret`. It compares slot[2] with its argument. `loader_jump` (500 bytes at `0xfffffff00744f1cc`) parses the boot-arg
   `bootcpu`, calls `gic_v3_irq_quiesce`, sets `loader_return_entered` (byte at `0xfffffff007d77009`), writes
   `TCR_EL1` (EPD0 cleared) and `TTBR0_EL1` for a private 2 MiB 1:1 block (descriptor `0x601`: AttrIndx 0, which is
   MAIR byte 0 = `0xff` = Normal write-back, not Device, using the MAIR value of the model; MAIR_EL1 was not read back on
   the phone), runs `tlbi vmalle1` and `br x5` to the stub with MMU and caches **on**: x0 = log PA, x1 = log length,
   x2 = 2, x3 = n. It is not resumable (`loader_return_entered`, changed TCR/TTBR0, and the C return address is gone).
7. **The first `PE_init_platform(0, args)` call is benign statically.** With `vm_initialized = 0` it skips
   `pe_arm_init_interrupts` and `pe_arm_init_debug` (`cbz w20` / `cbnz w20`; the only `ml_io_map` users). The path
   without the panic and `vm_initialized` edges is 46 functions: no system-register access, no `svc`/`hvc`/`smc`, no
   `tlbi`/`dc`/`ic`; two indirect branches, both compiler jump tables (`_PE_parse_boot_argn_internal`, `_argnumcpy`:
   `cmp; b.hi; adrp; add; adr; ldrb; add x10, x10, x11, lsl #2; br x10`); SIMD in `PE_init_platform` itself
   (`ldur/str q0` of `boot_args`), `SecureDTLookupEntry`, `pe_identify_machine`, `strlen` and `strncmp`.
   The payload's ADT (16 nodes, Apple format, at payload offset `0x148afd0`) has what the first call reads: `/chosen`,
   `/cpus/cpu0` with the six frequency properties and `state = "running"`, `target-type` and `model` on the root.
   (`test_first_platform_call_is_the_vm_not_initialized_one`, `test_adt_has_what_the_first_platform_call_reads`.)
8. **`gic_v3_irq_quiesce` is a no-op here.** It loads `gicd_base` (`0xfffffff007e867b0`) and branches to its epilogue
   on zero; the payload holds 0 there, and the only direct writer is `_gic_v3_irq_cpu_init`, which is in the direct-call
   closure of none of `arm_set_kernel_tbi`, `memmove`, `cpu_data_init`, `PE_init_platform` (an over-approximation, so
   "cannot be reached by a direct call"; indirect calls are not followed).
   (`test_gic_state_pointer_is_zero_and_nothing_on_the_path_sets_it`.)

### Static reach (depth 4, over-approximate: every direct `bl` and tail `b`, no indirect call)

| Root | Functions | System registers | Cache / TLB | SVC |
| -- | -- | -- | -- | -- |
| `loader_checkpoint` / `loader_jump` | 12 / 11 | R tcr, tpidr; W cntv_ctl_el0, daifset, icc_eoir1_el1, icc_igrpen1_el1, tcr, ttbr0 | `dc cvac`, `tlbi vmalle1` | none |
| `cpu_data_init` | 1 | none | none | none |
| `PE_init_platform` (all edges) | 112 | R cntvct, daif, id_aa64dfr0, tpidr; W daifset, daifclr | `tlbi` (vmalle1is, aside1is, vae1is, ...) | none |

The 112-function closure includes the panic and `vm_initialized` edges that the first call does not take; the
`tlbi` and `daif` accesses live there. The full table is in `artifacts/nat-032/reach-after5.json` (sha256 in
`evidence.json`).

**Not modelled** by NAT-030 (so everything below is review-only for the phone): caches, TLB, exceptions,
timers, SIMD, devices, memory attributes (data accesses with the MMU off are Device on hardware). The model's stub
stand-in sits at window base + `0x4a00000`, which is inside the kernel's identity range; the real stub is not, so
the model cannot show a fault for code run under the kernel's MMU at the stub's address.

## Design: resume at checkpoint 5, stop at a C checkpoint

Stub sequence for the next image (NAT-033, not built), on an asm-checkpoint arrival with N = 5:

1. draw the checkpoint report (as run 008), then choose the next stop: **11** for the first run past 5 (the first safe
   C stop); asm checkpoints 1..4 resume exactly as in decision 0016 (site + 60 with slot[2] = N + 1, unchanged);
2. write slot[2] with the cache order `dc civac, slot; dsb sy; str; dsb sy; dc civac, slot; dsb sy`. Reason: from
   checkpoint 5 on, the kernel reads slot[2] through a cacheable mapping and holds the line; a stub write with the MMU off
   goes to memory and would leave the kernel's stale line (value 5) to stop it again, and a dirty kernel line
   written back later would overwrite the new value; checkpoints 1..4 read it MMU-off, so they never needed this;
3. restore x0..x30 and SP from the frame, with `x21` exactly as at the stop (it is the primary/secondary flag);
4. `br` to `site5_va - 28` (`0x9e183e454`) with the MMU off. No `SCTLR_EL1` write in the stub. The existing
   restore sequence loads the continuation address into x9; resuming at `site5 - 28` the kernel's `movk x0 ...`
   block sets x0 itself, and nothing after it reads x9 before writing it (`test_no_read_of_a_clobbered_register`).

Hold policy: a C stop at 11 is final (the stub holds and reports; no resume, no retry). If the kernel instead
reaches an early-exception report or a panic via `loader_return`, the stub reports and holds as before. A hang with
no report is a silent outcome (the 83 s watchdog ends the run, as in runs 001-008).

### Arrival at a C checkpoint (needed by the same image)

`loader_jump` arrives **MMU on, caches on** at the stub's PA through its private block with x0 = log PA, x1 = log
length, x2 = 2, x3 = n. The existing stub assumes MMU off (the asm path clears M). A new prologue must, with
registers only and no memory access: clear `SCTLR_EL1.M` (and C), `isb`, `ic iallu`, `dsb`, `isb`, then continue
into the existing code. The prologue must be 4-byte aligned and contiguous so that instruction fetch stays inside
the private 2 MiB block; the stub's own code, stack and data are in the loader image, mapped by that block only if
they lie in the same 2 MiB (unchecked: see unknowns).

### Panic path (not a planned stop; what a failure could do)

A kernel panic reaches `_loader_return` → `psci_smp_stop_others` (guarded by `_psci_smp_started`, probably 0;
`hvc/smc 0xC4000004` = AFFINITY_INFO) → `redwood_{ufs,adreno,wifi,adsp,ddr,haptic,torch,camera,mic}_quiesce` →
`loader_jump(0, 0)` with x2 = 0. The MMIO behaviour of the quiesce functions is **not analysed**. A panic before
cp11 would therefore run kernel code that touches device registers on the phone; this is the main reason the next
decision must name it.

## Unknowns (each one a limit of the next decision, not a blocker for a host task)

* hardware behaviour of `arm_init` after cp5: `cpu_data_init` and `PE_init_platform` (SIMD, not modelled), caches,
  TLB and exceptions with the MMU on;
* the cause of the `SCTLR_EL1` bits 5/7 difference (hypothesis only) and whether it matters after the re-enable;
* stack coherence with the MMU on (the kernel's stack lines written MMU-on, the stub's restore reads them MMU-off);
* the real MAIR/attributes of the private 2 MiB block and whether the stub, its stack and the log all lie in it;
* I-cache coherence for the stub code fetched through the MMU-on arrival (Normal WB block);
* the panic-path MMIO in `redwood_*_quiesce` and `psci_smp_stop_others`;
* resumable C checkpoints (clear `loader_return_entered`, restore TCR/TTBR0 and the return address via the x29 frame)
  and whether the stub's PA is inside a range the kernel's TTBR0 could keep (needed only for that);
* anything past cp11.

## Next image proposal (NAT-033; needs its own task, host tests and a decision numbered 0017)

`loader-diag-xnu-ckpt2`: the run-008 loader, plus: (a) at N = 5 the resume above with slot[2] = 11; (b) the C-arrival
prologue; (c) the same marker protocol (CKPT kind 11, STAGE 0x51) with x2:x3 = `0x0211` for the C stop at 11.
Expected outcomes, none a failure of the phone and none retried: a cp11 report (the kernel ran `arm_init` through
`cpu_data_init` and `PE_init_platform` and the C path works); a held report at 5 again (the resume failed);
an early-exception report (mask bit 8: ESR/ELR/FAR); a panic report via `loader_return` (reason 0); or silence
(inconclusive). The decision must name: the Image hashes, device access identical to decision 0016, the new hazard
(kernel code past checkpoint 5 runs on the phone; a panic would reach the quiesce MMIO), what the model does not
cover (the list above), the recovery path (NAT-013 restore of the pinned stock RECOVERY), and a "Not granted" list
(anything past cp11, resuming C checkpoints, retries, any other partition).

A cheaper host step first (idea, not started): a full-ISA emulator (Unicorn) run of cp10 to cp11 would cover the SIMD
gap that the NAT-030 model stops at.

## Not established

Nothing in this directory shows that the S24 behaves like the model after checkpoint 5, that the resume works on
hardware, that `cpu_data_init`/`PE_init_platform` run on it, or that XNU boots. A cp5 resume or a cp11 report would
be the first evidence on any of that.
