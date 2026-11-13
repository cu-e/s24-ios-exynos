# NAT-150: scG, early marks for the PSCI-started cores (host-test)

Evidence kind: host-test. No device was used. Owner claude-opus-usb130-20261113.

## Why

NAT-149 confirmed NAT-148's topology fix on the phone: 10 CPUs were registered, and the retail firmware accepted PSCI `CPU_ON`
(status 0) for cores 1–9. But no core reached `arm_init_cpu()` (`PSCI_SMP_CPU_IN_KERNEL`), and no exception was recorded. The kernel
has no marker earlier than that, so the place the cores stop is unknown. It could be any of:
- no entry at all;
- the cpu-data lookup in the reset vector;
- before the MMU switch;
- after it.

The 9 × 5 s waits also pushed the home screen to about 354 s, so there was no frame-rate window.

## Changes against scF (NAT-148)

Three kernel objects change, rebuilt by KRN-044 together with NAT-143's five patched objects. Those five are byte-identical to
NAT-143's after path normalization.

| Object | Patch | Change |
| --- | --- | --- |
| `osfmk/start.o` | `start.patch` | `PSCI_SMP_EARLY_MARK stage, ra, rb` (only under `GENERIC_PSCI_SMP`). Each core has 128 B of `psci_smp_early_marks`, found by MPIDR Aff1. It holds the last stage reached (`0x5EC00000 \| stage`), the MPIDR, and two values per stage. The core writes it at the address it runs at, then cleans it to PoC. The macro uses only x9/x10; flags are unchanged. See the stage table below |
| `osfmk/psci_smp.o` | `psci_smp.patch` | Defines `psci_smp_early_marks` (128-aligned, `__DATA`). Before `CPU_ON` it zeroes the core's marks and flushes them to memory. In the wait loop it flushes the marks along with the fault record. After a failed wait it prints `psci: cpu N early marks: last … mpidr … 1:a,b … 6:a,b affinity_info S` (PSCI `AFFINITY_INFO`: 0 on, 1 off, 2 on pending). `PSCI_SMP_START_SECONDS` drops from 5 to 1 |
| `osfmk/machine_routines.o` | `machine_routines.patch` | `ml_choose_slow_core_partners()` never makes the boot processor a slower core's secondary. In NAT-149, cpu 0 was paired under cpu 9, which never ran |

Marks written by `start.patch`:

| Stage | Where | Values |
| --- | --- | --- |
| 1 | entry, after the secondary vectors are set | CurrentEL, SCTLR_EL1 as the core came in |
| 2 | cpu data and a valid handler found | cpu data PA, handler |
| 3 | not found, or invalid handler (then `b .`) | x0 (MPIDR & 0xffff, or the handler), x3 (end of the entries) |
| 4 | end of `start_cpu` | lr (the KVA of `arm_init_cpu`), the physical base |
| 5 | `common_start`, a started core (x21 ≠ 0), before the MMU is switched on | TTBR1, TCR |
| 6 | the same, after the MMU is on (V=P) | SCTLR_EL1, sp |

The boot processor's path gains two `cbz x21` instructions and nothing else.

