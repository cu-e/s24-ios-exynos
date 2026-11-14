# NAT-153: native run of loader-diag-xnu-scH-md1: the secondary cores enter at EL2

- **Evidence kind:** native-device.
- **Outcome:** **pass** as a measurement. The criteria registered in decision 0063 were all read.
- **Decision:** 0063 under 0061, one attempt, consumed (`artifacts/nat-153/native-attempt-loader-diag-xnu-scH-md1-used.json`).
- **Restore:** stock RECOVERY and Android verified.

## What ran (local time, 2026-11-14)

| Time | Event |
| --- | --- |
| 04:56:10 | RECOVERY e90fe5b0…9164 written to sda18, readback equal, reboot |
| 04:56:37 | the loader is up (1209:0001) |
| 04:57:56 | md1 delivered: 2475720704 B at 36.19 MB/s |
| after delivery | the loader passed its checkpoint checks (NAT-151's scG did not) and jumped to the kernel: `pre_jump`, then CK n=1, 2, … |
| ≈ +270 s from the jump | timed return to the loader; kernel ring dump why=2, 690654 B (head 8192 + tail 524288, gap 158174), no holes, no drops |
| 05:06:29 | the loader left USB at its 595 s deadline; Download Mode at 05:06:33 (no SEC_UPLOAD, no owner action) |
| 05:08:07 | watcher and collector ended |
| restore | `restore_stock.py` (venv) rc 0; check_android pass at 05:08:59; assess pass |

The owner did not touch the phone during the run (it was about 05:00), so no touch input was recorded.

## Result: where the PSCI-started cores stop

`analyze150` gives `smp` C0-one, running 1 of 10, joined none, `early_where` **E6-mmu-on for all of cpu 1–9**.
`AFFINITY_INFO` = 1 (off) for each of them, read 1 s after `CPU_ON`.

The early marks are nearly the same for every core. cpu 1 as an example:

| Stage | Values | Meaning |
| --- | --- | --- |
| 1 entry | **CurrentEL 0x8**, SCTLR_EL1 0x30d8099a (cpu 1–3) / 0x30d5099a (cpu 4–9) | **the core enters at EL2**. The boot CPU (loader and XNU) runs at EL1 (`EL=0x1` in the loader's log) |
| 2 cpu data found | 0x996dca720 (+0x4000 per core), handler 0x90183e00c | the reset vector found its cpu data and `start_cpu` (PA) |
| 3 | not written | |
| 4 end of `start_cpu` | lr 0xfffffff007431ee0 (`arm_init_cpu`), x23 0x8fe400000 (physical base) | as in the model |
| 5 before MMU | TTBR1 0x996a89000, TCR 0x22a51a251a | |
| 6 after MMU | SCTLR_EL1 0x3454599d, sp 0xfffffff91b9a4000 (a kernel stack VA) | the last mark |

What this shows: XNU's start path programs EL1 (TTBR1_EL1, TCR_EL1, SCTLR_EL1, VBAR_EL1). On a core running at EL2, none of that
translates what the core itself executes. Mark 6 was still written because, with EL2's MMU off, the mark's V=P address is the
physical one.

The next steps of the path need the kernel's virtual addresses: the stack at 0xfffffff9…, then `arm_init_cpu` at 0xfffffff0….
At EL2 with the EL2 MMU off, those addresses cannot be reached. The core takes an exception at EL2 with no vectors of the kernel's,
and it never reaches `arm_init_cpu()`.

This explains NAT-149's "no sign since the firmware took the request". The firmware's `CPU_ON` returns to the non-secure world at
EL2. The boot CPU came to the loader at EL1 (S-Boot's handoff), so the kernel was never written for EL2 entry.

What is **not** established:
- which instruction faults;
- what the EL2 exception does (the core is reported off afterwards: AFFINITY_INFO 1);
- whether EL2 on the secondaries carries any configuration from the firmware (HCR_EL2, CNTHCTL_EL2, ICC_SRE_EL2, CPTR_EL2,
  CNTVOFF_EL2).

## Frame rate (software display path, single core)

`MiniIOMobileFramebuffer`, kernel count, not a camera:
- From 341 s on: 34–37 frames per 5 s window (6–7/s). Each frame took **70.7 ms inside the driver** (0 us waiting for the GPU or for
  the refresh). The longest frame-to-frame time was 79 ms, and half were under 65 ms.
- `analyze150`'s steady-window rule counted 0 windows (`fps_steady_windows` 0, best null), so there is no comparison with NAT-144's
  touch-driven 21.72/s.
- The display verdict is D2-refreshing; the panel had pixels (`decode113` P1, 1149635 non-zero).

A 70 ms driver time per frame caps this path near 14/s even with no other work. The driver's copy of the frame is the first
frame-rate lever, independent of the GPU.

## What this establishes

- scH passes the loader's checks on the phone as on the host: check_loader_sites rc 0 was a sufficient gate.
- The NAT-150/152 marks work on the phone, and `CPU_ON` really starts the cores: they run about 100 instructions of the kernel.
- The cause of "no core joins" is that the cores enter at EL2.
- The next step is a host task: in the reset vector, a core that finds itself at EL2 sets up EL2 for an EL1 kernel and drops to EL1
  by `eret`, as Linux's `init_el2` does. That means HCR_EL2.RW, no stage 2, no traps (CPTR_EL2/HSTR_EL2), timer access
  (CNTHCTL_EL2, CNTVOFF_EL2), ICC_SRE_EL2, VPIDR/VMPIDR and SPSR_EL2 = EL1h with DAIF masked. It must also record what the
  firmware left in those registers.
