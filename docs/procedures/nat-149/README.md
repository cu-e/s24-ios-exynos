# NAT-149: native run of loader-diag-xnu-scF-md1: the topology fix works, but no secondary core joins

- **Evidence kind:** native-device.
- **Outcome:** **fail** for the SMP goal (task not complete).
- **Decision:** 0060, one attempt, consumed (`artifacts/nat-149/native-attempt-loader-diag-xnu-scF-md1-used.json`).
- **Restore:** stock RECOVERY and Android verified.

## What ran

- **03:29:16 local:** RECOVERY 56e9d3ac…6d3d written to sda18, readback equal, then reboot.
- **03:29:36:** loader up.
- **03:30:54:** root delivered at 36.17 MB/s.
- **03:39:27:** the run ended through the normal path: timed return, then the loader's log dump, then its deadline.
- **03:39:31:** Download Mode came up by itself ("SAMSUNG USB").
- **Restore:** `restore_stock.py` (venv) rc 0, then check_android pass at 03:40:19 (boot_completed=1, stock RECOVERY hash,
  user-data dirs), then assess pass.
- No SEC_UPLOAD loop.

The kernel log dump why=2 (517830 B, no holes) was received. The loader checkpoint records reach 21, as in NAT-144.

## Results (`artifacts/nat-149/analysis/kernel-text.txt`)

| Item | Observation |
| --- | --- |
| Topology (the NAT-148 fix) | **passed**: `memory 4096 MB, page size 16384, 10 cpu`; `GenericARMCPU: cpu 0..9 (phys id 0x0..0x900) registered` |
| Slow-core pairing | `cpu 3→6, 2→7, 1→8, 0→9`: "is a slower core: the scheduler uses it after cpu N". The **boot CPU 0** was paired as the secondary of cpu 9 |
| PSCI CPU_ON | **accepted by the firmware for all nine cores**: there is no "was not started" line, so every call returned 0 (success) |
| Secondaries | **none joined**. cpu 4..9 at 105.1–135.1 s and cpu 1..3 at 163.1–178.1 s each report "was started 5 seconds ago and has not joined: **no sign of it since the firmware took the request**" |
| Running | `GenericARMPE: 1 of 10 processors are running`; "the slower cores started too: 1 processors running" |
| Fault catcher | no "took an exception on its way in" line |
| Cost | 9 × 5 s waits in the boot path. The home screen came at about 354 s (the donor's automatic unlock); in NAT-144 it came at about 243 s. Only about 15 s of UI time remained before the 270 s return |
| UI | 4 presses, 17 frame changes; 3 frame-statistics lines, none a steady window. **No frame rate can be measured from this run** |

`analyze146.py` verdict line: smp **C1-some**. That label is wrong, and the fault is in the analyser rule, not the phone. "started"
counts `cpu_start() cpu: N` lines, which the boot processor prints for each core it asks for; they do not show that the core ran.
The facts are running = 1, all nine cores listed as not joined, and the init banner showing 10 because of hw.ncpu. Read the result
as **no secondary ran** (C0 in substance). The rule must count joins or the running count instead.

## What this establishes

- NAT-148's cause and fix are confirmed on the phone: with one "running" node, the kernel passes `ml_parse_cpu_topology` and
  registers ten CPUs.
- The retail secure firmware accepts PSCI CPU_ON from this EL1 kernel (status 0) for MPIDRs 0x100–0x900, with entry =
  `ml_static_vtop(LowResetVectorBase)`.
- The cores do not reach `arm_init_cpu()` (the first stage marker, `PSCI_SMP_CPU_IN_KERNEL`), and no exception is recorded.
- The system survives the failure and still ends through its own stop path.

## Not established

Where the cores are: never started at the entry, spinning in the reset vector's cpu-data lookup (`Lskip_cpu_reset_handler`), or
stuck before the MMU is on. psci_smp.c has no marker before `arm_init_cpu()`. Candidates to separate:
- The entry PA or exception level as the core sees it. The loader runs at EL1 (`EL=0x1`), so an EL2 layer belonging to Samsung is
  present and may handle the core's entry.
- A failed MPIDR match in `start.s`: an MT/Aff bit difference on the real core.
- Cache or visibility of the cpu data at MMU-off.

## Next

1. Host: per-core early markers in `start.s`. At `LowResetVectorBase`, after the cpu-data match and before the MMU is turned on,
   write to a physical scratch word, then clean to PoC. The boot CPU reads the markers back (after invalidating its copy) and prints
   them with the "has not joined" line.
2. Host: fix the analyser rule (joins and running count, not `cpu_start` lines). Use a shorter start wait, or start the cores after
   SpringBoard, so a failed start does not cost UI time.
3. Do not pair the boot CPU as a secondary of a core that has not joined.
4. Each of these needs its own decision for a native run.