Everything else is scF's:
- the loader (only the attempt tag's immediates differ, in `08-markerlib52.c.o`);
- the root and md0;
- the ADT (one `running` and nine `waiting` cores);
- every command-line token except `nat_attempt=NAT150-scG` (239 B).

## Host model of the start path (`model_secondary.py`, unicorn + capstone)

The model executes the built image, instruction by instruction, with the MMU off.
- Setup: the kernel's segments at a PA base. The boot processor's side (ResetHandlerData, CpuDataEntries, ten cpu data, boot args)
  is filled in as `cpu_start()` leaves it.
- System registers are the model's own: MRS returns model values, and MSR is only recorded.
- A run stops at the first `msr CPACR_EL1`, right after the MMU block, or where a core spins.
- Every case runs on both kernels: NAT-143's as it ran in NAT-149, and NAT-150's.

Result: `artifacts/nat-150/model-secondary.json`.

| Case | NAT-143 | NAT-150 | Comparison |
| --- | --- | --- | --- |
| cpu 4 (MPIDR 0x81000400), handler `start_cpu` | to `CPACR_EL1`, lr = `arm_init_cpu` | same, marks 1, 2, 4, 5, 6, last `0x5ec00006` | same instructions in the same order plus 5 mark blocks; registers (bar x9–x12) and every system-register write equal |
| handler `resume_idle_cpu` | same | same | same |
| MPIDR 0x81000a00 (no cpu data) | spins at `reset_vector+0xa0` | spins at `reset_vector+0x168`, mark 3 with x0 = 0xa00 | same apart from 2 mark blocks |
| null handler | spins | spins, mark 3 with x0 = 0 | same |
| boot processor cold start (`__start`) | to `CPACR_EL1` | same, no marks | exactly 2 instructions inserted (the two `cbz`) |

What the model does not cover:
- the firmware, the Samsung EL2 layer (the loader runs at EL1), caches and coherency;
- real page tables (the MMU stays off);
- anything after the MMU switch.

## Analyser (`analyze150.py`, rule fixed before the run)

It wraps analyze146 and keeps every verdict except `smp`.
- **smp:** `C2-all-ten` when the running count is 10, the banner says 10 and there is no failure line; `C1-some` when the running
  count is above 1; otherwise `C0-one`. analyze146's old label stays as `smp_rule146`.
- **joined:** the cores asked for (the `cpu_start` lines, excluding the boot processor) that have no failure line.
- **early marks:** per core, `where` is one of `E0-no-entry`, `E1-entry`, `E2-cpu-data-found`, `E3-no-cpu-data`, `E4-start-cpu`,
  `E5-before-mmu`, `E6-mmu-on`. Each also gets the values per stage and the affinity state.

On NAT-149's real text: `smp` C0-one (rule146: C1-some), running 1, joined [], not joined 1–9, no marks.

## Build

| Item | Value |
| --- | --- |
| kernel | `artifacts/nat-150/kernel-001`, kernel.no-storage `c84e72397f3bfad01e5fd305d15bc2340dc96629fe6517c81f00627aa2ee8901`, 0 undefined, 29 stubs. `__start` 0x…b570 (same page as `LowResetVectorBase`); `psci_smp_early_marks` 0x…d10b00 |
| image | `loader-diag-xnu-scG-md1`, tag `nat_attempt=NAT150-scG` |
| RECOVERY (100663296 B) | `a9f0eed0175fc9f4aea26dd67a50b6f2ca5b62494cf70414250f3700d8dd6de0` |
| payload (26206896 B) | `a68fd474af6775d5c66c525edf66b0baf006ff9e169795f0c67bf1e70cd2c213` |
| loader Image | `de0e0d87b2c7b47828257369d80ddb448be42d946b654eb4060fbde5b393afc0` |
| session | `session_nat151.py` `7a8b73318297e7084a0e6db323644bc1d7d97a839a8641d7fbd6310c82a51ec4`, counted from `session_nat149.py` (`derive151.py --check`); precondition list + NAT-150 |

Payload against scF:
- same segment VM layout; only `__LINKEDIT` grows by 256 B (the new symbol);
- the md0 segment, the ADT and everything after them are byte-identical;
- the header differs in the tag and the offsets.

nat-123/build.py requires a kernel record with exactly its four extra objects. For that one check, `build.py` shows it this kernel's
record without the three NAT-150 objects. `check_kernel()` verifies those three: their patches and hashes, and the NAT-143 objects
unchanged.

## Tests

| Command | Result |
| --- | --- |
| `artifacts/nat-065/venv/bin/python -B docs/procedures/nat-150/test_nat150.py` | 15 OK: objects, patch shape, symbols, the model cases above, the analyser on NAT-149/NAT-144's real text plus synthetic marks, the printf format against the parser, the payload against scF, the build record, the session derivation |
| `python3 -B docs/procedures/nat-150/test_nat150.py` | 15, of which 4 skip without unicorn |

## For the native run (NAT-151, decision 0061 + its per-image file)

- Expected without new knowledge: the same as NAT-149, a single running core, but each failed core now has an early-marks line and
  an affinity state. The 1 s wait leaves the home screen at about NAT-144's time, so the single-core frame rate can be measured too.
- Risks:
  - The boot path changes by two `cbz` (model-checked).
  - A started core writes at most 128 B of its own marks and nothing else new.
  - If it fails before the kernel feeds the watchdog, the SEC_UPLOAD loop of NAT-146 is possible. The owner breaks it with:
    1. Volume Down + Side 7–10 s;
    2. then Volume Up + Volume Down;
    3. then Volume Up.
